"""The SLA matrix: the standard deadline per (area, work type) from the board's history.

Completed tasks are classified in the taxonomy (by the keyword rules, offline, or by a
small model through the Message Batches API), their durations measured in business days,
and the median and the 80th percentile computed per type. The P80, rounded up, is the
proposed standard; rows with a thin sample are flagged for review. Recomputed quarterly,
validated by the heads, then pasted into the area's `sla_reference`."""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

from .areas import Area
from .business_days import business_days_between
from .models import Task
from .triage.rules import normalise

MIN_SAMPLE = 5


@dataclass
class HistoryRow:
    area: str
    title: str
    created: date
    completed: date
    work_type: str = ""

    @property
    def duration(self) -> int:
        return max(1, business_days_between(self.created, self.completed))


@dataclass
class MatrixRow:
    area: str
    work_type: str
    median_days: float
    p80_days: float
    standard_days: int
    sample: int
    review: bool


def classify_by_rules(title: str, area: Area) -> str:
    norm = normalise(title)
    for t in area.taxonomy:
        if any(normalise(k) in norm for k in t.keywords):
            return t.slug
    return "other"


def classify_by_batch(
    titles: list[str], area: Area, *, client: Any, model: str, poll_seconds: float = 30.0
) -> dict[str, str]:
    """Unique titles through the Message Batches API (half the price, no local load)."""
    unique = sorted(set(titles))
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["work_type"],
        "properties": {"work_type": {"type": "string", "enum": [t.slug for t in area.taxonomy]}},
    }
    taxonomy = "; ".join(f"{t.slug} = {t.title}" for t in area.taxonomy)
    batch = client.messages.batches.create(
        requests=[
            {
                "custom_id": f"t-{i}",
                "params": {
                    "model": model,
                    "max_tokens": 64,
                    "output_config": {"format": {"type": "json_schema", "schema": schema}},
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Classify this task title of a law firm's practice area in the"
                                f" taxonomy ({taxonomy}). Answer only the JSON.\n\nTitle: {title}"
                            ),
                        }
                    ],
                },
            }
            for i, title in enumerate(unique)
        ]
    )
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        time.sleep(poll_seconds)
    by_index: dict[int, str] = {}
    for result in client.messages.batches.results(batch.id):
        i = int(result.custom_id.split("-")[1])
        if result.result.type == "succeeded":
            text = next(b.text for b in result.result.message.content if b.type == "text")
            by_index[i] = json.loads(text).get("work_type", "other")
        else:
            by_index[i] = "other"
    return {title: by_index.get(i, "other") for i, title in enumerate(unique)}


def percentile(values: list[int], q: float) -> float:
    """Linear interpolation between order statistics (pandas' default)."""
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(s[lo])
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def build_matrix(rows: list[HistoryRow]) -> list[MatrixRow]:
    groups: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        groups.setdefault((r.area, r.work_type or "other"), []).append(r.duration)
    out = []
    for (area, work_type), durations in sorted(groups.items()):
        median = statistics.median(durations)
        p80 = percentile(durations, 0.8)
        out.append(
            MatrixRow(
                area=area,
                work_type=work_type,
                median_days=round(median, 1),
                p80_days=round(p80, 1),
                standard_days=max(1, math.ceil(p80)),
                sample=len(durations),
                review=len(durations) < MIN_SAMPLE,
            )
        )
    return out


def history_from_tasks(tasks: list[Task], area: Area) -> list[HistoryRow]:
    return [
        HistoryRow(
            area=area.key,
            title=t.title,
            created=t.created_at.date(),
            completed=t.completed_at.date(),
        )
        for t in tasks
        if t.completed_at and t.percent_complete >= 100
    ]


def matrix_as_reference(matrix: list[MatrixRow], area_key: str) -> dict[str, float]:
    """The `sla_reference` block for an area's configuration (medians per type)."""
    return {
        r.work_type: r.median_days
        for r in matrix
        if r.area == area_key and not r.review and r.work_type != "other"
    }
