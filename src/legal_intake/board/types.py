"""The work board: plans with buckets (one per client), tasks with an assignee, a due
date, a label and a checklist. Planner in production, SQLite in the demo and the tests."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from ..models import Task


class TaskBoard(Protocol):
    kind: str

    def buckets(self, plan: str) -> list[str]: ...
    def ensure_bucket(self, plan: str, name: str) -> str: ...
    def create_task(
        self,
        *,
        plan: str,
        bucket: str,
        title: str,
        assignee: str | None,
        due_date: date | None,
        description: str,
        checklist: list[str],
        label: str | None,
        demand_id: str | None,
        created_at: datetime,
    ) -> Task: ...
    def get(self, task_id: str) -> Task | None: ...
    def list_tasks(self, plan: str) -> list[Task]: ...
    def open_tasks_by_assignee(self, plan: str) -> dict[str, int]: ...
    def complete(self, task_id: str, completed_at: datetime) -> None: ...
