# Demo walkthrough (about five minutes)

Everything runs offline. No API key, no Microsoft 365 tenant, no network. `DEMO_MODE=true` swaps the mailbox for a fixture inbox of fourteen messages, the triager for recorded readings (with a rules-based fallback), the board and the registry for SQLite under `.demo/`, and the mailer for one that writes every card and reply to `.demo/outbox/`. "Today" is pinned to **Monday 2026-09-21**.

```bash
uv sync
cp .env.example .env          # DEMO_MODE=true already
```

## 1. The sweep

```bash
uv run intake --demo sweep
```

The fourteen messages of the intake mailbox take their routes:

| Message | Route | Why |
|---|---|---|
| A client of Business Advisory asks for a contract review | demand → card to **Bruno Costa** | the client's lead in the directory; the portfolio owner (Carla) is suggested |
| An unknown company asks for a services agreement | demand → card to the two heads | no lead; the lowest load (Elena) is suggested |
| Carla forwards a client's request for a notice (`ENC:`) | demand → card to Bruno | forwarded demands are registered; the forwarder is suggested; no reply to the client |
| The form's e-mail for a WhatsApp contact (`[Forms/WhatsApp] ... por diego.souza@`) | demand → card to **Diego** | the channel comes from the subject, the card goes back to the responder |
| Ana's team-meeting e-mail | skipped | an internal message that is not a forward |
| A newsletter from `noreply@` | skipped | auto-generated sender |
| An out-of-office auto-reply | skipped | automatic reply |
| The client's second message in the first thread | duplicate | one conversation, one demand |
| "URGENTE: hearing tomorrow" from a client with a portfolio owner | demand → card to Ana | urgent, one business day, the owner (Diego) suggested |
| Carla's reply to a client with the intake account in copy (thread of a seeded demand) | **closes** `d-seed-1` | internal sender, known thread, demand in execution: the real reply date is recorded |
| A client's reply in the other seeded thread | duplicate | a client's reply never closes a demand |
| Igor forwards a shareholders' agreement request to the corporate list | demand → card to **Igor** | in this area whoever forwards decides |
| A client writes straight to the corporate list | demand → card to the head (Helena) | the card never goes outside the firm |
| A marketing e-mail | demand (type `other`) → card to the heads | it passed the filters; the head discards it |

Run the sweep again: `already_processed=14`, nothing sent. The demand ids are stable (a hash of the message id), so the commands below work as written.

## 2. The cards

`uv run intake --demo pending` lists the eight demands awaiting a decision with the package each card carries. Every card is in `.demo/outbox/` as the recipient's mail client would render it (the Adaptive Card JSON inside the HTML, with a text fallback linking to the console).

Or open the console: `uv run intake --demo serve` and http://127.0.0.1:8000/cards. The demo is open (no password); the sign-in only asks who you are, so the decision carries a name.

## 3. Decide

```bash
# as suggested: five business days, the portfolio owner, a draft reply to the team mailbox
uv run intake --demo decide d-0f44ab69 --approve --by bruno.costa@lawfirm.example

# adjusted: the head names the new client and picks another lawyer (counts in the adjustment rate)
uv run intake --demo decide d-634ff991 --approve --by ana.ribeiro@lawfirm.example --client "Empresa Nova" --lawyer "Diego Souza"

# urgent: due tomorrow
uv run intake --demo decide d-3cb294d4 --approve --by ana.ribeiro@lawfirm.example

# corporate: the forwarder decides, adds an internal review of two days; ten + two business days
uv run intake --demo decide d-13aeee51 --approve --by igor.lima@lawfirm.example --reviewer "Helena Duarte" --review-days 2

# the marketing e-mail
uv run intake --demo decide d-e68250dc --discard --by ana.ribeiro@lawfirm.example

# the race: a second decision on the first demand
uv run intake --demo decide d-0f44ab69 --discard --by ana.ribeiro@lawfirm.example
```

The last command answers `already decided by bruno.costa@lawfirm.example`: the first decision wins. Each approval created a task in the client's bucket (`Empresa Nova` was created on the fly), assigned, labelled, with the type's checklist and a description carrying the summary and the reply with the real date; the drafts for the team's mailbox are in the outbox.

## 4. Close

```bash
uv run intake --demo show d-8ddef8e8            # the notice for Loja Fictícia, still awaiting
uv run intake --demo decide d-8ddef8e8 --approve --by bruno.costa@lawfirm.example
uv run intake --demo complete-task <task id printed above>   # the lawyer marks it done on the board
uv run intake --demo sync-board                  # closed from the board, no reply date
```

The first sweep already showed the other path: Carla's reply with the intake account in copy closed a demand with the real reply date.

## 5. Measure

```bash
uv run intake --demo stats
uv run intake --demo sla --history fixtures/sla/history.csv
uv run python scripts/eval.py
```

`stats` prints, per area, the adjustment rate and which fields were adjusted, the average hours to a decision, the same-day replies, the closings by e-mail versus board, on-time versus late, the overdue tasks and each lawyer's load; the console's dashboard shows the same. `sla` builds the standard-deadline matrix from a synthetic history of 210 completed tasks, classifying the titles by the keyword rules (median, P80, the P80 rounded up as the standard, thin samples flagged). `eval.py` checks every route of the inbox and measures the rules-based baseline against the recorded readings.

Delete `.demo/` (or `uv run intake reset`) to start over.
