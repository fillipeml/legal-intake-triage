"""The deterministic rules of distribution.

Rule one: the client's portfolio owner, always. Rule two: the lawyer who forwarded the
demand (or registered it through the form), who owns the relationship. Rule three: the
lawyer with the lowest current load
among those who receive distribution, ties by name. The model is asked to follow the same
rules and cite them; the code checks its answer and corrects it (see `triage/checks.py`)."""

from __future__ import annotations

from dataclasses import dataclass

from .areas import Area
from .models import NOT_IDENTIFIED


@dataclass(frozen=True)
class Suggestion:
    lawyer: str
    rationale: str
    rule: str  # owner | forwarder | load | none


def suggest_lawyer(
    area: Area, *, client_name: str | None, forwarded_by: str | None, load: dict[str, int]
) -> Suggestion:
    client = (
        area.client_by_name(client_name) if client_name and client_name != NOT_IDENTIFIED else None
    )
    if client and client.owner:
        return Suggestion(client.owner, f"portfolio owner of {client.name}", "owner")
    if forwarded_by:
        lawyer = area.lawyer_by_email(forwarded_by)
        if lawyer:
            return Suggestion(
                lawyer.name,
                "the lawyer who forwarded the demand owns the relationship",
                "forwarder",
            )
    pool = area.distribution()
    if not pool:
        return Suggestion(NOT_IDENTIFIED, "no lawyer receives distribution in this area", "none")
    ranked = sorted(pool, key=lambda lw: (load.get(lw.name, 0), lw.name))
    best = ranked[0]
    others = ", ".join(f"{lw.name} {load.get(lw.name, 0)}" for lw in ranked[1:3])
    detail = f" (open tasks: {best.name} {load.get(best.name, 0)}; {others})" if others else ""
    return Suggestion(best.name, f"lowest current load in the area{detail}", "load")
