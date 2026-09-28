import json
from datetime import datetime
from pathlib import Path

import pytest

from legal_intake.models import NOT_IDENTIFIED, Complexity, InboundMessage, TriagePackage
from legal_intake.triage.checks import check_package
from legal_intake.triage.claude import ClaudeTriager, TriageError
from legal_intake.triage.fixture import FixtureTriager
from legal_intake.triage.prompts import output_schema, system_prompt, user_message
from legal_intake.triage.rules import RuleTriager
from legal_intake.triage.types import TriageInput

ROOT = Path(__file__).resolve().parents[1]
LOAD = {"Bruno Costa": 4, "Carla Mendes": 6, "Diego Souza": 5, "Elena Prado": 2}


def message(**kw) -> InboundMessage:
    base = dict(
        id="x1",
        conversation_id="c1",
        sender="financeiro@construtora-exemplo.example",
        to=["advisory@lawfirm.example"],
        subject="Revisão de contrato de fornecimento",
        body="Prezados, precisamos que revisem o contrato de fornecimento até sexta.",
        received_at=datetime.fromisoformat("2026-09-18T10:00:00-03:00"),
    )
    base.update(kw)
    return InboundMessage(**base)


def package(**kw) -> TriagePackage:
    base = dict(
        client="Construtora Exemplo",
        client_confidence="high",
        work_type="contract_review",
        summary="s",
        suggested_lawyer="Carla Mendes",
        lawyer_rationale="owner",
        complexity="medium",
        suggested_days=5,
        explicit_deadline=NOT_IDENTIFIED,
        reply_draft="Prezados, retornaremos até [DUE_DATE].",
    )
    base.update(kw)
    return TriagePackage.model_validate(base)


class TestRuleTriager:
    def test_classifies_by_directory_keywords_and_deadline_words(self, advisory):
        out = RuleTriager().triage(
            TriageInput(
                message=message(), area=advisory, body=message().body, forwarded_by=None, load=LOAD
            )
        )
        p = out.package
        assert out.model == "rules"
        assert (p.client, p.client_confidence) == ("Construtora Exemplo", "high")
        assert p.work_type == "contract_review"
        assert p.suggested_lawyer == "Carla Mendes"
        assert p.complexity == Complexity.URGENT  # "até sexta"
        assert p.suggested_days == 1
        assert (
            "[DUE_DATE]" in p.reply_draft and "Example" not in p.reply_draft
        )  # the firm is filled in by the checks

    def test_finds_the_client_in_a_forwarded_body_and_uses_the_forwarder(self, advisory):
        m = message(
            sender="carla.mendes@lawfirm.example",
            subject="ENC: Notificação",
            body="De: juridico@loja-ficticia.example\nQueremos notificar o fornecedor inadimplente.",
        )
        out = RuleTriager().triage(
            TriageInput(message=m, area=advisory, body=m.body, forwarded_by=m.sender, load=LOAD)
        )
        assert out.package.client == "Loja Fictícia"
        assert out.package.work_type == "extrajudicial_notice"
        assert out.package.suggested_lawyer == "Carla Mendes"

    def test_unknown_client_by_name_and_other_type(self, advisory):
        m = message(
            sender="x@somewhere.example",
            subject="Oferta",
            body="Assine hoje o software da Clínica Beta",
        )
        out = RuleTriager().triage(
            TriageInput(message=m, area=advisory, body=m.body, forwarded_by=None, load=LOAD)
        )
        assert (out.package.client, out.package.client_confidence) == ("Clínica Beta", "medium")
        assert out.package.work_type == "other"
        assert out.package.suggested_lawyer == "Elena Prado"


class TestChecks:
    def test_clean_package_passes_untouched(self, advisory):
        p, notes = check_package(
            package(), advisory, forwarded_by=None, load=LOAD, firm_name="Example Law Firm"
        )
        assert notes == [] and p == package()

    def test_owner_overrides_the_model(self, advisory):
        p, notes = check_package(
            package(suggested_lawyer="Elena Prado"),
            advisory,
            forwarded_by=None,
            load=LOAD,
            firm_name="F",
        )
        assert p.suggested_lawyer == "Carla Mendes"
        assert any("rule 'owner' overrides" in n for n in notes)

    def test_unknown_lawyer_type_and_confidence(self, advisory):
        p, notes = check_package(
            package(
                suggested_lawyer="Dr. Nobody",
                work_type="magic",
                client="Empresa Nova",
                client_confidence="high",
            ),
            advisory,
            forwarded_by=None,
            load=LOAD,
            firm_name="F",
        )
        assert p.work_type == "other"
        assert p.suggested_lawyer == "Elena Prado"  # the client is unknown: lowest load
        assert p.client_confidence == "medium"
        assert len(notes) == 3

    def test_unknown_client_falls_to_lowest_load(self, advisory):
        p, notes = check_package(
            package(client=NOT_IDENTIFIED, suggested_lawyer="Dr. Nobody"),
            advisory,
            forwarded_by=None,
            load=LOAD,
            firm_name="F",
        )
        assert p.suggested_lawyer == "Elena Prado"

    def test_days_bounded_and_marker_restored(self, advisory):
        p, notes = check_package(
            package(suggested_days=15, reply_draft="Sem marcador."),
            advisory,
            forwarded_by=None,
            load=LOAD,
            firm_name="Example Law Firm",
        )
        assert p.suggested_days == 5
        assert "[DUE_DATE]" in p.reply_draft and "Example Law Firm" in p.reply_draft
        assert len(notes) == 2

    def test_not_identified_lawyer_gets_the_rule(self, advisory):
        p, notes = check_package(
            package(client=NOT_IDENTIFIED, suggested_lawyer=NOT_IDENTIFIED),
            advisory,
            forwarded_by="diego.souza@lawfirm.example",
            load=LOAD,
            firm_name="F",
        )
        assert p.suggested_lawyer == "Diego Souza" and "forwarder" in notes[0]


class TestFixtureTriager:
    def test_recording_or_fallback(self, advisory):
        t = FixtureTriager(ROOT / "fixtures" / "triage" / "recorded.json")
        m = message(id="m01")
        assert (
            t.triage(
                TriageInput(message=m, area=advisory, body=m.body, forwarded_by=None, load=LOAD)
            ).model
            == "fixture:m01"
        )
        m = message(id="unknown")
        out = t.triage(
            TriageInput(message=m, area=advisory, body=m.body, forwarded_by=None, load=LOAD)
        )
        assert out.model == "rules (no recording)" and out.package.work_type == "contract_review"


class FakeMessages:
    def __init__(self, answer, stop="end_turn"):
        self.answer, self.stop, self.calls = answer, stop, []

    def create(self, **params):
        self.calls.append(params)

        class Block:
            type = "text"
            text = json.dumps(self.answer) if not isinstance(self.answer, str) else self.answer

        class Usage:
            input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = (
                900,
                120,
                800,
                0,
            )

        class Response:
            stop_reason = self.stop
            content = [Block()]
            usage = Usage()

        return Response()


class FakeClient:
    def __init__(self, answer, stop="end_turn"):
        self.messages = FakeMessages(answer, stop)


class TestClaudeTriager:
    def test_call_shape_and_parsing(self, advisory):
        client = FakeClient(package().model_dump(mode="json"))
        t = ClaudeTriager("key", "claude-sonnet-5", "Example Law Firm", client=client)
        m = message()
        out = t.triage(
            TriageInput(message=m, area=advisory, body=m.body, forwarded_by=None, load=LOAD)
        )
        assert out.package.client == "Construtora Exemplo" and out.model == "claude-sonnet-5"
        assert out.usage == {
            "input_tokens": 900,
            "output_tokens": 120,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 0,
        }
        params = client.messages.calls[0]
        assert params["thinking"] == {"type": "disabled"}
        assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert params["output_config"]["format"]["type"] == "json_schema"
        assert (
            params["output_config"]["format"]["schema"]["properties"]["work_type"]["enum"][0]
            == "existing_case"
        )
        assert (
            "CURRENT LOAD" in params["messages"][0]["content"]
            and "Elena Prado: 2" in params["messages"][0]["content"]
        )

    def test_failures(self, advisory):
        m = message()
        item = TriageInput(message=m, area=advisory, body=m.body, forwarded_by=None, load=LOAD)
        with pytest.raises(TriageError, match="cut short"):
            ClaudeTriager(
                "k",
                "m",
                "F",
                client=FakeClient(package().model_dump(mode="json"), stop="max_tokens"),
            ).triage(item)
        with pytest.raises(TriageError, match="declined"):
            ClaudeTriager("k", "m", "F", client=FakeClient({}, stop="refusal")).triage(item)
        with pytest.raises(TriageError, match="does not fit"):
            ClaudeTriager("k", "m", "F", client=FakeClient("not json")).triage(item)
        with pytest.raises(TriageError, match="ANTHROPIC_API_KEY"):
            ClaudeTriager("", "m", "F").triage(item)


class TestPrompts:
    def test_system_prompt_carries_the_area(self, advisory, corporate):
        text = system_prompt(advisory, "Example Law Firm")
        assert "Business Advisory" in text and "@construtora-exemplo.example" in text
        assert "Construtora Exemplo -> Carla Mendes" in text
        assert "[DUE_DATE]" in text and "LOWEST current load" in text
        text2 = system_prompt(corporate, "F")
        assert "WHO FORWARDED" in text2 and "does NOT set the deadline" in text2

    def test_user_message_and_schema(self, advisory):
        m = message()
        text = user_message(
            TriageInput(
                message=m,
                area=advisory,
                body="corpo",
                forwarded_by="x@lawfirm.example",
                load={"A": 1},
            )
        )
        assert (
            "Forwarded by: x@lawfirm.example" in text
            and "- A: 1 open task(s)" in text
            and "corpo" in text
        )
        schema = output_schema(advisory)
        assert "$defs" not in schema and schema["additionalProperties"] is False
        assert schema["properties"]["complexity"]["enum"] == ["urgent", "low", "medium", "high"]
        assert schema["properties"]["suggested_days"]["type"] == "integer"
        assert set(schema["required"]) == set(TriagePackage.model_fields)
