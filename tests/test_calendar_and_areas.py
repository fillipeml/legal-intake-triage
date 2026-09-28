from datetime import date

import pytest

from legal_intake.areas import Area, area_for, load_areas
from legal_intake.business_days import (
    add_business_days,
    business_days_between,
    date_br,
    is_business_day,
)
from legal_intake.models import NOT_IDENTIFIED
from legal_intake.suggest import suggest_lawyer


def test_business_days_skip_weekends_and_holidays():
    monday = date(2026, 9, 21)
    assert add_business_days(monday, 1) == date(2026, 9, 22)
    assert add_business_days(monday, 5) == date(2026, 9, 28)  # a full week later
    # 12 October 2026 (Monday) is a national holiday
    assert not is_business_day(date(2026, 10, 12))
    assert add_business_days(date(2026, 10, 9), 1) == date(2026, 10, 13)
    assert add_business_days(monday, 0) == monday
    assert business_days_between(monday, date(2026, 9, 28)) == 5
    assert business_days_between(monday, monday) == 0
    assert date_br(monday) == "21/09/2026"


def test_areas_load_and_lookups(advisory: Area, corporate: Area):
    assert advisory.work_type("contract_review").title == "Contract review"
    assert advisory.lawyer_by_name("carla mendes").email == "carla.mendes@lawfirm.example"
    assert advisory.lawyer_by_email("CARLA.MENDES@lawfirm.example").name == "Carla Mendes"
    assert advisory.client_for("x@construtora-exemplo.example").name == "Construtora Exemplo"
    assert advisory.client_for("founder@alfa-founders.example").name == "Startup Alfa"
    assert advisory.client_for("x@unknown.example") is None
    assert [lw.name for lw in advisory.distribution()] == [
        "Bruno Costa",
        "Carla Mendes",
        "Diego Souza",
        "Elena Prado",
    ]
    assert corporate.validation == "forwarder" and corporate.reply_mode == "none"
    assert (
        corporate.internal_review.enabled and "Helena Duarte" in corporate.internal_review.reviewers
    )


def test_area_routing(services):
    assert area_for(services.areas, ["advisory@lawfirm.example"]).key == "advisory"
    assert (
        area_for(services.areas, ["x@lawfirm.example", "corporate.intake@lawfirm.example"]).key
        == "corporate"
    )
    assert (
        area_for(services.areas, ["corporate@lawfirm.example"]) is None
    )  # the team's box is not the intake address
    assert area_for(services.areas, ["intake@lawfirm.example"]) is None


def test_area_validation_rejects_inconsistencies(advisory: Area):
    raw = advisory.model_dump()
    raw["clients"][0]["owner"] = "Nobody"
    with pytest.raises(ValueError, match="unknown lawyer"):
        Area.model_validate(raw)
    raw = advisory.model_dump()
    raw["taxonomy"] = [t for t in raw["taxonomy"] if t["slug"] != "other"]
    with pytest.raises(ValueError, match="'other'"):
        Area.model_validate(raw)


def test_load_areas_requires_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_areas(tmp_path)


def test_suggestion_rules(advisory: Area):
    load = {"Bruno Costa": 4, "Carla Mendes": 6, "Diego Souza": 5, "Elena Prado": 2}
    owner = suggest_lawyer(
        advisory, client_name="Construtora Exemplo", forwarded_by=None, load=load
    )
    assert (owner.lawyer, owner.rule) == ("Carla Mendes", "owner")
    forwarder = suggest_lawyer(
        advisory, client_name="Loja Fictícia", forwarded_by="bruno.costa@lawfirm.example", load=load
    )
    assert (forwarder.lawyer, forwarder.rule) == ("Bruno Costa", "forwarder")
    # the owner beats the forwarder
    both = suggest_lawyer(
        advisory,
        client_name="Construtora Exemplo",
        forwarded_by="bruno.costa@lawfirm.example",
        load=load,
    )
    assert both.lawyer == "Carla Mendes"
    lowest = suggest_lawyer(advisory, client_name=NOT_IDENTIFIED, forwarded_by=None, load=load)
    assert (lowest.lawyer, lowest.rule) == ("Elena Prado", "load")
    assert "2" in lowest.rationale
    tie = suggest_lawyer(
        advisory, client_name="Clínica Beta", forwarded_by="stranger@lawfirm.example", load={}
    )
    assert tie.lawyer == "Bruno Costa"  # everyone at zero: alphabetical
