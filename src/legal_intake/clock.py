"""The routine's notion of now. Pinned by REFERENCE_DATE (tests, the demo); otherwise the
wall clock in the firm's time zone."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from .config import Settings


def today(settings: Settings) -> date:
    if settings.reference_date:
        return settings.reference_date
    return datetime.now(ZoneInfo(settings.timezone)).date()


def now(settings: Settings) -> datetime:
    """A timezone-aware instant; on a pinned date, nine in the morning of that day."""
    tz = ZoneInfo(settings.timezone)
    if settings.reference_date:
        return datetime.combine(settings.reference_date, time(9, 0), tzinfo=tz)
    return datetime.now(tz)


def utc_now() -> datetime:
    return datetime.now(UTC)
