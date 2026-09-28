"""The mailbox the intake reads and the mailer that sends the cards and the replies."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol

from ..models import InboundMessage

logger = logging.getLogger(__name__)


class Mailbox(Protocol):
    kind: str

    def recent_messages(self, since: datetime) -> list[InboundMessage]: ...


class Mailer(Protocol):
    kind: str

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_html: str,
        cc: list[str] | None = None,
    ) -> str: ...
    def reply_in_thread(self, message: InboundMessage, *, to: list[str], body_html: str) -> str: ...


class DryRunMailer:
    """Logs what would go out and sends nothing (shadow mode of a real deployment)."""

    kind = "dry-run"

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_html: str,
        cc: list[str] | None = None,
    ) -> str:
        logger.info("[DRY RUN] would send '%s' from %s to %s", subject, sender, ", ".join(to))
        return "dry-run"

    def reply_in_thread(self, message: InboundMessage, *, to: list[str], body_html: str) -> str:
        logger.info(
            "[DRY RUN] would reply in the thread of '%s' to %s", message.subject, ", ".join(to)
        )
        return "dry-run"
