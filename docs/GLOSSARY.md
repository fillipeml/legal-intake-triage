# Glossary

Operational terms behind the English identifiers, and the Portuguese that stays in the fixtures, the filters and the reply draft on purpose.

## The operation

| Term | Meaning |
|---|---|
| Front door, intake | The single entry of a practice area's demands: an e-mail address per area, plus a form for what arrives by WhatsApp, phone or meeting. A demand outside the funnel does not exist. |
| Area | A practice team (Business Advisory, Corporate & M&A in the shipped configuration) with its own mailbox, heads, taxonomy, lawyers and clients. |
| Head | The lawyer who leads an area and validates its demands when no lead is defined for the client. |
| Lead (of a client) | The lawyer who validates the demands of one client; the card goes to them. |
| Portfolio owner | The lawyer responsible for a client's work; rule one of distribution. |
| Distribution | Who a demand is suggested to: the owner, else the forwarding lawyer, else the lawyer with the lowest current load. |
| Decision package | What the triage prepares: client, type, summary, lawyer, complexity, days, explicit deadline, reply draft. |
| Card | The Adaptive Card with the package pre-filled in editable fields, sent as a reply in the demand's thread; also a web form in the console. |
| Adjustment rate | The share of decided demands where the person changed at least one of client, type, lawyer, complexity or days. The metric the original ran the pilot on. |
| Registry, master record | One row per demand with the `ai_*` (suggested) and `final_*` (decided) fields, statuses and closing data; a SharePoint list in the original, SQLite here. |
| Board | The team's task board: Planner in the original, SQLite in the demo. Buckets are clients; labels are work types; every task carries the type's checklist. |
| Closing by e-mail | The lawyer answers the client in the same thread with the intake account in copy: the demand closes with the real reply date. |
| Closing by the board | The task was completed but no copy was sent: a periodic sync closes the demand without a reply date. The share of these is the adherence gap. |
| SLA matrix | Median and 80th percentile of the business-day duration per (area, work type), from the board's history; the P80 rounded up is the standard deadline. |
| Dry run | The sweep reads and triages but sends nothing: the shadow mode before go-live. |

## Kept in Portuguese

| Where | Why |
|---|---|
| `ENC:`, `RES:` (with `FW:`, `Fwd:`) | Outlook's Portuguese forward and reply prefixes; the filters must match the firm's mail as it is. |
| `Resposta Automática`, `ausência` | Auto-reply subjects in Portuguese, beside the English ones. |
| Keywords of the taxonomies (`contestação`, `notificação extrajudicial`, `parecer`, `minuta`, `acordo de sócios`...) | The rules-based classifier reads Portuguese titles and bodies. |
| `Prezado(a)`, `retornaremos até`, `Permanecemos à disposição` | The firm's tone in the acknowledgement to the client. |
| `[Forms/WhatsApp] Demanda registrada por ...` | The subject the form's flow produces; the channel names are as the form offers them. |
| The fixture messages | A Brazilian firm's mail, invented but in the language it would have. |

## Legal terms in the fixtures

| Term | Meaning |
|---|---|
| Contestação | The defendant's answer in a lawsuit. |
| Notificação extrajudicial | A formal out-of-court notice, often before a lawsuit. |
| Parecer | A written legal opinion. |
| Minuta, aditivo, distrato, procuração | A draft, an amendment, a termination agreement, a power of attorney. |
| Acordo de sócios, alteração do contrato social, ata de assembleia | Shareholders' agreement, amendment of the articles of association, minutes of a shareholders' meeting. |
| Due diligence, diagnóstico | The structured review of a company's legal situation. |
| Junta Comercial | The commercial registry where corporate acts are filed. |
| Audiência de conciliação | A conciliation hearing in a lawsuit. |
