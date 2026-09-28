"""The configuration of a practice area: its mailbox, who validates, its taxonomy, its
lawyers and its client directory. One JSON file per area under `areas/`; the ones shipped
here are fictional."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import Complexity


class WorkType(BaseModel):
    slug: str
    title: str
    keywords: list[str] = Field(
        default_factory=list,
        description="Portuguese keywords for the rules-based classifier, most specific first",
    )
    label: str | None = Field(
        default=None, description="The board label (Planner category) applied on approval"
    )
    checklist: list[str] = Field(default_factory=list)


class Lawyer(BaseModel):
    name: str
    email: str
    receives_distribution: bool = True
    specialties: str = ""


class Client(BaseModel):
    name: str
    domains: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    owner: str | None = Field(
        default=None,
        description="The lawyer who holds the client's portfolio: rule number one of distribution",
    )
    lead: str | None = Field(
        default=None,
        description="The lawyer who validates this client's demands (falls back to the heads)",
    )

    def matches(self, email: str) -> bool:
        e = email.strip().lower()
        domain = e.split("@")[-1]
        return e in [x.lower() for x in self.emails] or domain in [
            d.lower().lstrip("@") for d in self.domains
        ]


class InternalReview(BaseModel):
    enabled: bool = False
    reviewers: list[str] = Field(default_factory=list)


class Board(BaseModel):
    plan: str
    fallback_bucket: str = "OTHERS"
    create_buckets: bool = True


class Area(BaseModel):
    key: str
    name: str
    mailbox: str = Field(description="The team's address")
    intake_address: str = Field(
        description="The address the sweep routes on (the team's mailbox, or a list that only the automation reads)"
    )
    validation: Literal["heads", "forwarder"] = Field(
        description="heads: the client's lead or the heads decide; forwarder: whoever forwarded the demand decides"
    )
    heads: list[str]
    reply_mode: Literal["draft", "send", "none"] = "draft"
    deadline_scale: dict[Complexity, int] = Field(
        default_factory=lambda: {
            Complexity.URGENT: 1,
            Complexity.LOW: 3,
            Complexity.MEDIUM: 5,
            Complexity.HIGH: 10,
        }
    )
    complexity_sets_deadline: bool = Field(
        default=True,
        description="false: the scale is only a suggestion and the person sets the deadline on the card",
    )
    internal_review: InternalReview = Field(default_factory=InternalReview)
    board: Board
    taxonomy: list[WorkType]
    lawyers: list[Lawyer]
    clients: list[Client] = Field(default_factory=list)
    sla_reference: dict[str, float] = Field(
        default_factory=dict,
        description="Historical median in business days per work type, from the SLA matrix; calibrates the prompt",
    )

    @model_validator(mode="after")
    def _consistent(self) -> Area:
        slugs = [t.slug for t in self.taxonomy]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"area {self.key}: duplicated work type slug")
        if "other" not in slugs:
            raise ValueError(
                f"area {self.key}: the taxonomy needs an 'other' type for what is not a demand"
            )
        names = {lw.name for lw in self.lawyers}
        for c in self.clients:
            for who in (c.owner, c.lead):
                if who and who not in names:
                    raise ValueError(
                        f"area {self.key}: client {c.name} names an unknown lawyer {who}"
                    )
        for r in self.internal_review.reviewers:
            if r not in names:
                raise ValueError(f"area {self.key}: unknown reviewer {r}")
        return self

    # --- lookups -------------------------------------------------------------------
    def work_type(self, slug: str) -> WorkType | None:
        return next((t for t in self.taxonomy if t.slug == slug), None)

    def lawyer_by_name(self, name: str) -> Lawyer | None:
        wanted = name.strip().lower()
        return next((lw for lw in self.lawyers if lw.name.lower() == wanted), None)

    def lawyer_by_email(self, email: str) -> Lawyer | None:
        wanted = email.strip().lower()
        return next((lw for lw in self.lawyers if lw.email.lower() == wanted), None)

    def client_for(self, email: str) -> Client | None:
        return next((c for c in self.clients if c.matches(email)), None)

    def client_by_name(self, name: str) -> Client | None:
        wanted = name.strip().lower()
        return next((c for c in self.clients if c.name.lower() == wanted), None)

    def distribution(self) -> list[Lawyer]:
        return [lw for lw in self.lawyers if lw.receives_distribution]

    def lawyer_emails(self) -> list[str]:
        return [lw.email.lower() for lw in self.lawyers]

    def is_area_address(self, recipients: list[str]) -> bool:
        wanted = self.intake_address.lower()
        return any(r.lower() == wanted for r in recipients)


def load_areas(directory: str | Path) -> list[Area]:
    root = Path(directory)
    areas = [
        Area.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(root.glob("*.json"))
    ]
    if not areas:
        raise FileNotFoundError(f"no area configuration found in {root}")
    return areas


def area_for(areas: list[Area], recipients: list[str]) -> Area | None:
    """The area whose intake address is among the recipients (the routing condition)."""
    return next((a for a in areas if a.is_area_address(recipients)), None)
