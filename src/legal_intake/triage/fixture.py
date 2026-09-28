"""Recorded readings of the fixture inbox, keyed by message id; a message without a
recording falls back to the rules-based triager, and the output says which one answered."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import TriagePackage
from .rules import RuleTriager
from .types import TriageInput, TriageOutput


class FixtureTriager:
    kind = "fixture"

    def __init__(
        self, recordings: dict[str, dict] | Path, fallback: RuleTriager | None = None
    ) -> None:
        if isinstance(recordings, Path):
            recordings = json.loads(recordings.read_text(encoding="utf-8"))
        self.recordings = recordings
        self.fallback = fallback or RuleTriager()

    def triage(self, item: TriageInput) -> TriageOutput:
        raw = self.recordings.get(item.message.id)
        if raw is None:
            out = self.fallback.triage(item)
            return TriageOutput(package=out.package, model="rules (no recording)")
        return TriageOutput(
            package=TriagePackage.model_validate(raw), model=f"fixture:{item.message.id}"
        )
