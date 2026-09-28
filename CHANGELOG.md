# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-09-28

First public release: the coded rebuild of a law firm's intake automation that ran as Power Automate flows in two practice areas, with fictional areas, a fixture inbox and an offline demo.

### Added

- Sweep of the intake mailbox: routing by area address, noise filters (auto-generated senders, auto-replies, plain internal mail), forwards and form-relayed demands as registrations, deduplication by conversation, processed-message idempotency.
- Triage behind one contract with three implementations: the Claude API (one call, structured output enforced by the package's schema with the area's taxonomy, cached system prompt per area, thinking off), a keyword rules baseline, and recorded readings for the demo; checks in code that re-apply the distribution rules, the taxonomy, the deadline scale and the reply marker and note every correction.
- Decision cards: Adaptive Card with the package in editable inputs, sent as a reply in the demand's thread to recipients computed by rule and internal by construction, plus a console form for the same decision.
- The decision as deterministic side effects: due date in business days with holidays, task in the client's bucket with label and checklist (buckets created on the fly, matched case-insensitively), registry row with `ai_*` and `final_*` fields and the adjustment flag, acknowledgement to the original sender only in the area's reply mode, first decision wins.
- Two closing paths: the lawyer's reply with the intake account in copy (real reply date) and the board sync (no reply date), with the adherence gap measured.
- Area configuration as validated JSON (mailbox, validation mode, deadline scale, internal review, taxonomy with labels and checklists, lawyers, client directory); two fictional areas shipped.
- Adapters: Microsoft Graph mailbox and mailer, Planner board, SQLite registry and board, fixture inbox, outbox on disk, dry-run mailer.
- Metrics per area and a FastAPI console with the cards, the decision form, the dashboard and a shared-password gate; CLI for the sweep, the decisions, the board sync, the stats, the SLA matrix and the console.
- SLA matrix from the board's history (keyword rules or the Message Batches API), a deterministic synthetic history of 210 completed tasks, and an evaluation script that checks every route of the inbox and measures the rules baseline against the recorded readings.
- 49 offline tests; CI with lint, tests, fixtures check, the demo walkthrough and a secret scan; a Dockerfile and a Windows scheduled-task installer.

[0.1.0]: https://github.com/fillipeml/legal-intake-triage/releases/tag/v0.1.0
