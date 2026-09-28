# The flow, step by step

The original ran as Power Automate flows around a shared mailbox, Microsoft Lists, Planner and Teams or Outlook cards. This document is the same design as the code implements it, so that someone comparing the two, or wiring the real adapters, finds every step.

## 1. Entry: what counts as a demand

The intake account (`INTAKE_MAILBOX`) is a member of each area's group and receives every message sent to the area's address. A message is routed to an area when the area's `intake_address` is among its recipients (`areas.area_for`). Two shapes exist in the shipped configuration:

- **Business Advisory**: the team's mailbox is the intake address. Clients write to it; lawyers forward what reached their personal inbox.
- **Corporate & M&A**: the intake address is a separate list (`corporate.intake@`) that only the automation reads. Nothing reaches the team's own mailbox through the funnel; the single gesture of the team is *forward the client's e-mail to the list*. A client who writes to the list directly still opens a demand, but the card goes to the head.

Demands that do not arrive by e-mail (WhatsApp, phone, a meeting) are registered through a short form. The form's own flow sends an e-mail to the area from the intake account with the subject `[Forms/<channel>] Demand registered by <responder e-mail>`; the sweep reads the channel from the subject and sends the card back to the responder. The rule of the house, kept from the original: a demand that is not in the funnel does not exist.

## 2. Filters and routes (`filters.py`)

Before any model call, in this order:

| Condition | Route |
|---|---|
| sender contains `noreply`, `no-reply`, `mailer-daemon`, `postmaster`, `donotreply` | skip: auto-generated |
| subject starts with an auto-reply marker (Portuguese and English) | skip: automatic reply |
| subject starts with `[Forms/` from the intake account or an internal sender | demand, channel from the subject, "forwarded by" the responder |
| subject starts with `[Forms/` from an external sender | skip (a forged form) |
| internal sender with a forward prefix (`ENC:`, `FW:`, `Fwd:`, `RES:`) | demand, "forwarded by" the sender |
| internal sender, anything else | closing candidate (a reply in a thread, see 7), else skip |
| external sender | demand |

## 3. Deduplication

One conversation, one demand. A message whose conversation id already has a demand is a reply in the thread: from an internal sender it may close the demand (7); from the client it is ignored. Processed message ids are recorded, so a sweep can run every fifteen minutes and a missed run is recovered by the lookback without double work.

## 4. Triage

The body is converted to plain text and cut at `MAX_BODY_CHARS`. The lawyers' current load (open tasks per assignee on the area's plan) is read from the board. The triager receives the message, the area and the load and returns the decision package: client and confidence, work type from the area's taxonomy, an executive summary, the suggested lawyer with a rationale, the complexity, the suggested business days, any explicit deadline in the text, and a reply draft with the `[DUE_DATE]` marker.

The Claude triager uses one call with a structured output enforced by the package's schema (the taxonomy is the enum), a system prompt per area that is stable across calls (prompt caching) with the dynamic load in the user message, and thinking off (a short deterministic classification). The rules-based triager does the same job with keywords and the directory; it is the baseline of the evaluation and the demo's fallback.

## 5. Checks (`triage/checks.py`)

Whatever prepared the package, the code re-applies the rules and records every correction as a note the card shows:

- a work type outside the taxonomy becomes `other`;
- a client the directory does not know cannot have high confidence;
- the suggested lawyer must be in the area, and the deterministic suggestion (portfolio owner, then the forwarding lawyer, then the lowest load) overrides a different one when the rule is the owner's or the forwarder's;
- the days are bounded by the scale of the complexity;
- a reply without the `[DUE_DATE]` marker is replaced by the template.

## 6. The card

The demand is written to the registry as *awaiting validation* with every `ai_*` field, and the card is sent as a reply in the demand's own conversation, so it lands next to the e-mail it is about. Recipients are computed, never taken from the model:

- **heads mode**: the client's lead in the directory; without one, the heads (the first answer decides);
- **forwarder mode**: the forwarding lawyer, or the form's responder, when they are lawyers of the area; anyone else, and any external sender, goes to the head;
- every recipient is on the firm's domain by construction.

The card is an Adaptive Card 1.4 with the suggestions as default values of editable inputs (client, a free-text client for one not listed, type, lawyer, complexity, days, reviewer and internal days where the area reviews internally, the reply where the area replies), and Approve / Discard actions. Clients that do not render it see a text fallback with a link to the console's form for the same decision.

## 7. The decision (`pipeline/decision.py`)

The first decision wins; a second one is answered with who decided. On approval:

1. the final fields are the person's choices or the suggestions; `adjusted` is true when any of client, type, lawyer, complexity or days differs from the suggestion (the adjustment rate);
2. the effective days are the person's number when they changed it, else the scale of the final complexity (in an area where complexity does not set the deadline, the suggestion stands), plus the internal review days when a reviewer was chosen;
3. the due date is that many business days after the decision, with national and state holidays;
4. the task is created on the area's plan, in the client's bucket (created when missing, matched case- and space-insensitively so a typed name does not duplicate one), titled `[client] type — subject`, assigned to the lawyer, due on that date, labelled with the type's label, with the type's checklist, and a description carrying the summary, the reply with the real date, the internal-review line and the link to the e-mail;
5. the demand becomes *in execution* with the task id;
6. the reply to the client: only if the area replies (`draft` to the team's mailbox with a review prefix, or `send` from the area's mailbox), only for a demand that came by e-mail and was not forwarded or registered by the team, and only to the original sender.

On discard the demand is kept as *discarded*: what arrived stays recorded.

## 8. Closing

**By e-mail** (the rule the team learns: *answer the client in the same conversation and copy the intake account*): a message from an internal sender in the thread of a demand in execution closes it with the real reply date (`replied_at`), the source of the response-time KPI, and completes the task.

**By the board** (the safety net): a periodic sync closes any demand in execution whose task is complete, without a reply date. The dashboard shows the share of closings that came this way: the gap in the team's adherence to the copy rule.

## 9. Metrics (`pipeline/metrics.py`)

Per area: demands by status, channel, type and client; the adjustment rate and which fields were adjusted; average hours from arrival to decision; replies on the same day; closings by e-mail versus board; tasks closed on time versus late; overdue now; open tasks by lawyer. The console renders them; `intake stats` prints them.

## 10. The SLA matrix (`sla.py`)

Quarterly, offline: completed tasks of the plan (or a CSV export) are classified in the taxonomy by the keyword rules or by a small model through the Message Batches API, their durations are measured in business days, and the median and the 80th percentile are computed per type. The P80 rounded up is the proposed standard; thin samples are flagged for review; the medians go into the area's `sla_reference`, which the prompt quotes as the historical reference. Heads validate the matrix before it is pasted.
