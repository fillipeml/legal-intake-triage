"""The decision: what a person's approval does. Idempotent (the first decision wins, the
second is told who decided), and everything after the click is deterministic: the due date
in business days, the task in the client's bucket with the type's label and checklist, the
registry row with the suggested and the final fields, and the reply to the original sender
only, in the modes the area allows."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime

from ..areas import Area
from ..business_days import add_business_days, date_br
from ..clock import now
from ..filters import is_forms_subject
from ..models import DUE_DATE_MARKER, NOT_IDENTIFIED, Channel, Decision, Demand, DemandStatus
from ..services import Services


class DecisionError(ValueError):
    pass


@dataclass
class DecisionOutcome:
    demand: Demand
    already_decided: bool = False
    task_id: str | None = None
    reply: str | None = None  # "sent to x" | "draft to team mailbox" | "not sent: reason"

    def line(self) -> str:
        if self.already_decided:
            return f"{self.demand.id}: already decided by {self.demand.validated_by}"
        if self.demand.status == DemandStatus.DISCARDED:
            return f"{self.demand.id}: discarded by {self.demand.validated_by}"
        return (
            f"{self.demand.id}: approved by {self.demand.validated_by} -> task {self.task_id}"
            f" due {self.demand.due_date} ({self.reply})"
        )


def effective_days(area: Area, demand: Demand, decision: Decision, complexity) -> int:
    """The person's number when they changed it; otherwise the scale of the final complexity
    (in areas where complexity does not set the deadline, the suggestion stands)."""
    if decision.days is not None and decision.days != demand.ai_days:
        base = decision.days
    elif area.complexity_sets_deadline:
        base = area.deadline_scale[complexity]
    else:
        base = decision.days if decision.days is not None else demand.ai_days
    return max(1, base)


def decide(
    services: Services, decision: Decision, *, moment: datetime | None = None
) -> DecisionOutcome:
    settings, registry, board = services.settings, services.registry, services.board
    at = moment or now(settings)
    demand = registry.get(decision.demand_id)
    if demand is None:
        raise DecisionError(f"demand {decision.demand_id} not found")
    if demand.status != DemandStatus.AWAITING_VALIDATION:
        return DecisionOutcome(demand=demand, already_decided=True)
    area = services.area(demand.area)

    client = (decision.client or demand.ai_client).strip() or NOT_IDENTIFIED
    work_type_slug = decision.work_type or demand.ai_work_type
    if area.work_type(work_type_slug) is None:
        raise DecisionError(f"work type '{work_type_slug}' is not in the taxonomy of {area.name}")
    lawyer = decision.lawyer or demand.ai_lawyer
    if lawyer != NOT_IDENTIFIED and area.lawyer_by_name(lawyer) is None:
        raise DecisionError(f"'{lawyer}' is not a lawyer of {area.name}")
    complexity = decision.complexity or demand.ai_complexity
    reviewer = decision.reviewer or None
    if reviewer and reviewer not in area.internal_review.reviewers:
        raise DecisionError(f"'{reviewer}' is not a reviewer of {area.name}")
    review_days = max(0, decision.review_days) if reviewer else 0
    days = effective_days(area, demand, decision, complexity)
    reply_text = decision.reply if decision.reply is not None else demand.ai_reply_draft

    demand.final_client, demand.final_work_type, demand.final_lawyer = (
        client,
        work_type_slug,
        lawyer,
    )
    demand.final_complexity, demand.final_days, demand.final_reply = complexity, days, reply_text
    demand.reviewer, demand.review_days = reviewer, review_days
    demand.validated_by, demand.decided_at = decision.validated_by.lower(), at
    demand.adjusted = any(
        [
            client != demand.ai_client,
            work_type_slug != demand.ai_work_type,
            lawyer != demand.ai_lawyer,
            complexity != demand.ai_complexity,
            days != demand.ai_days,
        ]
    )

    if decision.action == "discard":
        demand.status = DemandStatus.DISCARDED
        registry.update(demand)
        return DecisionOutcome(demand=demand)

    due = add_business_days(at.date(), days + review_days, settings.holiday_subdivision)
    demand.due_date = due
    work_type = area.work_type(work_type_slug)
    bucket_name = client if client != NOT_IDENTIFIED else area.board.fallback_bucket
    bucket = (
        board.ensure_bucket(area.board.plan, bucket_name)
        if area.board.create_buckets
        else bucket_name
    )
    reply_with_date = reply_text.replace(DUE_DATE_MARKER, date_br(due))
    description = ""
    if reviewer:
        description += f"INTERNAL REVIEW: {reviewer} — {review_days} business day(s) added to the client's deadline.\n\n"
    description += (
        f"{demand.ai_summary}\n\nSUGGESTED REPLY TO THE CLIENT:\n{reply_with_date}"
        f"\n\nOriginal e-mail: {demand.web_link or demand.message_id}"
    )
    task = board.create_task(
        plan=area.board.plan,
        bucket=bucket,
        title=f"[{client}] {work_type.title} — {demand.subject}",
        assignee=lawyer if lawyer != NOT_IDENTIFIED else None,
        due_date=due,
        description=description,
        checklist=work_type.checklist,
        label=work_type.label,
        demand_id=demand.id,
        created_at=at,
    )
    demand.board_task_id = task.id
    demand.status = DemandStatus.IN_EXECUTION

    reply = _reply_to_client(services, area, demand, reply_with_date)
    registry.update(demand)
    return DecisionOutcome(demand=demand, task_id=task.id, reply=reply)


def _reply_to_client(services: Services, area: Area, demand: Demand, body: str) -> str:
    """The acknowledgement: never for a forwarded demand or a form (the lawyer already talks
    to the client), never to an address the model chose, and only in the area's mode."""
    if area.reply_mode == "none":
        return "not sent: the area does not reply automatically"
    if demand.channel != Channel.EMAIL or demand.forwarded_by or is_forms_subject(demand.subject):
        return "not sent: forwarded or registered by the team"
    html_body = "<p>" + html.escape(body).replace("\n", "<br>") + "</p>"
    if area.reply_mode == "send":
        services.mailer.send(
            sender=area.mailbox,
            to=[demand.sender],
            subject=f"RE: {demand.subject}",
            body_html=html_body,
        )
        demand.reply_sent_to = demand.sender
        return f"sent to {demand.sender}"
    services.mailer.send(
        sender=area.mailbox,
        to=[area.mailbox],
        subject=f"[DRAFT for review] RE: {demand.subject}",
        body_html=html_body,
    )
    return f"draft to {area.mailbox}"
