"""Business-day arithmetic with the national and state holidays.

The original flow counted weekdays only; a deadline promised to a client must not land on
a holiday, so the calendar here includes them (the state is a setting)."""

from __future__ import annotations

from datetime import date, timedelta

import holidays

_CACHE: dict[tuple[str, int], holidays.HolidayBase] = {}


def _calendar(subdivision: str, year: int) -> holidays.HolidayBase:
    key = (subdivision, year)
    if key not in _CACHE:
        _CACHE[key] = holidays.Brazil(subdiv=subdivision or None, years=year)
    return _CACHE[key]


def is_business_day(day: date, subdivision: str = "GO") -> bool:
    return day.weekday() < 5 and day not in _calendar(subdivision, day.year)


def add_business_days(start: date, days: int, subdivision: str = "GO") -> date:
    """The date `days` business days after `start` (the start day itself does not count)."""
    current = start
    remaining = max(0, days)
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current, subdivision):
            remaining -= 1
    return current


def business_days_between(start: date, end: date, subdivision: str = "GO") -> int:
    """Business days from `start` (exclusive) to `end` (inclusive); the duration of a task."""
    if end <= start:
        return 0
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if is_business_day(current, subdivision):
            count += 1
    return count


def date_br(day: date) -> str:
    return day.strftime("%d/%m/%Y")
