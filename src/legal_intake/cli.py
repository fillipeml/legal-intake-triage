"""Command line.

intake sweep [--date] [--demo]            read the intake mailbox, triage, send the cards
intake pending [--demo]                    demands awaiting a decision
intake decide <id> --approve|--discard ... apply a decision (what the card does)
intake demands [--status s] [--area a]     the registry
intake show <id>                           one demand in full
intake sync-board                          close demands whose task was completed
intake complete-task <task-id>             demo helper: mark a task complete on the board
intake stats                               the metrics the dashboard shows
intake sla [--mode rules|batch]            the SLA matrix from the board's history
intake serve                               the console (cards, dashboard)
intake reset                               delete the demo state
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from legal_intake import __version__


def _utf8_console() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() != "utf-8":
            stream.reconfigure(encoding="utf-8")


def _services(demo: bool, reference: str | None):
    if demo:
        os.environ["DEMO_MODE"] = "true"
    if reference:
        os.environ["REFERENCE_DATE"] = reference
    from legal_intake.config import get_settings
    from legal_intake.factory import build_services

    return build_services(get_settings())


def main() -> int:
    _utf8_console()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="intake", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--demo", action="store_true", help="DEMO_MODE=true: fixtures in, files out, no network"
    )
    parser.add_argument(
        "--date", metavar="YYYY-MM-DD", help="pin 'today' (the demo defaults to 2026-09-21)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sweep", help="read the mailbox, triage and send the cards")
    sub.add_parser("pending", help="demands awaiting a decision")
    d = sub.add_parser("decide", help="apply a decision")
    d.add_argument("demand_id")
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--discard", action="store_true")
    d.add_argument("--by", default="operator@lawfirm.example", help="who decides (e-mail)")
    d.add_argument("--client")
    d.add_argument("--type", dest="work_type")
    d.add_argument("--lawyer")
    d.add_argument("--complexity", choices=["urgent", "low", "medium", "high"])
    d.add_argument("--days", type=int)
    d.add_argument("--reviewer")
    d.add_argument("--review-days", type=int, default=0)
    d.add_argument("--reply-file", help="a file with the reply text (keeps the draft otherwise)")
    ls = sub.add_parser("demands", help="list the registry")
    ls.add_argument("--status")
    ls.add_argument("--area")
    sh = sub.add_parser("show", help="one demand in full")
    sh.add_argument("demand_id")
    sub.add_parser("sync-board", help="close demands whose task was completed on the board")
    ct = sub.add_parser("complete-task", help="demo helper: complete a task on the board")
    ct.add_argument("task_id")
    sub.add_parser("stats", help="the metrics")
    sl = sub.add_parser("sla", help="the SLA matrix from the board's history")
    sl.add_argument("--mode", choices=["rules", "batch"], default="rules")
    sl.add_argument("--history", help="a CSV (area,title,created,completed) instead of the board")
    sl.add_argument("--out", help="write the matrix as JSON here")
    sv = sub.add_parser("serve", help="run the console")
    sv.add_argument("--port", type=int, default=8000)
    sub.add_parser("reset", help="delete the demo state")

    args = parser.parse_args()
    if args.command == "reset":
        target = Path(".demo")
        if target.exists():
            shutil.rmtree(target)
        print("demo state removed")
        return 0

    services = _services(args.demo, args.date)
    settings = services.settings
    from legal_intake.clock import now, today

    if args.command == "sweep":
        from legal_intake.pipeline.intake import sweep

        mode = "DEMO" if settings.demo_mode else ("DRY_RUN" if settings.dry_run else "LIVE")
        summary = sweep(services)
        print(f"Sweep of {today(settings)} | mode: {mode} | {summary.line()}")
        for s in summary.skipped:
            print(f"  skipped:    {s}")
        for c in summary.closed:
            print(f"  closed:     {c}")
        for c in summary.cards:
            print(f"  card:       {c['demand']} -> {', '.join(c['to'])}  ({c['subject']})")
        for f in summary.failed:
            print(f"  failed:     {f}")
        return 1 if summary.failed else 0

    if args.command == "pending":
        from legal_intake.models import DemandStatus

        rows = services.registry.list(status=DemandStatus.AWAITING_VALIDATION)
        if not rows:
            print("No demand awaiting a decision.")
            return 0
        for dm in sorted(rows, key=lambda x: x.received_at):
            print(f"{dm.id}  [{dm.area}] {dm.subject}")
            print(
                f"           {dm.ai_client} · {dm.ai_work_type} · {dm.ai_complexity} · {dm.ai_days} d"
                f" · {dm.ai_lawyer} · card to {', '.join(dm.card_recipients)}"
            )
        return 0

    if args.command == "decide":
        from legal_intake.models import Decision
        from legal_intake.pipeline.decision import DecisionError, decide

        reply = Path(args.reply_file).read_text(encoding="utf-8") if args.reply_file else None
        decision = Decision(
            demand_id=args.demand_id,
            action="approve" if args.approve else "discard",
            validated_by=args.by,
            client=args.client,
            work_type=args.work_type,
            lawyer=args.lawyer,
            complexity=args.complexity,
            days=args.days,
            reply=reply,
            reviewer=args.reviewer,
            review_days=args.review_days,
        )
        try:
            outcome = decide(services, decision)
        except DecisionError as exc:
            print(f"error: {exc}")
            return 1
        print(outcome.line())
        return 0

    if args.command == "demands":
        from legal_intake.models import DemandStatus

        rows = services.registry.list(
            area=args.area, status=DemandStatus(args.status) if args.status else None
        )
        for dm in sorted(rows, key=lambda x: x.received_at):
            final = f"{dm.final_lawyer} · due {dm.due_date}" if dm.final_lawyer else "-"
            adj = "adjusted" if dm.adjusted else ("as suggested" if dm.adjusted is False else "")
            print(f"{dm.id}  {dm.status.value:20} [{dm.area}] {dm.subject[:48]:48} {final} {adj}")
        print(f"\n{len(rows)} demand(s)")
        return 0

    if args.command == "show":
        dm = services.registry.get(args.demand_id)
        if not dm:
            print("not found")
            return 1
        print(json.dumps(dm.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0

    if args.command == "sync-board":
        from legal_intake.pipeline.closing import sync_from_board

        closed = sync_from_board(services, now(settings))
        for c in closed:
            print(f"  {c}")
        print(f"{len(closed)} demand(s) closed from the board")
        return 0

    if args.command == "complete-task":
        services.board.complete(args.task_id, now(settings))
        print(f"task {args.task_id} completed")
        return 0

    if args.command == "stats":
        from legal_intake.pipeline.metrics import closed_via_gap, compute_metrics

        metrics = compute_metrics(services, today(settings))
        for m in metrics.areas:
            print(f"\n== {m.name} ({m.demands} demands)")
            print(f"   status: {m.by_status}")
            print(f"   channel: {m.by_channel}")
            print(f"   type: {m.by_type}")
            rate = f"{m.adjustment_rate:.0%}" if m.adjustment_rate is not None else "-"
            print(
                f"   decided {m.decided} · adjusted {m.adjusted} ({rate}) · fields {m.adjusted_fields}"
            )
            print(
                f"   hours to decision (avg): {m.hours_to_decision_avg}"
                f" · replied same day: {m.replied_same_day}/{m.replied_total}"
            )
            gap = closed_via_gap(m)
            print(
                f"   closed via: {m.closed_via} · board share {gap if gap is not None else '-'}"
                f" · on time {m.done_on_time} · late {m.done_late} · overdue now {m.overdue}"
            )
            print(f"   open by lawyer: {m.open_by_lawyer}")
        return 0

    if args.command == "sla":
        from legal_intake.sla import (
            HistoryRow,
            build_matrix,
            classify_by_batch,
            classify_by_rules,
            history_from_tasks,
        )

        rows: list[HistoryRow] = []
        if args.history:
            with open(args.history, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    rows.append(
                        HistoryRow(
                            area=r["area"],
                            title=r["title"],
                            created=date.fromisoformat(r["created"]),
                            completed=date.fromisoformat(r["completed"]),
                        )
                    )
        else:
            for area in services.areas:
                rows.extend(history_from_tasks(services.board.list_tasks(area.board.plan), area))
        by_area = {a.key: a for a in services.areas}
        if args.mode == "batch":
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            for area in services.areas:
                titles = [r.title for r in rows if r.area == area.key]
                mapping = classify_by_batch(
                    titles, area, client=client, model=settings.sla_classifier_model
                )
                for r in rows:
                    if r.area == area.key:
                        r.work_type = mapping.get(r.title, "other")
        else:
            for r in rows:
                r.work_type = (
                    classify_by_rules(r.title, by_area[r.area]) if r.area in by_area else "other"
                )
        matrix = build_matrix(rows)
        print(
            f"{'area':10} {'work type':26} {'median':>7} {'p80':>6} {'standard':>9} {'sample':>7}  review"
        )
        for m in matrix:
            print(
                f"{m.area:10} {m.work_type:26} {m.median_days:7.1f} {m.p80_days:6.1f}"
                f" {m.standard_days:9d} {m.sample:7d}  {'yes' if m.review else ''}"
            )
        if args.out:
            Path(args.out).write_text(
                json.dumps([m.__dict__ for m in matrix], indent=2), encoding="utf-8"
            )
            print(f"written to {args.out}")
        return 0

    if args.command == "serve":
        import uvicorn

        from legal_intake.console.app import create_app

        uvicorn.run(create_app(services), host="127.0.0.1", port=args.port)
        return 0

    return 2


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""
