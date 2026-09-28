"""What the code checks and corrects in a package, whoever prepared it.

The model is asked to follow the directory and the distribution rules; here they are
applied again: a work type outside the taxonomy becomes `other`; a lawyer outside the list,
or a lawyer other than the client's portfolio owner, is replaced by the deterministic
suggestion; the days are bounded by the scale; a reply without the date marker gets the
template. Every correction is a note that travels with the demand to the card."""

from __future__ import annotations

from ..areas import Area
from ..models import DUE_DATE_MARKER, NOT_IDENTIFIED, TriagePackage
from ..suggest import suggest_lawyer


def check_package(
    package: TriagePackage,
    area: Area,
    *,
    forwarded_by: str | None,
    load: dict[str, int],
    firm_name: str,
) -> tuple[TriagePackage, list[str]]:
    notes: list[str] = []
    data = package.model_dump()

    if area.work_type(data["work_type"]) is None:
        notes.append(f"work type '{data['work_type']}' is not in the taxonomy: set to 'other'")
        data["work_type"] = "other"

    # a name the directory does not know stays visible, but its confidence cannot be high
    if (
        data["client"] != NOT_IDENTIFIED
        and area.client_by_name(data["client"]) is None
        and data["client_confidence"] == "high"
    ):
        notes.append(
            f"client '{data['client']}' is not in the directory: confidence lowered to medium"
        )
        data["client_confidence"] = "medium"

    suggestion = suggest_lawyer(
        area, client_name=data["client"], forwarded_by=forwarded_by, load=load
    )
    if (
        data["suggested_lawyer"] != NOT_IDENTIFIED
        and area.lawyer_by_name(data["suggested_lawyer"]) is None
    ):
        notes.append(
            f"suggested lawyer '{data['suggested_lawyer']}' is not in the area:"
            f" replaced by {suggestion.lawyer} ({suggestion.rationale})"
        )
        data["suggested_lawyer"], data["lawyer_rationale"] = suggestion.lawyer, suggestion.rationale
    elif (
        suggestion.rule in ("owner", "forwarder") and data["suggested_lawyer"] != suggestion.lawyer
    ):
        notes.append(
            f"rule '{suggestion.rule}' overrides the suggestion: {data['suggested_lawyer']}"
            f" -> {suggestion.lawyer} ({suggestion.rationale})"
        )
        data["suggested_lawyer"], data["lawyer_rationale"] = suggestion.lawyer, suggestion.rationale
    elif data["suggested_lawyer"] == NOT_IDENTIFIED and suggestion.lawyer != NOT_IDENTIFIED:
        notes.append(f"no lawyer suggested: {suggestion.lawyer} by rule '{suggestion.rule}'")
        data["suggested_lawyer"], data["lawyer_rationale"] = suggestion.lawyer, suggestion.rationale

    scale_days = area.deadline_scale[data["complexity"]]
    if data["suggested_days"] > scale_days:
        notes.append(
            f"suggested days {data['suggested_days']} exceed the scale for {data['complexity']} ({scale_days}): bounded"
        )
        data["suggested_days"] = scale_days
    if data["suggested_days"] < 1:
        notes.append("suggested days below one: set to one")
        data["suggested_days"] = 1

    if DUE_DATE_MARKER not in data["reply_draft"]:
        notes.append("reply draft without the [DUE_DATE] marker: replaced by the template")
        name = data["client"] if data["client"] != NOT_IDENTIFIED else "cliente"
        data["reply_draft"] = (
            f"Prezado(a) {name},\n\nConfirmamos o recebimento da sua solicitação. "
            f"Nossa equipe já está analisando o pedido e retornaremos até {DUE_DATE_MARKER}.\n\n"
            f"Permanecemos à disposição.\n\nEquipe {area.name} — {firm_name}"
        )
    data["reply_draft"] = data["reply_draft"].replace("{firm}", firm_name)

    return TriagePackage.model_validate(data), notes
