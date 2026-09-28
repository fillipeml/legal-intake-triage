"""The prompt of the triage. The system block is stable per area (it is what prompt caching
caches): the taxonomy, the deadline scale, the client directory and the lawyer list. The
dynamic part (the message and the lawyers' current load) goes in the user message."""

from __future__ import annotations

from ..areas import Area
from ..models import DUE_DATE_MARKER, NOT_IDENTIFIED, Complexity
from .types import TriageInput


def _taxonomy_block(area: Area) -> str:
    return "\n".join(f"- `{t.slug}`: {t.title}" for t in area.taxonomy)


def _scale_block(area: Area) -> str:
    s = area.deadline_scale
    lines = [
        f'- `urgent`: {s[Complexity.URGENT]} business day. ONLY when an external deadline falls within two business days ("today", "tomorrow", "due Friday") or damage is under way. "Next week" is NOT urgent.',
        f"- `low`: {s[Complexity.LOW]} business days. A quick consultation, a short standard document, something one lawyer resolves in one sitting.",
        f"- `medium`: {s[Complexity.MEDIUM]} business days. A typical contract to review or draft, an ordinary notice, work that needs reading documents but no multiple parties or theses.",
        f"- `high`: {s[Complexity.HIGH]} business days. A formal opinion, a long or atypical contract, several parties or documents, a new thesis, research in stages.",
    ]
    if area.sla_reference:
        ref = "; ".join(
            f"{area.work_type(k).title if area.work_type(k) else k} about {v:g}"
            for k, v in area.sla_reference.items()
        )
        lines.append(
            f"\n(Historical reference of the area, in business days, to calibrate the judgement: {ref}.)"
        )
    if not area.complexity_sets_deadline:
        lines.append(
            "\nIn this area the complexity does NOT set the deadline: it only guides the suggestion. The lawyer sets the deadline on the card."
        )
    return "\n".join(lines)


def _clients_block(area: Area) -> str:
    if not area.clients:
        return "(no client directory: identify by the name in the message and mark the confidence accordingly)"
    rows = []
    for c in area.clients:
        keys = ", ".join([f"@{d}" for d in c.domains] + c.emails) or "no domain on record"
        rows.append(f"- {c.name} ({keys})")
    return "\n".join(rows)


def _lawyers_block(area: Area) -> str:
    rows = [
        f"- {lw.name}"
        + (f" ({lw.specialties})" if lw.specialties else "")
        + ("" if lw.receives_distribution else " [does not receive distribution]")
        for lw in area.lawyers
    ]
    owners = [f"- {c.name} -> {c.owner}" for c in area.clients if c.owner]
    text = "\n".join(rows)
    if owners:
        text += "\n\nPortfolio owners (client -> lawyer):\n" + "\n".join(owners)
    return text


def _distribution_rule(area: Area) -> str:
    if area.validation == "forwarder":
        return (
            "Rule of suggestion: suggest the lawyer WHO FORWARDED the demand (the internal sender). "
            "Every demand of this area arrives forwarded by one of its lawyers; the portfolio table is not used. "
            "Never suggest a name outside the list."
        )
    return (
        "The demand comes with the CURRENT LOAD of each lawyer (open tasks on the board). Rule of suggestion, in this order:\n"
        "1. A client with a portfolio owner in the table -> suggest that lawyer, always. The portfolio is the house rule; load does not override it. Cite the rule in the rationale.\n"
        "2. A client without an owner (or not identified) -> suggest the lawyer with the LOWEST current load among those who receive distribution; break ties by the closest specialty. Cite the load in the rationale.\n"
        "Never suggest a name outside the list."
    )


def system_prompt(area: Area, firm_name: str) -> str:
    return f"""You are the intake assistant of {firm_name}, a Brazilian law firm. You read demands that reach the mailbox of the practice area "{area.name}" and prepare a DECISION PACKAGE for a person to approve.

You do NOT decide and do NOT answer the client: you prepare. The person who validates has full control; your job is to remove their typing.

## Work types (the area's taxonomy)

Classify each demand in exactly one type:

{_taxonomy_block(area)}

## Complexity and deadline

Classify the complexity in exactly one grade; the area's scale turns it into business days:

{_scale_block(area)}

If the text carries an explicit or implicit deadline SHORTER than the scale ("the hearing is on the 15th", "I need it by Friday"), the suggested days must respect it, and the grade must be reconsidered (a close external deadline tends to `urgent`).

## Clients of the area

Known clients (identify by the sender, the domain, the signature or the body; for a forwarded message, by the ORIGINAL sender in the forwarded content, never by the lawyer who forwarded):

{_clients_block(area)}

Confidence: a match by a registered domain or e-mail = high; by name or signature = medium; a guess = low. A client not in the directory is "{NOT_IDENTIFIED}" (write the name you read in the summary).

## Lawyers of the area

{_lawyers_block(area)}

{_distribution_rule(area)}

## Forwarded demands

A demand forwarded by a lawyer (subject ENC:/FW:/RES:, internal sender) or registered through the form: identify the REAL client in the forwarded content; the forwarding lawyer probably owns the relationship, so suggest them when the client has no owner; address the reply draft to the client (the lawyer decides whether to use it).

## Reply draft

Write a short e-mail (three to six sentences) in Brazilian Portuguese, in the firm's tone (formal, cordial, direct, no needless legalese), confirming receipt and stating the return date:

1. a nominal greeting ("Prezado(a) [nome],");
2. confirmation of receipt with a specific reference to the subject;
3. the return date written literally as "retornaremos até {DUE_DATE_MARKER}": use exactly the marker {DUE_DATE_MARKER}, never a date or a number of days (the system computes the exact business date and replaces it);
4. closing: "Permanecemos à disposição." and the signature "Equipe {area.name} — {firm_name}".

Do not promise a result, do not anticipate the merits, do not mention amounts.

## Inviolable rules

- Never invent. A field without information in the text = "{NOT_IDENTIFIED}".
- The summary has at most three sentences and spares re-reading the thread.
- A message that is clearly not a legal demand (spam, marketing, a notification that slipped through the filters): type `other`, complexity `low`, and say so in the summary.
- Answer only with the JSON the schema requires."""


def user_message(item: TriageInput) -> str:
    load = (
        "\n".join(f"- {name}: {n} open task(s)" for name, n in sorted(item.load.items()))
        or "- (no load information)"
    )
    forwarded = f"\nForwarded by: {item.forwarded_by}" if item.forwarded_by else ""
    return (
        f"NEW DEMAND RECEIVED\n\nFrom: {item.message.sender}\nSubject: {item.message.subject}\n"
        f"Received at: {item.message.received_at.isoformat()}{forwarded}\n\n"
        f"CURRENT LOAD OF THE LAWYERS (open tasks on the board):\n{load}\n\n"
        f"Body of the message:\n{item.body}"
    )


def output_schema(area: Area) -> dict:
    """The JSON schema of the package with the area's taxonomy as the enum of `work_type`."""
    from ..models import TriagePackage

    schema = TriagePackage.model_json_schema()
    schema["properties"]["work_type"]["enum"] = [t.slug for t in area.taxonomy]
    schema["additionalProperties"] = False
    # inline the enums pydantic puts under $defs: structured outputs want a flat object
    defs = schema.pop("$defs", {})
    for name, prop in schema["properties"].items():
        ref = prop.pop("$ref", None)
        if ref:
            target = defs[ref.split("/")[-1]]
            prop["type"] = "string"
            prop["enum"] = target["enum"]
        if "allOf" in prop:
            target = defs[prop.pop("allOf")[0]["$ref"].split("/")[-1]]
            prop["type"] = "string"
            prop["enum"] = target["enum"]
        prop.pop("title", None)
        if name == "suggested_days":
            prop["type"] = "integer"
    schema.pop("title", None)
    return schema
