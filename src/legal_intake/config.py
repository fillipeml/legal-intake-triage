"""Settings from the environment. The only module that knows the variable names."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_REFERENCE_DATE = date(2026, 9, 21)  # a Monday; the fixture inbox is built around it


def _csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if v.strip()]
    return [v.strip() for v in value.replace(";", ",").split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- mode -------------------------------------------------------------------------
    demo_mode: bool = False
    dry_run: bool = True
    reference_date: date | None = None
    timezone: str = "America/Sao_Paulo"
    holiday_subdivision: str = "GO"

    # --- the firm ---------------------------------------------------------------------
    firm_name: str = "Example Law Firm"
    internal_domain: str = "lawfirm.example"
    intake_mailbox: str = "intake@lawfirm.example"
    areas_dir: str = "areas"
    max_body_chars: int = 15_000
    sweep_lookback_days: int = 3
    alert_emails: list[str] = Field(default_factory=list)

    # --- Microsoft Graph --------------------------------------------------------------
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    sharepoint_site: str = ""
    registry_list: str = "Intake - Master record"

    # --- model ------------------------------------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    sla_classifier_model: str = "claude-haiku-4-5"

    # --- state and console ------------------------------------------------------------
    state_db: str = "data/state.sqlite"
    console_password: str = ""
    console_secret: str = ""

    @field_validator("alert_emails", mode="before")
    @classmethod
    def _lists(cls, v: object) -> list[str]:
        return _csv(v)  # type: ignore[arg-type]

    @field_validator("reference_date", mode="before")
    @classmethod
    def _empty_date(cls, v: object) -> object:
        return None if v in ("", None) else v

    @field_validator("demo_mode", "dry_run", mode="before")
    @classmethod
    def _empty_bool(cls, v: object) -> object:
        return False if v == "" else v

    @field_validator("internal_domain", mode="before")
    @classmethod
    def _domain(cls, v: object) -> object:
        return str(v).strip().lower().lstrip("@") if v else v

    def is_internal(self, email: str) -> bool:
        return email.strip().lower().endswith("@" + self.internal_domain)

    @property
    def state_dir(self) -> Path:
        return Path(self.state_db).parent

    def for_demo(self) -> Settings:
        """The demo profile: fixtures in, files out, no network."""
        return self.model_copy(
            update={
                "demo_mode": True,
                "state_db": ".demo/state.sqlite",
                "reference_date": self.reference_date or DEMO_REFERENCE_DATE,
                "intake_mailbox": "intake@lawfirm.example",
                "internal_domain": "lawfirm.example",
                "alert_emails": ["operator@lawfirm.example"],
            }
        )


def get_settings() -> Settings:
    settings = Settings()
    return settings.for_demo() if settings.demo_mode else settings
