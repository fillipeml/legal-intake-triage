# CLAUDE.md

Working rules for AI-assisted changes in this repository. They mirror the README; the README wins on conflict.

## Non-negotiable rules

1. **The model prepares; a person decides; the approval acts.** `triage/claude.py` is the only module that calls a model, and its output is a suggestion. Nothing reaches the board, the registry as a decision, or the client until a person approves on a card, and everything the approval does (`pipeline/decision.py`) is deterministic.
2. **The rules are applied in code too.** `triage/checks.py` re-applies the distribution rules, the taxonomy and the deadline scale to whatever the triager returned, and records every correction as a note the card shows. Do not move a rule back into the prompt only.
3. **Recipients are never a model output.** The card goes to people computed by `cards.card_recipients` (the client's lead, the heads, the forwarding lawyer, the form's responder) and only to the firm's domain; the reply goes to the original sender only, never for forwarded or form-registered demands, and only in the area's reply mode.
4. **Idempotent by construction.** A message id is processed once; a conversation opens one demand; the first decision wins and the second is told who decided; a sweep can run twice and send nothing.
5. **Demo adapters are chosen only in `factory.py`.** Business code receives built services and never reads `DEMO_MODE`. Fixtures are fictional: `.example` domains, invented people, case numbers dated 2099 with invalid check digits.
6. **Portuguese is the clients' language, English is the product's.** The keywords of the filters and the rules-based classifier, the reply draft and the fixture messages are Portuguese because the firm's mail is; the code, the prompts, the console, the docs and the logs are English.

## Conventions

- Python 3.12, `uv`, `ruff` (line length 100, `E501` at 130; the prompt file is exempt because it is prose), `pytest`; tests run offline with the fixture adapters on a temporary SQLite file.
- Area configuration lives in `areas/*.json` and is validated by `areas.py`; the fictional areas shipped here are the documented example.
- Never commit `.env`, `data/`, `.demo/`, `*.sqlite`.
- Commits: English, Conventional Commits, one logical change each, no AI attribution trailers.
