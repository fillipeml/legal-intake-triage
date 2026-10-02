from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..clock import today
from ..models import NOT_IDENTIFIED, Complexity, Decision, DemandStatus
from ..pipeline.decision import DecisionError, decide
from ..pipeline.metrics import closed_via_gap, compute_metrics
from ..services import Services

TEMPLATES = Path(__file__).parent / "templates"
COOKIE = "intake_session"


def create_app(services: Services) -> FastAPI:
    settings = services.settings
    app = FastAPI(title="Legal intake console", docs_url=None, redoc_url=None)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    signer = URLSafeSerializer(
        settings.console_secret or "demo-secret-not-for-production", salt="session"
    )
    protected = bool(settings.console_password)

    def user_of(request: Request) -> str | None:
        raw = request.cookies.get(COOKIE)
        if not raw:
            return None
        try:
            return signer.loads(raw).get("email")
        except BadSignature:
            return None

    def render(name: str, request: Request, **context) -> HTMLResponse:
        template = env.get_template(name)
        return HTMLResponse(
            template.render(
                request=request,
                user=user_of(request),
                demo=settings.demo_mode,
                firm=settings.firm_name,
                protected=protected,
                **context,
            )
        )

    def gate(request: Request) -> RedirectResponse | None:
        if protected and not user_of(request):
            return RedirectResponse(f"/sign-in?next={request.url.path}", status_code=303)
        return None

    @app.get("/sign-in", response_class=HTMLResponse)
    def sign_in_page(request: Request, next: str = "/"):
        return render("sign_in.html", request, next=next, error="")

    @app.post("/sign-in")
    def sign_in(
        request: Request, email: str = Form(...), password: str = Form(""), next: str = Form("/")
    ):
        email = email.strip().lower()
        if protected and not hmac.compare_digest(password, settings.console_password):
            return render("sign_in.html", request, next=next, error="Wrong password.")
        if not settings.is_internal(email):
            return render(
                "sign_in.html", request, next=next, error="Use an address of the firm's domain."
            )
        # "//evil.example/..." starts with "/" and is a protocol-relative URL that the
        # browser resolves to another host, so the single-slash test was an open redirect.
        safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
        response = RedirectResponse(safe_next, status_code=303)
        response.set_cookie(COOKIE, signer.dumps({"email": email}), httponly=True, samesite="lax")
        return response

    @app.post("/sign-out")
    def sign_out():
        response = RedirectResponse("/sign-in", status_code=303)
        response.delete_cookie(COOKIE)
        return response

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        if redirect := gate(request):
            return redirect
        metrics = compute_metrics(services, today(settings))
        pending = services.registry.list(status=DemandStatus.AWAITING_VALIDATION)
        recent = sorted(services.registry.list(), key=lambda d: d.received_at, reverse=True)[:25]
        return render(
            "dashboard.html",
            request,
            metrics=metrics,
            gaps={m.key: closed_via_gap(m) for m in metrics.areas},
            pending=pending,
            recent=recent,
            areas={a.key: a for a in services.areas},
        )

    @app.get("/cards", response_class=HTMLResponse)
    def cards(request: Request):
        if redirect := gate(request):
            return redirect
        pending = sorted(
            services.registry.list(status=DemandStatus.AWAITING_VALIDATION),
            key=lambda d: d.received_at,
        )
        return render(
            "cards.html", request, pending=pending, areas={a.key: a for a in services.areas}
        )

    @app.get("/cards/{demand_id}", response_class=HTMLResponse)
    def card(request: Request, demand_id: str, outcome: str = ""):
        if redirect := gate(request):
            return redirect
        demand = services.registry.get(demand_id)
        if not demand:
            return HTMLResponse("Demand not found.", status_code=404)
        area = services.area(demand.area)
        return render(
            "card.html",
            request,
            demand=demand,
            area=area,
            outcome=outcome,
            complexities=[
                (c.value, c.value.capitalize(), area.deadline_scale[c])
                for c in (Complexity.URGENT, Complexity.LOW, Complexity.MEDIUM, Complexity.HIGH)
            ],
            not_identified=NOT_IDENTIFIED,
            default_by=user_of(request)
            or (demand.card_recipients[0] if demand.card_recipients else ""),
        )

    @app.post("/cards/{demand_id}")
    def submit_card(
        request: Request,
        demand_id: str,
        action: str = Form(...),
        validated_by: str = Form(""),
        client: str = Form(""),
        client_other: str = Form(""),
        work_type: str = Form(""),
        lawyer: str = Form(""),
        complexity: str = Form(""),
        days: int | None = Form(None),
        reviewer: str = Form(""),
        review_days: int = Form(0),
        reply: str = Form(""),
    ):
        if redirect := gate(request):
            return redirect
        by = (user_of(request) or validated_by).strip().lower()
        if not by or not settings.is_internal(by):
            return RedirectResponse(f"/cards/{demand_id}?outcome=who", status_code=303)
        decision = Decision(
            demand_id=demand_id,
            action="approve" if action == "approve" else "discard",
            validated_by=by,
            client=client_other.strip() or client or None,
            work_type=work_type or None,
            lawyer=lawyer or None,
            complexity=Complexity(complexity) if complexity else None,
            days=days,
            reply=reply if reply.strip() else None,
            reviewer=reviewer or None,
            review_days=review_days or 0,
        )
        try:
            outcome = decide(services, decision)
        except DecisionError as exc:
            return RedirectResponse(f"/cards/{demand_id}?outcome=error:{exc}", status_code=303)
        code = (
            "already"
            if outcome.already_decided
            else ("discarded" if outcome.demand.status == DemandStatus.DISCARDED else "approved")
        )
        return RedirectResponse(f"/cards/{demand_id}?outcome={code}", status_code=303)

    @app.post("/api/decisions")
    async def api_decision(request: Request):
        """What the Outlook card posts (Action.Http). Authenticated by a bearer secret here;
        a production deployment validates the Entra token the card carries (docs)."""
        auth = (
            request.headers.get("action-authorization")
            or request.headers.get("authorization")
            or ""
        )
        if not settings.console_secret or not hmac.compare_digest(
            auth, f"Bearer {settings.console_secret}"
        ):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        body = await request.json()
        try:
            decision = Decision.model_validate(body)
            outcome = decide(services, decision)
        except (DecisionError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if outcome.already_decided:
            text = f"This demand was already decided by {outcome.demand.validated_by}. Nothing changed."
        else:
            verb = "discarded" if outcome.demand.status == DemandStatus.DISCARDED else "approved"
            text = f"Demand {verb} by {outcome.demand.validated_by}."
        card = {
            "type": "AdaptiveCard",
            "version": "1.0",
            "body": [{"type": "TextBlock", "text": text, "weight": "Bolder", "wrap": True}],
        }
        return JSONResponse(card, headers={"CARD-UPDATE-IN-BODY": "true"})

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "demo_mode": settings.demo_mode,
            "dry_run": settings.dry_run,
            "areas": [a.key for a in services.areas],
            "registry": services.registry.kind,
            "board": services.board.kind,
            "mailbox": services.mailbox.kind,
            "mailer": services.mailer.kind,
            "triager": services.triager.kind,
        }

    return app
