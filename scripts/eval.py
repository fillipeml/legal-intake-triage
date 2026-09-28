"""Evaluates the deterministic parts of the intake on the fixture inbox.

1. Routes: every message of the inbox takes the route it was built for (skip, duplicate,
   closing, demand) and every card goes to an internal address.
2. The rules-based triager against the recorded readings of the eight demands, field by
   field (client, work type, complexity, days, lawyer): how far the keyword baseline gets
   before a model is involved. The recorded readings stand in for the model in the demo;
   they are hand-written expectations, not a measurement of a model.
3. The checks over the recorded readings: how many corrections the code makes to them.

    uv run python scripts/eval.py      (exit 1 when a route or a guard is not as expected)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legal_intake.areas import area_for, load_areas  # noqa: E402
from legal_intake.filters import clean_body, route_message  # noqa: E402
from legal_intake.mail.fixture import FixtureInbox  # noqa: E402
from legal_intake.models import TriagePackage  # noqa: E402
from legal_intake.triage.checks import check_package  # noqa: E402
from legal_intake.triage.rules import RuleTriager  # noqa: E402
from legal_intake.triage.types import TriageInput  # noqa: E402

INTERNAL = "lawfirm.example"
INTAKE = "intake@lawfirm.example"
LOAD = {
    "advisory": {"Bruno Costa": 4, "Carla Mendes": 6, "Diego Souza": 5, "Elena Prado": 2},
    "corporate": {"Igor Lima": 3, "Júlia Neves": 2, "Lucas Pires": 5},
}
EXPECTED_ROUTES = {
    "m01": "demand",
    "m02": "demand",
    "m03": "demand",
    "m04": "demand",
    "m05": "skip",
    "m06": "skip",
    "m07": "skip",
    "m08": "duplicate",
    "m09": "demand",
    "m10": "closing",
    "m11": "duplicate",
    "m12": "demand",
    "m13": "demand",
    "m14": "demand",
}
FIELDS = ["client", "work_type", "complexity", "suggested_days", "suggested_lawyer"]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    areas = load_areas(ROOT / "areas")
    inbox = FixtureInbox(ROOT / "fixtures" / "inbox" / "messages.json")
    recorded = json.loads(
        (ROOT / "fixtures" / "triage" / "recorded.json").read_text(encoding="utf-8")
    )
    failures = 0
    seen_conversations: set[str] = set()

    print("routes")
    for m in inbox.messages:
        area = area_for(areas, m.recipients)
        if area is None:
            actual = (
                "closing"
                if m.sender.endswith("@" + INTERNAL) and INTAKE in m.recipients
                else "skip"
            )
        else:
            route = route_message(
                m.sender,
                m.subject,
                is_internal=m.sender.endswith("@" + INTERNAL),
                is_intake_account=m.sender == INTAKE,
            )
            if (
                route.kind == "demand"
                and m.conversation_id in seen_conversations
                or route.kind == "demand"
                and m.conversation_id.startswith("conv-seed")
            ):
                actual = "duplicate"
            elif route.kind == "closing_candidate":
                actual = "skip"
            else:
                actual = route.kind
            if route.kind == "demand":
                seen_conversations.add(m.conversation_id)
        ok = actual == EXPECTED_ROUTES[m.id]
        failures += 0 if ok else 1
        print(f"  {'ok ' if ok else 'BAD'} {m.id} {actual:9} {m.subject[:60]}")

    print("\nrules baseline vs recorded readings (field agreement)")
    agree = dict.fromkeys(FIELDS, 0)
    total = 0
    notes_total = 0
    for m in inbox.messages:
        if m.id not in recorded:
            continue
        area = area_for(areas, m.recipients)
        route = route_message(
            m.sender,
            m.subject,
            is_internal=m.sender.endswith("@" + INTERNAL),
            is_intake_account=m.sender == INTAKE,
        )
        item = TriageInput(
            message=m,
            area=area,
            body=clean_body(m.body, 15_000),
            forwarded_by=route.forwarded_by,
            load=LOAD[area.key],
        )
        rules = RuleTriager().triage(item).package
        rules, _ = check_package(
            rules,
            area,
            forwarded_by=route.forwarded_by,
            load=LOAD[area.key],
            firm_name="Example Law Firm",
        )
        expected = TriagePackage.model_validate(recorded[m.id])
        checked, notes = check_package(
            expected,
            area,
            forwarded_by=route.forwarded_by,
            load=LOAD[area.key],
            firm_name="Example Law Firm",
        )
        notes_total += len(notes)
        total += 1
        marks = []
        for f in FIELDS:
            same = getattr(rules, f) == getattr(expected, f)
            agree[f] += int(same)
            marks.append(f"{f.split('_')[-1]}={'=' if same else 'x'}")
        got = f"{rules.work_type}/{rules.complexity.value}/{rules.suggested_lawyer}"
        want = f"{expected.work_type}/{expected.complexity.value}/{expected.suggested_lawyer}"
        print(f"  {m.id} {' '.join(marks)}  rules: {got} · recorded: {want}")
        if notes:
            print(f"       checks on the recording: {'; '.join(notes)}")

    print("\nfield          agreement")
    for f in FIELDS:
        print(f"{f:14} {agree[f]}/{total}")
    print(f"\ncorrections the checks made to the recorded readings: {notes_total}")
    print(f"routes as expected: {14 - failures}/14")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
