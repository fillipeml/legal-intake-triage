"""Shared fixtures: settings pinned to the demo's Monday, services on a temporary state
file seeded from the fixtures, and a way to pick a demand of the fixture inbox by id."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from legal_intake.config import Settings
from legal_intake.factory import build_services
from legal_intake.services import Services

ROOT = Path(__file__).resolve().parents[1]
ENV_VARS = [
    "DEMO_MODE",
    "DRY_RUN",
    "REFERENCE_DATE",
    "STATE_DB",
    "AREAS_DIR",
    "INTERNAL_DOMAIN",
    "INTAKE_MAILBOX",
    "ANTHROPIC_API_KEY",
    "CONSOLE_PASSWORD",
    "CONSOLE_SECRET",
    "MS_TENANT_ID",
]


def demand_id_for(message_id: str) -> str:
    return "d-" + hashlib.sha1(message_id.encode()).hexdigest()[:8]


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(ROOT)
    return Settings(
        demo_mode=True,
        dry_run=False,
        reference_date=date(2026, 9, 21),
        state_db=str(tmp_path / "state.sqlite"),
        areas_dir=str(ROOT / "areas"),
        intake_mailbox="intake@lawfirm.example",
        internal_domain="lawfirm.example",
        firm_name="Example Law Firm",
    )


@pytest.fixture
def services(settings: Settings) -> Services:
    return build_services(settings)


@pytest.fixture
def advisory(services: Services):
    return services.area("advisory")


@pytest.fixture
def corporate(services: Services):
    return services.area("corporate")
