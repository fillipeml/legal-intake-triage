"""The decision card: an Adaptive Card with the package pre-filled in editable fields, sent
as a reply in the demand's own thread to the people who decide, plus the HTML fallback
with a link to the console. Who receives it is a rule, not a model output, and the
recipients are internal by construction."""

from __future__ import annotations

import html
import json

from .areas import Area
from .config import Settings
from .filters import forms_responder, is_forms_subject
from .models import NOT_IDENTIFIED, Complexity, Demand

COMPLEXITY_TITLES = {
    Complexity.URGENT: "Urgent",
    Complexity.LOW: "Low",
    Complexity.MEDIUM: "Medium",
    Complexity.HIGH: "High",
}


def card_recipients(
    area: Area,
    settings: Settings,
    *,
    sender: str,
    subject: str,
    client_name: str,
    forwarded_by: str | None,
) -> list[str]:
    """heads: the client's lead, else the heads (the first answer decides).
    forwarder: whoever forwarded (a lawyer of the area, or the form's responder); anyone
    else, including an external sender writing straight to the list, goes to the head."""
    if area.validation == "forwarder":
        candidate = (
            forms_responder(subject)
            if is_forms_subject(subject)
            else (forwarded_by or sender.lower())
        )
        if candidate and candidate in area.lawyer_emails():
            return [candidate]
        return [area.heads[0]]
    if is_forms_subject(subject):
        responder = forms_responder(subject)
        # A lawyer of the area, not merely someone on the firm's domain: an intern who
        # registers a demand through the form would otherwise become the sole recipient
        # of the decision card, and the area's heads would never see it.
        if responder and responder in area.lawyer_emails():
            return [responder]
    client = area.client_by_name(client_name) if client_name != NOT_IDENTIFIED else None
    if client and client.lead:
        lead = area.lawyer_by_name(client.lead)
        if lead:
            return [lead.email]
    return list(area.heads)


def build_card(demand: Demand, area: Area) -> dict:
    """The Adaptive Card (schema 1.4). Inputs carry the suggestion as the default value."""
    work_type = area.work_type(demand.ai_work_type)
    facts = [
        {
            "title": "Client",
            "value": f"{demand.ai_client} (confidence: {demand.ai_client_confidence})",
        },
        {"title": "Type", "value": work_type.title if work_type else demand.ai_work_type},
        {"title": "Complexity", "value": COMPLEXITY_TITLES[demand.ai_complexity]},
        {"title": "Deadline in the text", "value": demand.ai_explicit_deadline},
        {"title": "Channel", "value": demand.channel.value},
        {"title": "Sender", "value": demand.forwarded_by or demand.sender},
    ]
    body: list[dict] = [
        {
            "type": "Container",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"New demand — {area.name}",
                    "weight": "Bolder",
                    "size": "Medium",
                    "color": "Accent",
                },
                {"type": "TextBlock", "text": demand.subject, "wrap": True, "weight": "Bolder"},
            ],
        },
        {"type": "FactSet", "facts": facts},
        {"type": "TextBlock", "text": "Summary", "weight": "Bolder", "spacing": "Medium"},
        {"type": "TextBlock", "text": demand.ai_summary, "wrap": True},
        {
            "type": "TextBlock",
            "text": f"Suggested lawyer: {demand.ai_lawyer_rationale}",
            "wrap": True,
            "isSubtle": True,
            "size": "Small",
        },
    ]
    if demand.triage_notes:
        body.append(
            {
                "type": "TextBlock",
                "text": "Checks: " + " · ".join(demand.triage_notes),
                "wrap": True,
                "isSubtle": True,
                "size": "Small",
            }
        )
    body += [
        {
            "type": "Input.ChoiceSet",
            "id": "client",
            "label": "Client",
            "value": demand.ai_client,
            "choices": [{"title": c.name, "value": c.name} for c in area.clients]
            + [{"title": NOT_IDENTIFIED, "value": NOT_IDENTIFIED}],
        },
        {
            "type": "Input.Text",
            "id": "client_other",
            "label": "Client not listed (type the name)",
            "placeholder": "leave empty to keep the choice above",
        },
        {
            "type": "Input.ChoiceSet",
            "id": "work_type",
            "label": "Work type",
            "value": demand.ai_work_type,
            "choices": [{"title": t.title, "value": t.slug} for t in area.taxonomy],
        },
        {
            "type": "Input.ChoiceSet",
            "id": "lawyer",
            "label": "Responsible lawyer",
            "value": demand.ai_lawyer,
            "choices": [{"title": lw.name, "value": lw.name} for lw in area.lawyers],
        },
        {
            "type": "Input.ChoiceSet",
            "id": "complexity",
            "label": "Complexity"
            + (" (sets the deadline)" if area.complexity_sets_deadline else ""),
            "value": demand.ai_complexity.value,
            "choices": [
                {
                    "title": f"{COMPLEXITY_TITLES[c]}"
                    + (
                        f" ({area.deadline_scale[c]} business day{'s' if area.deadline_scale[c] != 1 else ''})"
                        if area.complexity_sets_deadline
                        else ""
                    ),
                    "value": c.value,
                }
                for c in (Complexity.URGENT, Complexity.LOW, Complexity.MEDIUM, Complexity.HIGH)
            ],
        },
        {
            "type": "Input.Number",
            "id": "days",
            "label": "Deadline for the client (business days)",
            "value": demand.ai_days,
        },
    ]
    if area.internal_review.enabled:
        body += [
            {
                "type": "Input.ChoiceSet",
                "id": "reviewer",
                "label": "Internal review",
                "value": "",
                "choices": [{"title": "No review", "value": ""}]
                + [{"title": r, "value": r} for r in area.internal_review.reviewers],
            },
            {
                "type": "Input.Number",
                "id": "review_days",
                "label": "Internal deadline (business days, added to the client's)",
                "value": 0,
            },
        ]
    if area.reply_mode != "none":
        body.append(
            {
                "type": "Input.Text",
                "id": "reply",
                "label": "Reply to the client",
                "isMultiline": True,
                "value": demand.ai_reply_draft,
            }
        )
    body.append(
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Approve",
                    "style": "positive",
                    "data": {"action": "approve", "demand_id": demand.id, "area": area.key},
                },
                {
                    "type": "Action.Submit",
                    "title": "Discard",
                    "style": "destructive",
                    "data": {"action": "discard", "demand_id": demand.id, "area": area.key},
                },
            ],
        }
    )
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }


def card_html(card: dict, demand: Demand, console_url: str) -> str:
    """The e-mail body: the card for clients that render it, a text fallback with the
    console link for the others."""
    fallback = (
        f"<p><b>New demand awaiting validation</b> — {html.escape(demand.subject)}</p>"
        f"<p>{html.escape(demand.ai_summary)}</p>"
        f"<p>Client: {html.escape(demand.ai_client)} · Type: {html.escape(demand.ai_work_type)} · "
        f"Complexity: {demand.ai_complexity.value} · {demand.ai_days} business day(s) · "
        f"Lawyer: {html.escape(demand.ai_lawyer)}</p>"
        f'<p><a href="{html.escape(console_url)}/cards/{demand.id}">Decide in the console</a>'
        " (open in Outlook to decide here).</p>"
    )
    # Escape "</" so sender-controlled text cannot close the script element it is
    # embedded in. Subject, summary and client name are all copied into the card from
    # the incoming e-mail, so "</script><img src=x onerror=...>" in a subject line was
    # enough to break out. JSON treats \/ as /, so the card is unchanged.
    payload = json.dumps(card, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<html><head><script type="application/adaptivecard+json">'
        f"{payload}</script></head><body>{fallback}</body></html>"
    )
