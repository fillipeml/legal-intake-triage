"""The services a pipeline receives: built once by the factory, passed explicitly."""

from __future__ import annotations

from dataclasses import dataclass

from .areas import Area
from .board.types import TaskBoard
from .config import Settings
from .mail.types import Mailbox, Mailer
from .registry.types import Registry
from .triage.types import Triager


@dataclass
class Services:
    settings: Settings
    areas: list[Area]
    registry: Registry
    board: TaskBoard
    mailbox: Mailbox
    mailer: Mailer
    triager: Triager
    console_url: str = "http://localhost:8000"

    def area(self, key: str) -> Area:
        for a in self.areas:
            if a.key == key:
                return a
        raise KeyError(f"unknown area {key}")
