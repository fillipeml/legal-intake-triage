"""Generates the synthetic history of completed tasks for the SLA matrix demo
(fixtures/sla/history.csv). Deterministic: a seeded generator, fictional clients, titles
that follow the taxonomies' vocabulary, durations drawn around a per-type median.

    uv run python scripts/make_fixtures.py
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "sla" / "history.csv"

CLIENTS = [
    "Construtora Exemplo",
    "Incorporadora Modelo",
    "Loja Fictícia",
    "Startup Alfa",
    "Clínica Beta",
    "Empresa Zeta",
]
CORPORATE_CLIENTS = ["Holding Beta Participações", "Grupo Gama", "Família Delta", "Indústria Ômega"]

# (title template, median business days, spread)
ADVISORY = [
    ("Análise contratual — {client}", 4, 2),
    ("Revisão do contrato de fornecimento — {client}", 4, 2),
    ("Elaboração de aditivo — {client}", 5, 2),
    ("Elaboração de contrato de prestação de serviços — {client}", 5, 3),
    ("Notificação extrajudicial — {client}", 4, 2),
    ("Parecer sobre {topic} — {client}", 7, 3),
    ("Consulta sobre {topic} — {client}", 1, 1),
    ("Contestação — processo nº {case}", 6, 3),
    ("Manifestação nos autos — processo nº {case}", 3, 2),
    ("Ajuizar ação de cobrança — {client}", 8, 3),
    ("Reunião de alinhamento com {client}", 2, 1),  # classified as other by the rules
]
CORPORATE = [
    ("Elaboração de contrato — {client}", 6, 3),
    ("Revisão do acordo de sócios — {client}", 5, 2),
    ("Elaborar ata de assembleia — {client}", 3, 1),
    ("Revisão da ata — {client}", 2, 1),
    ("Due diligence — {client}", 12, 4),
    ("Elaborar parecer sobre {topic} — {client}", 8, 3),
    ("Consulta sobre {topic} — {client}", 1, 1),
    ("Elaborar notificação — {client}", 3, 1),
]
TOPICS = [
    "garantia",
    "reajuste",
    "rescisão",
    "marca",
    "distribuição de lucros",
    "responsabilidade dos sócios",
    "franquia",
    "locação",
]


def case_number(rng: random.Random) -> str:
    return (
        f"{rng.randint(1, 9999999):07d}-{rng.randint(10, 99)}.2099.8.26.{rng.randint(1, 999):04d}"
    )


def rows_for(
    rng: random.Random,
    area: str,
    templates: list[tuple[str, int, int]],
    clients: list[str],
    count: int,
    start: date,
) -> list[dict]:
    rows = []
    for _ in range(count):
        template, median, spread = rng.choice(templates)
        created = start + timedelta(days=rng.randint(0, 330))
        while created.weekday() >= 5:
            created += timedelta(days=1)
        duration = max(1, round(rng.gauss(median, spread / 1.5)))
        completed = created
        remaining = duration
        while remaining > 0:
            completed += timedelta(days=1)
            if completed.weekday() < 5:
                remaining -= 1
        title = template.format(
            client=rng.choice(clients), topic=rng.choice(TOPICS), case=case_number(rng)
        )
        rows.append(
            {
                "area": area,
                "title": title,
                "created": created.isoformat(),
                "completed": completed.isoformat(),
            }
        )
    return rows


def main() -> None:
    rng = random.Random(7)
    rows = rows_for(rng, "advisory", ADVISORY, CLIENTS, 140, date(2025, 9, 1)) + rows_for(
        rng, "corporate", CORPORATE, CORPORATE_CLIENTS, 70, date(2025, 9, 1)
    )
    rows.sort(key=lambda r: (r["area"], r["created"], r["title"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["area", "title", "created", "completed"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
