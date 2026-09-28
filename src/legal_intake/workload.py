"""The current load of an area's lawyers: open tasks on the area's plan, by assignee.
It goes in the user message of the triage (dynamic, so it does not break the cache)."""

from __future__ import annotations

from .areas import Area
from .board.types import TaskBoard


def current_load(board: TaskBoard, area: Area) -> dict[str, int]:
    counts = board.open_tasks_by_assignee(area.board.plan)
    return {lw.name: counts.get(lw.name, 0) for lw in area.lawyers if lw.receives_distribution}
