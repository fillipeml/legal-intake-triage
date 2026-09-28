"""Demo glue: the paths of the fixtures and the seeding of the state."""

from __future__ import annotations

import json
from pathlib import Path

from .board.sqlite import SQLiteBoard
from .models import Demand, Task
from .registry.sqlite import SQLiteRegistry

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def seed_if_empty(
    registry: SQLiteRegistry, board: SQLiteBoard, seed_path: Path = FIXTURES / "state" / "seed.json"
) -> bool:
    """Loads the seed once: the boards' tasks and the historical demands."""
    if registry.list() or any(
        board.list_tasks(plan) for plan in ("advisory-weekly", "corporate-advisory")
    ):
        return False
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    for plan, names in seed.get("buckets", {}).items():
        for name in names:
            board.ensure_bucket(plan, name)
    for raw in seed.get("tasks", []):
        board.insert(Task.model_validate(raw))
    for raw in seed.get("demands", []):
        registry.create(Demand.model_validate(raw))
    return True
