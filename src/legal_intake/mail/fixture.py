"""Demo adapters: an inbox read from a JSON file, and a mailer that writes every e-mail to
a folder, so the cards and the replies can be read as the recipients would."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..models import InboundMessage


class FixtureInbox:
    kind = "fixture"

    def __init__(self, path: Path) -> None:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.messages = [InboundMessage.model_validate(m) for m in raw["messages"]]

    def recent_messages(self, since: datetime) -> list[InboundMessage]:
        return sorted(
            (m for m in self.messages if m.received_at >= since), key=lambda m: m.received_at
        )


class OutboxMailer:
    kind = "outbox"

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sent: list[dict] = []

    def _write(
        self,
        kind: str,
        *,
        sender: str,
        to: list[str],
        cc: list[str],
        subject: str,
        body_html: str,
        thread: str = "",
    ) -> str:
        n = len(list(self.directory.glob("*.html"))) + 1
        safe = re.sub(r"[^A-Za-z0-9]+", "-", subject).strip("-")[:70]
        path = self.directory / f"{n:03d}-{kind}-{safe}.html"
        header = (
            f"<!-- {kind}\nFrom: {sender}\nTo: {', '.join(to)}\nCc: {', '.join(cc)}\nSubject: {subject}\n"
            f"Thread: {thread}\n-->\n"
        )
        path.write_text(header + body_html, encoding="utf-8")
        self.sent.append(
            {
                "kind": kind,
                "from": sender,
                "to": to,
                "cc": cc,
                "subject": subject,
                "file": path.name,
                "thread": thread,
            }
        )
        return path.name

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_html: str,
        cc: list[str] | None = None,
    ) -> str:
        return self._write(
            "mail", sender=sender, to=to, cc=cc or [], subject=subject, body_html=body_html
        )

    def reply_in_thread(self, message: InboundMessage, *, to: list[str], body_html: str) -> str:
        return self._write(
            "card",
            sender="intake",
            to=to,
            cc=[],
            subject=f"RE: {message.subject}",
            body_html=body_html,
            thread=message.conversation_id,
        )
