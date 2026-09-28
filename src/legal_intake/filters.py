"""The noise filters and the routes of an inbound message, decided before any model call.

The original flow's rules, in code: internal senders are ignored unless they are
registering a demand (a forward, or the e-mail a form sends); auto-generated senders
and auto-replies are ignored; the channel comes from the form's subject."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Channel

FORWARD_PREFIXES = ("enc:", "fw:", "fwd:", "res:", "re: enc:", "re: fw:")
FORMS_PREFIX = "[forms/"
AUTO_SENDER_MARKERS = ("noreply", "no-reply", "mailer-daemon", "postmaster", "donotreply")
AUTO_REPLY_PREFIXES = (
    "resposta automática",
    "automatic reply",
    "out of office",
    "undeliverable",
    "ausência",
    "auto:",
)
_CHANNELS = {
    "whatsapp": Channel.WHATSAPP,
    "telefone": Channel.PHONE,
    "phone": Channel.PHONE,
    "reunião": Channel.MEETING,
    "reuniao": Channel.MEETING,
    "meeting": Channel.MEETING,
}


def is_forwarded_subject(subject: str) -> bool:
    return subject.strip().lower().startswith(FORWARD_PREFIXES)


def is_forms_subject(subject: str) -> bool:
    return subject.strip().lower().startswith(FORMS_PREFIX)


def channel_of(subject: str) -> Channel:
    """`[Forms/WhatsApp] Demand registered by ...` -> whatsapp; anything else is e-mail."""
    m = re.match(r"^\s*\[forms/([^\]]+)\]", subject, flags=re.I)
    if not m:
        return Channel.EMAIL
    return _CHANNELS.get(m.group(1).strip().lower(), Channel.OTHER)


def forms_responder(subject: str) -> str | None:
    """The form's e-mail ends with the responder's address: that is who gets the card."""
    if not is_forms_subject(subject):
        return None
    last = subject.strip().split()[-1]
    return last.lower() if "@" in last else None


def is_auto_generated(sender: str) -> bool:
    local = sender.lower().split("@")[0]
    return any(marker in local for marker in AUTO_SENDER_MARKERS)


def is_auto_reply(subject: str) -> bool:
    return subject.strip().lower().startswith(AUTO_REPLY_PREFIXES)


@dataclass(frozen=True)
class Route:
    """Where a message goes. `skip` carries the reason when it goes nowhere."""

    kind: str  # demand | closing_candidate | skip
    skip: str = ""
    forwarded: bool = False
    channel: Channel = Channel.EMAIL
    forwarded_by: str | None = None


def route_message(
    sender: str, subject: str, *, is_internal: bool, is_intake_account: bool
) -> Route:
    """The route of a message addressed to an area.

    - auto-generated senders and auto-replies: skip;
    - an internal sender: a demand only when forwarding (subject prefix) or when it is the
      intake account relaying a form; otherwise a closing candidate (a reply in a thread)
      or noise;
    - an external sender: a demand.
    """
    if is_auto_generated(sender):
        return Route("skip", "auto-generated sender")
    if is_auto_reply(subject):
        return Route("skip", "automatic reply")
    if is_forms_subject(subject):
        if not is_internal and not is_intake_account:
            return Route("skip", "a form-shaped subject from an external sender")
        return Route(
            "demand",
            channel=channel_of(subject),
            forwarded=True,
            forwarded_by=forms_responder(subject),
        )
    if is_internal:
        if is_forwarded_subject(subject):
            return Route("demand", forwarded=True, forwarded_by=sender.lower())
        return Route("closing_candidate", "internal message that is not a forward")
    return Route("demand")


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"</p>|</div>", "\n\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>|</tr>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_body(body: str, max_chars: int) -> str:
    """Plain text, bounded: long e-mails rarely add to the triage."""
    text = strip_html(body) if "<" in body and ">" in body else body.strip()
    return text[:max_chars]
