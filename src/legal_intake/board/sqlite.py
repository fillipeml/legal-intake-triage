from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from ..models import Task

_SCHEMA = """
CREATE TABLE IF NOT EXISTS buckets (
    plan TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (plan, name)
);
CREATE TABLE IF NOT EXISTS tasks (
    id               TEXT PRIMARY KEY,
    plan             TEXT NOT NULL,
    bucket           TEXT NOT NULL,
    title            TEXT NOT NULL,
    assignee         TEXT,
    due_date         TEXT,
    created_at       TEXT NOT NULL,
    completed_at     TEXT,
    percent_complete INTEGER NOT NULL DEFAULT 0,
    label            TEXT,
    description      TEXT NOT NULL DEFAULT '',
    checklist        TEXT NOT NULL DEFAULT '[]',
    demand_id        TEXT
);
"""


def _task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        plan=row["plan"],
        bucket=row["bucket"],
        title=row["title"],
        assignee=row["assignee"],
        due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        percent_complete=row["percent_complete"],
        label=row["label"],
        description=row["description"],
        checklist=json.loads(row["checklist"]),
        demand_id=row["demand_id"],
    )


class SQLiteBoard:
    kind = "sqlite"

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def buckets(self, plan: str) -> list[str]:
        with closing(self._connect()) as conn:
            return [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM buckets WHERE plan = ? ORDER BY name", (plan,)
                ).fetchall()
            ]

    def ensure_bucket(self, plan: str, name: str) -> str:
        """Finds the bucket case- and space-insensitively (a client typed on the card must not
        create a duplicate) and creates it when missing."""
        wanted = name.strip().lower()
        for existing in self.buckets(plan):
            if existing.strip().lower() == wanted:
                return existing
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO buckets (plan, name) VALUES (?, ?)", (plan, name.strip())
            )
            conn.commit()
        return name.strip()

    def create_task(
        self,
        *,
        plan,
        bucket,
        title,
        assignee,
        due_date,
        description,
        checklist,
        label,
        demand_id,
        created_at,
    ) -> Task:
        task = Task(
            id=f"task-{uuid.uuid4().hex[:12]}",
            plan=plan,
            bucket=bucket,
            title=title,
            assignee=assignee,
            due_date=due_date,
            created_at=created_at,
            label=label,
            description=description,
            checklist=list(checklist),
            demand_id=demand_id,
        )
        self.insert(task)
        return task

    def insert(self, task: Task) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO buckets (plan, name) VALUES (?, ?)", (task.plan, task.bucket)
            )
            conn.execute(
                "INSERT INTO tasks (id, plan, bucket, title, assignee, due_date, created_at,"
                " completed_at, percent_complete, label, description, checklist, demand_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task.id,
                    task.plan,
                    task.bucket,
                    task.title,
                    task.assignee,
                    task.due_date.isoformat() if task.due_date else None,
                    task.created_at.isoformat(),
                    task.completed_at.isoformat() if task.completed_at else None,
                    task.percent_complete,
                    task.label,
                    task.description,
                    json.dumps(task.checklist, ensure_ascii=False),
                    task.demand_id,
                ),
            )
            conn.commit()

    def get(self, task_id: str) -> Task | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return _task(row) if row else None

    def list_tasks(self, plan: str) -> list[Task]:
        with closing(self._connect()) as conn:
            return [
                _task(r)
                for r in conn.execute(
                    "SELECT * FROM tasks WHERE plan = ? ORDER BY created_at", (plan,)
                ).fetchall()
            ]

    def open_tasks_by_assignee(self, plan: str) -> dict[str, int]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT assignee, COUNT(*) AS n FROM tasks"
                " WHERE plan = ? AND percent_complete < 100 AND assignee IS NOT NULL GROUP BY assignee",
                (plan,),
            ).fetchall()
            return {r["assignee"]: r["n"] for r in rows}

    def complete(self, task_id: str, completed_at: datetime) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE tasks SET percent_complete = 100, completed_at = ? WHERE id = ?",
                (completed_at.isoformat(), task_id),
            )
            conn.commit()
