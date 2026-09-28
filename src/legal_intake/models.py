"""The data that crosses the boundaries: the inbound message, the decision package the
model prepares, the decision a person takes, the demand as the registry keeps it and the
task as the board keeps it."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

NOT_IDENTIFIED = "Not identified"
DUE_DATE_MARKER = "[DUE_DATE]"


class Channel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    PHONE = "phone"
    MEETING = "meeting"
    OTHER = "other"


class Complexity(StrEnum):
    URGENT = "urgent"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InboundMessage(BaseModel):
    """An e-mail as the mailbox delivers it. `conversation_id` threads replies together."""

    id: str
    conversation_id: str
    sender: str
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str
    body: str
    received_at: datetime
    web_link: str = ""
    has_attachments: bool = False

    @property
    def recipients(self) -> list[str]:
        return [r.lower() for r in self.to + self.cc]


class TriagePackage(BaseModel):
    """What the model prepares and the person decides on. Every field is a suggestion."""

    client: str = Field(
        description="Name exactly as in the area's client directory, or 'Not identified'"
    )
    client_confidence: Confidence = Field(
        description="high = exact match in the directory; medium = inferred from the text or the domain; low = a guess"
    )
    work_type: str = Field(description="One slug of the area's taxonomy")
    summary: str = Field(description="Up to three sentences that spare re-reading the thread")
    suggested_lawyer: str = Field(
        description="Name exactly as in the area's lawyer list, or 'Not identified'"
    )
    lawyer_rationale: str = Field(
        description="One sentence: the rule of the directory or the criterion used"
    )
    complexity: Complexity = Field(
        description="urgent, low, medium or high; the area's scale turns it into business days"
    )
    suggested_days: int = Field(
        description="Business days from the complexity scale, reduced when the text carries a shorter explicit deadline"
    )
    explicit_deadline: str = Field(
        description="A deadline or date mentioned in the demand, or 'Not identified'"
    )
    reply_draft: str = Field(
        description=(
            "A short acknowledgement to the client in the firm's tone, in Portuguese, with the"
            " literal marker [DUE_DATE] where the return date goes"
        )
    )


class DemandStatus(StrEnum):
    AWAITING_VALIDATION = "awaiting_validation"
    IN_EXECUTION = "in_execution"
    DONE = "done"
    DISCARDED = "discarded"


class ClosedVia(StrEnum):
    EMAIL = "email"
    BOARD = "board"
    MANUAL = "manual"


class Demand(BaseModel):
    """One row of the master record. The `ai_*` fields never change after triage; the
    `final_*` fields are the decision; the difference is the adjustment rate."""

    id: str
    area: str
    subject: str
    channel: Channel
    sender: str
    conversation_id: str
    message_id: str
    web_link: str = ""
    received_at: datetime
    status: DemandStatus = DemandStatus.AWAITING_VALIDATION
    forwarded_by: str | None = None
    card_recipients: list[str] = Field(default_factory=list)

    ai_client: str = NOT_IDENTIFIED
    ai_client_confidence: Confidence = Confidence.LOW
    ai_work_type: str = "other"
    ai_summary: str = ""
    ai_lawyer: str = NOT_IDENTIFIED
    ai_lawyer_rationale: str = ""
    ai_complexity: Complexity = Complexity.LOW
    ai_days: int = 3
    ai_explicit_deadline: str = NOT_IDENTIFIED
    ai_reply_draft: str = ""
    triage_model: str = ""
    triage_notes: list[str] = Field(default_factory=list)

    final_client: str | None = None
    final_work_type: str | None = None
    final_lawyer: str | None = None
    final_complexity: Complexity | None = None
    final_days: int | None = None
    final_reply: str | None = None
    reviewer: str | None = None
    review_days: int = 0
    validated_by: str | None = None
    decided_at: datetime | None = None
    adjusted: bool | None = None
    due_date: date | None = None

    board_task_id: str | None = None
    reply_sent_to: str | None = None
    replied_at: datetime | None = None
    closed_via: ClosedVia | None = None
    closed_at: datetime | None = None


class Decision(BaseModel):
    """What the card returns. Empty fields mean 'keep the suggestion'."""

    demand_id: str
    action: str = Field(pattern="^(approve|discard)$")
    validated_by: str
    client: str | None = None
    work_type: str | None = None
    lawyer: str | None = None
    complexity: Complexity | None = None
    days: int | None = None
    reply: str | None = None
    reviewer: str | None = None
    review_days: int = 0


class Task(BaseModel):
    """A task on the board (Planner in production, SQLite in the demo)."""

    id: str
    plan: str
    bucket: str
    title: str
    assignee: str | None
    due_date: date | None
    created_at: datetime
    completed_at: datetime | None = None
    percent_complete: int = 0
    label: str | None = None
    description: str = ""
    checklist: list[str] = Field(default_factory=list)
    demand_id: str | None = None
