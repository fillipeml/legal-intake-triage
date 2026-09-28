"""The only module that chooses the implementation behind each boundary."""

from __future__ import annotations

import logging
from pathlib import Path

from .areas import load_areas
from .board.sqlite import SQLiteBoard
from .config import Settings
from .demo import FIXTURES, seed_if_empty
from .mail.fixture import FixtureInbox, OutboxMailer
from .mail.types import DryRunMailer
from .registry.sqlite import SQLiteRegistry
from .services import Services
from .triage.fixture import FixtureTriager

logger = logging.getLogger(__name__)


def build_services(settings: Settings, *, fixtures: Path = FIXTURES) -> Services:
    areas = load_areas(settings.areas_dir)
    registry = SQLiteRegistry(settings.state_db)

    if settings.demo_mode:
        board = SQLiteBoard(settings.state_db)
        if seed_if_empty(registry, board, fixtures / "state" / "seed.json"):
            logger.info("demo state seeded in %s", settings.state_db)
        return Services(
            settings=settings,
            areas=areas,
            registry=registry,
            board=board,
            mailbox=FixtureInbox(fixtures / "inbox" / "messages.json"),
            mailer=OutboxMailer(settings.state_dir / "outbox"),
            triager=FixtureTriager(fixtures / "triage" / "recorded.json"),
        )

    from .board.planner import PlannerBoard
    from .graph import GraphClient, GraphError
    from .mail.graph import GraphMailbox, GraphMailer
    from .triage.claude import ClaudeTriager

    graph = GraphClient(settings.ms_tenant_id, settings.ms_client_id, settings.ms_client_secret)
    user_ids: dict[str, str] = {}
    for area in areas:
        for lawyer in area.lawyers:
            try:
                user_ids[lawyer.name] = graph.get(f"/users/{lawyer.email}", {"$select": "id"})["id"]
            except GraphError as exc:  # a lawyer without an account is assigned nothing
                logger.warning("no directory user for %s: %s", lawyer.email, exc)
    return Services(
        settings=settings,
        areas=areas,
        registry=registry,
        board=PlannerBoard(graph, user_ids=user_ids),
        mailbox=GraphMailbox(graph, settings.intake_mailbox),
        mailer=DryRunMailer() if settings.dry_run else GraphMailer(graph, settings.intake_mailbox),
        triager=ClaudeTriager(
            settings.anthropic_api_key, settings.anthropic_model, settings.firm_name
        ),
    )
