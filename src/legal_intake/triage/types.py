from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..areas import Area
from ..models import InboundMessage, TriagePackage


@dataclass
class TriageInput:
    message: InboundMessage
    area: Area
    body: str  # the cleaned, bounded text
    forwarded_by: str | None
    load: dict[str, int] = field(default_factory=dict)  # open tasks per lawyer


@dataclass
class TriageOutput:
    package: TriagePackage
    model: str
    usage: dict[str, int] | None = None


class Triager(Protocol):
    kind: str

    def triage(self, item: TriageInput) -> TriageOutput: ...
