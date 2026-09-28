"""What the registry and the board can measure, for the console and the CLI."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ..areas import Area
from ..models import ClosedVia, Demand, DemandStatus
from ..services import Services


@dataclass
class AreaMetrics:
    key: str
    name: str
    demands: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_channel: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    by_client: dict[str, int] = field(default_factory=dict)
    decided: int = 0
    adjusted: int = 0
    adjustment_rate: float | None = None
    adjusted_fields: dict[str, int] = field(default_factory=dict)
    hours_to_decision_avg: float | None = None
    replied_same_day: int = 0
    replied_total: int = 0
    closed_via: dict[str, int] = field(default_factory=dict)
    done_on_time: int = 0
    done_late: int = 0
    open_by_lawyer: dict[str, int] = field(default_factory=dict)
    overdue: int = 0


@dataclass
class Metrics:
    as_of: date
    areas: list[AreaMetrics]


def _area_metrics(
    area: Area, demands: list[Demand], open_by_lawyer: dict[str, int], today: date
) -> AreaMetrics:
    m = AreaMetrics(key=area.key, name=area.name, demands=len(demands))
    m.by_status = dict(Counter(d.status.value for d in demands))
    m.by_channel = dict(Counter(d.channel.value for d in demands))
    m.by_type = dict(
        Counter(
            (
                area.work_type(d.final_work_type or d.ai_work_type).title
                if area.work_type(d.final_work_type or d.ai_work_type)
                else "Other"
            )
            for d in demands
        )
    )
    m.by_client = dict(Counter((d.final_client or d.ai_client) for d in demands))
    decided = [d for d in demands if d.decided_at]
    m.decided = len(decided)
    m.adjusted = sum(1 for d in decided if d.adjusted)
    m.adjustment_rate = round(m.adjusted / m.decided, 3) if decided else None
    fields = Counter()
    for d in decided:
        if d.final_client != d.ai_client:
            fields["client"] += 1
        if d.final_work_type != d.ai_work_type:
            fields["work type"] += 1
        if d.final_lawyer != d.ai_lawyer:
            fields["lawyer"] += 1
        if d.final_complexity != d.ai_complexity:
            fields["complexity"] += 1
        if d.final_days != d.ai_days:
            fields["deadline"] += 1
    m.adjusted_fields = dict(fields)
    hours = [
        (d.decided_at - d.received_at).total_seconds() / 3600
        for d in decided
        if d.decided_at and d.received_at
    ]
    m.hours_to_decision_avg = round(sum(hours) / len(hours), 1) if hours else None
    replied = [d for d in demands if d.replied_at]
    m.replied_total = len(replied)
    m.replied_same_day = sum(1 for d in replied if d.replied_at.date() == d.received_at.date())
    m.closed_via = dict(Counter(d.closed_via.value for d in demands if d.closed_via))
    for d in demands:
        if d.status == DemandStatus.DONE and d.due_date and d.closed_at:
            if d.closed_at.date() <= d.due_date:
                m.done_on_time += 1
            else:
                m.done_late += 1
        if d.status == DemandStatus.IN_EXECUTION and d.due_date and d.due_date < today:
            m.overdue += 1
    m.open_by_lawyer = {lw.name: open_by_lawyer.get(lw.name, 0) for lw in area.lawyers}
    return m


def compute_metrics(services: Services, today: date) -> Metrics:
    out = []
    for area in services.areas:
        demands = services.registry.list(area=area.key)
        load = services.board.open_tasks_by_assignee(area.board.plan)
        out.append(_area_metrics(area, demands, load, today))
    return Metrics(as_of=today, areas=out)


def closed_via_gap(metrics: AreaMetrics) -> float | None:
    """The share of closings that came from the board (no reply date): the adherence gap."""
    total = sum(metrics.closed_via.values())
    if not total:
        return None
    return round(metrics.closed_via.get(ClosedVia.BOARD.value, 0) / total, 3)
