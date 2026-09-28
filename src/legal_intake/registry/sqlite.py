"""SQLite registry: the demand as JSON with the columns the lookups need. One file holds
the registry and the board (the demo's `.demo/state.sqlite`, production's `data/`)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from ..clock import utc_now
from ..models import Demand, DemandStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS demands (
    id              TEXT PRIMARY KEY,
    area            TEXT NOT NULL,
    status          TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id      TEXT NOT NULL,
    board_task_id   TEXT,
    received_at     TEXT NOT NULL,
    data            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS demands_conversation ON demands (conversation_id);
CREATE INDEX IF NOT EXISTS demands_task ON demands (board_task_id);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    result       TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
"""


class SQLiteRegistry:
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

    def create(self, demand: Demand) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO demands (id, area, status, conversation_id, message_id, board_task_id, received_at, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    demand.id,
                    demand.area,
                    demand.status,
                    demand.conversation_id,
                    demand.message_id,
                    demand.board_task_id,
                    demand.received_at.isoformat(),
                    demand.model_dump_json(),
                ),
            )
            conn.commit()

    def update(self, demand: Demand) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE demands SET status=?, board_task_id=?, data=? WHERE id=?",
                (demand.status, demand.board_task_id, demand.model_dump_json(), demand.id),
            )
            conn.commit()

    def _one(self, sql: str, params: tuple) -> Demand | None:
        with closing(self._connect()) as conn:
            row = conn.execute(sql, params).fetchone()
            return Demand.model_validate_json(row["data"]) if row else None

    def get(self, demand_id: str) -> Demand | None:
        return self._one("SELECT data FROM demands WHERE id = ?", (demand_id,))

    def by_conversation(self, conversation_id: str) -> Demand | None:
        return self._one(
            "SELECT data FROM demands WHERE conversation_id = ? ORDER BY received_at LIMIT 1",
            (conversation_id,),
        )

    def by_task(self, task_id: str) -> Demand | None:
        return self._one("SELECT data FROM demands WHERE board_task_id = ? LIMIT 1", (task_id,))

    def list(self, *, area: str | None = None, status: DemandStatus | None = None) -> list[Demand]:
        sql, params = "SELECT data FROM demands WHERE 1=1", []
        if area:
            sql, params = sql + " AND area = ?", [*params, area]
        if status:
            sql, params = sql + " AND status = ?", [*params, status]
        sql += " ORDER BY received_at DESC"
        with closing(self._connect()) as conn:
            return [
                Demand.model_validate_json(r["data"]) for r in conn.execute(sql, params).fetchall()
            ]

    def message_processed(self, message_id: str) -> bool:
        with closing(self._connect()) as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
                ).fetchone()
                is not None
            )

    def record_message(self, message_id: str, *, result: str, received_at: datetime) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_messages (message_id, result, received_at, processed_at) VALUES (?, ?, ?, ?)",
                (message_id, result, received_at.isoformat(), utc_now().isoformat()),
            )
            conn.commit()

    def processed_messages(self) -> list[dict]:
        with closing(self._connect()) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM processed_messages ORDER BY received_at"
                ).fetchall()
            ]
