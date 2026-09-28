"""The intake mailbox and the sender through Microsoft Graph (application permissions
Mail.Read and Mail.ReadWrite on the intake account, Mail.Send on the area mailboxes)."""

from __future__ import annotations

from datetime import datetime

from ..graph import GraphClient
from ..models import InboundMessage


class GraphMailbox:
    kind = "graph"

    def __init__(self, graph: GraphClient, mailbox: str) -> None:
        self.graph, self.mailbox = graph, mailbox

    def recent_messages(self, since: datetime) -> list[InboundMessage]:
        items = self.graph.get_paged(
            f"/users/{self.mailbox}/mailFolders/inbox/messages",
            {
                "$filter": f"receivedDateTime ge {since.astimezone().isoformat()}",
                "$select": "id,conversationId,subject,from,toRecipients,ccRecipients,"
                "receivedDateTime,webLink,hasAttachments,body",
                "$orderby": "receivedDateTime asc",
                "$top": "50",
            },
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        out = []
        for m in items:
            out.append(
                InboundMessage(
                    id=m["id"],
                    conversation_id=m.get("conversationId") or m["id"],
                    sender=((m.get("from") or {}).get("emailAddress") or {})
                    .get("address", "")
                    .lower(),
                    to=[r["emailAddress"]["address"].lower() for r in m.get("toRecipients", [])],
                    cc=[r["emailAddress"]["address"].lower() for r in m.get("ccRecipients", [])],
                    subject=m.get("subject") or "",
                    body=(m.get("body") or {}).get("content", ""),
                    received_at=datetime.fromisoformat(
                        m["receivedDateTime"].replace("Z", "+00:00")
                    ),
                    web_link=m.get("webLink") or "",
                    has_attachments=bool(m.get("hasAttachments")),
                )
            )
        return out


class GraphMailer:
    kind = "graph"

    def __init__(self, graph: GraphClient, intake_mailbox: str) -> None:
        self.graph, self.intake_mailbox = graph, intake_mailbox

    def send(
        self,
        *,
        sender: str,
        to: list[str],
        subject: str,
        body_html: str,
        cc: list[str] | None = None,
    ) -> str:
        self.graph.post(
            f"/users/{sender}/sendMail",
            {
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": body_html},
                    "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                    "ccRecipients": [{"emailAddress": {"address": a}} for a in (cc or [])],
                },
                "saveToSentItems": True,
            },
        )
        return "sent"

    def reply_in_thread(self, message: InboundMessage, *, to: list[str], body_html: str) -> str:
        """The card as a reply in the demand's own conversation: create the reply draft,
        replace its recipients (so the client never receives the card) and send it."""
        draft = self.graph.post(
            f"/users/{self.intake_mailbox}/messages/{message.id}/createReply", {}
        )
        self.graph.patch(
            f"/users/{self.intake_mailbox}/messages/{draft['id']}",
            {
                "body": {"contentType": "html", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": a}} for a in to],
                "ccRecipients": [],
            },
        )
        self.graph.post(f"/users/{self.intake_mailbox}/messages/{draft['id']}/send", {})
        return draft["id"]
