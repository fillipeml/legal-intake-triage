"""The sweep: every message of the intake mailbox since the lookback, routed, filtered,
deduplicated, triaged, recorded and sent as a card. Idempotent: a processed message id is
never handled twice, and a conversation already registered never becomes a second demand."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..areas import area_for
from ..cards import build_card, card_html, card_recipients
from ..clock import now
from ..filters import clean_body, route_message
from ..models import Demand, DemandStatus
from ..services import Services
from ..triage.checks import check_package
from ..triage.types import TriageInput
from ..workload import current_load
from .closing import try_close_by_reply

logger = logging.getLogger(__name__)


@dataclass
class SweepSummary:
    messages: int = 0
    already_processed: int = 0
    skipped: list[str] = field(default_factory=list)
    duplicates: int = 0
    closed: list[str] = field(default_factory=list)
    registered: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"messages={self.messages} already_processed={self.already_processed} skipped={len(self.skipped)} "
            f"duplicates={self.duplicates} closed={len(self.closed)} registered={len(self.registered)} failed={len(self.failed)}"
        )


def sweep(services: Services, *, moment: datetime | None = None) -> SweepSummary:
    settings = services.settings
    at = moment or now(settings)
    since = at - timedelta(days=settings.sweep_lookback_days)
    summary = SweepSummary()

    for message in services.mailbox.recent_messages(since):
        summary.messages += 1
        if services.registry.message_processed(message.id):
            summary.already_processed += 1
            continue
        try:
            _handle(services, message, at, summary)
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the sweep
            logger.exception("message %s failed", message.id)
            summary.failed.append(f"{message.subject}: {exc}")
            services.registry.record_message(
                message.id, result=f"failed: {exc}", received_at=message.received_at
            )
    return summary


def _handle(services: Services, message, at: datetime, summary: SweepSummary) -> None:
    settings, registry = services.settings, services.registry

    def done(result: str) -> None:
        registry.record_message(message.id, result=result, received_at=message.received_at)

    area = area_for(services.areas, message.recipients)
    if area is None:
        # not addressed to an area: only a closing reply copied to the intake account matters
        closed = try_close_by_reply(services, message, at)
        if closed:
            summary.closed.append(closed)
            done(f"closed: {closed}")
        else:
            summary.skipped.append(f"{message.subject}: not addressed to an area")
            done("skipped: not addressed to an area")
        return

    route = route_message(
        message.sender,
        message.subject,
        is_internal=settings.is_internal(message.sender),
        is_intake_account=message.sender.lower() == settings.intake_mailbox.lower(),
    )
    if route.kind == "skip":
        summary.skipped.append(f"{message.subject}: {route.skip}")
        done(f"skipped: {route.skip}")
        return
    if route.kind == "closing_candidate":
        closed = try_close_by_reply(services, message, at)
        if closed:
            summary.closed.append(closed)
            done(f"closed: {closed}")
        else:
            summary.skipped.append(f"{message.subject}: {route.skip}")
            done(f"skipped: {route.skip}")
        return

    existing = registry.by_conversation(message.conversation_id)
    if existing:
        closed = (
            try_close_by_reply(services, message, at)
            if settings.is_internal(message.sender)
            else None
        )
        if closed:
            summary.closed.append(closed)
            done(f"closed: {closed}")
        else:
            summary.duplicates += 1
            done(f"duplicate: reply in the thread of {existing.id}")
        return

    body = clean_body(message.body, settings.max_body_chars)
    load = current_load(services.board, area)
    item = TriageInput(
        message=message, area=area, body=body, forwarded_by=route.forwarded_by, load=load
    )
    output = services.triager.triage(item)
    package, notes = check_package(
        output.package,
        area,
        forwarded_by=route.forwarded_by,
        load=load,
        firm_name=settings.firm_name,
    )

    demand = Demand(
        id=f"d-{hashlib.sha1(message.id.encode()).hexdigest()[:8]}",
        area=area.key,
        subject=message.subject,
        channel=route.channel,
        sender=message.sender.lower(),
        conversation_id=message.conversation_id,
        message_id=message.id,
        web_link=message.web_link,
        received_at=message.received_at,
        status=DemandStatus.AWAITING_VALIDATION,
        forwarded_by=route.forwarded_by,
        ai_client=package.client,
        ai_client_confidence=package.client_confidence,
        ai_work_type=package.work_type,
        ai_summary=package.summary,
        ai_lawyer=package.suggested_lawyer,
        ai_lawyer_rationale=package.lawyer_rationale,
        ai_complexity=package.complexity,
        ai_days=package.suggested_days,
        ai_explicit_deadline=package.explicit_deadline,
        ai_reply_draft=package.reply_draft,
        triage_model=output.model,
        triage_notes=notes,
    )
    demand.card_recipients = card_recipients(
        area,
        settings,
        sender=message.sender,
        subject=message.subject,
        client_name=package.client,
        forwarded_by=route.forwarded_by,
    )
    registry.create(demand)

    card = build_card(demand, area)
    ref = services.mailer.reply_in_thread(
        message, to=demand.card_recipients, body_html=card_html(card, demand, services.console_url)
    )
    summary.registered.append(demand.id)
    summary.cards.append(
        {"demand": demand.id, "to": demand.card_recipients, "ref": ref, "subject": message.subject}
    )
    logger.info(
        "registered %s (%s) -> card to %s",
        demand.id,
        message.subject,
        ", ".join(demand.card_recipients),
    )
    done(f"registered: {demand.id}")
