import json
from datetime import date, datetime

from legal_intake.board.sqlite import SQLiteBoard
from legal_intake.cards import build_card, card_html, card_recipients
from legal_intake.models import NOT_IDENTIFIED, Demand
from legal_intake.registry.sqlite import SQLiteRegistry
from legal_intake.sla import (
    HistoryRow,
    build_matrix,
    classify_by_batch,
    classify_by_rules,
    history_from_tasks,
    matrix_as_reference,
    percentile,
)

AT = datetime.fromisoformat("2026-09-21T09:00:00-03:00")


def demand(**kw) -> Demand:
    base = dict(
        id="d-1",
        area="advisory",
        subject="S",
        channel="email",
        sender="c@x.example",
        conversation_id="conv",
        message_id="m",
        received_at=AT,
    )
    base.update(kw)
    return Demand.model_validate(base)


class TestStorage:
    def test_registry_roundtrip(self, tmp_path):
        r = SQLiteRegistry(str(tmp_path / "s.sqlite"))
        r.create(demand())
        assert (
            r.get("d-1").subject == "S"
            and r.by_conversation("conv").id == "d-1"
            and r.by_conversation("x") is None
        )
        d = r.get("d-1")
        d.board_task_id = "t-9"
        r.update(d)
        assert r.by_task("t-9").id == "d-1"
        assert [x.id for x in r.list(area="advisory")] == ["d-1"] and r.list(area="corporate") == []
        assert not r.message_processed("m")
        r.record_message("m", result="registered", received_at=AT)
        assert r.message_processed("m") and r.processed_messages()[0]["result"] == "registered"

    def test_board_roundtrip(self, tmp_path):
        b = SQLiteBoard(str(tmp_path / "s.sqlite"))
        assert b.buckets("p") == []
        assert (
            b.ensure_bucket("p", "Client A") == "Client A"
            and b.ensure_bucket("p", " client a ") == "Client A"
        )
        t = b.create_task(
            plan="p",
            bucket="Client A",
            title="T",
            assignee="Ana",
            due_date=date(2026, 9, 25),
            description="d",
            checklist=["a", "b"],
            label="category1",
            demand_id="d-1",
            created_at=AT,
        )
        assert b.get(t.id).checklist == ["a", "b"] and b.open_tasks_by_assignee("p") == {"Ana": 1}
        b.complete(t.id, AT)
        assert (
            b.get(t.id).percent_complete == 100
            and b.open_tasks_by_assignee("p") == {}
            and len(b.list_tasks("p")) == 1
        )
        assert b.get("nope") is None


class TestCards:
    def test_recipients_rules(self, services, advisory, corporate):
        s = services.settings
        assert card_recipients(
            advisory,
            s,
            sender="x@construtora-exemplo.example",
            subject="S",
            client_name="Construtora Exemplo",
            forwarded_by=None,
        ) == ["bruno.costa@lawfirm.example"]
        assert (
            card_recipients(
                advisory,
                s,
                sender="x@y.example",
                subject="S",
                client_name=NOT_IDENTIFIED,
                forwarded_by=None,
            )
            == advisory.heads
        )
        assert card_recipients(
            advisory,
            s,
            sender="intake@lawfirm.example",
            subject="[Forms/Telefone] Demanda registrada por elena.prado@lawfirm.example",
            client_name=NOT_IDENTIFIED,
            forwarded_by="elena.prado@lawfirm.example",
        ) == ["elena.prado@lawfirm.example"]
        assert (
            card_recipients(
                advisory,
                s,
                sender="intake@lawfirm.example",
                subject="[Forms/Telefone] Demanda registrada por hacker@evil.example",
                client_name=NOT_IDENTIFIED,
                forwarded_by=None,
            )
            == advisory.heads
        )
        assert card_recipients(
            corporate,
            s,
            sender="igor.lima@lawfirm.example",
            subject="ENC: x",
            client_name="Grupo Gama",
            forwarded_by="igor.lima@lawfirm.example",
        ) == ["igor.lima@lawfirm.example"]
        assert card_recipients(
            corporate,
            s,
            sender="someone.else@lawfirm.example",
            subject="ENC: x",
            client_name="Grupo Gama",
            forwarded_by="someone.else@lawfirm.example",
        ) == ["helena.duarte@lawfirm.example"]
        assert card_recipients(
            corporate,
            s,
            sender="ceo@grupo-gama.example",
            subject="x",
            client_name="Grupo Gama",
            forwarded_by=None,
        ) == ["helena.duarte@lawfirm.example"]

    def test_card_json_and_html(self, advisory, corporate):
        d = demand(
            ai_client="Construtora Exemplo",
            ai_work_type="contract_review",
            ai_lawyer="Carla Mendes",
            ai_days=5,
            triage_notes=["a note"],
        )
        card = build_card(d, advisory)
        ids = [b.get("id") for b in card["body"] if b.get("type", "").startswith("Input.")]
        assert ids == [
            "client",
            "client_other",
            "work_type",
            "lawyer",
            "complexity",
            "days",
            "reply",
        ]
        actions = card["body"][-1]["actions"]
        assert actions[0]["data"] == {"action": "approve", "demand_id": "d-1", "area": "advisory"}
        assert any("Checks: a note" in b.get("text", "") for b in card["body"])
        corp = build_card(demand(area="corporate", ai_work_type="consulting"), corporate)
        corp_ids = [b.get("id") for b in corp["body"] if b.get("type", "").startswith("Input.")]
        assert "reviewer" in corp_ids and "review_days" in corp_ids and "reply" not in corp_ids
        html = card_html(card, d, "http://console")
        assert "application/adaptivecard+json" in html and "http://console/cards/d-1" in html
        assert json.loads(html.split('+json">', 1)[1].split("</script>", 1)[0])["version"] == "1.4"


class TestSla:
    def test_percentile_and_matrix(self):
        assert (
            percentile([1, 2, 3, 4, 5], 0.8) == 4.2
            and percentile([], 0.5) == 0.0
            and percentile([7], 0.8) == 7.0
        )
        rows = [HistoryRow("a", "t", date(2026, 9, 1), date(2026, 9, 8), "x") for _ in range(6)] + [
            HistoryRow("a", "t", date(2026, 9, 1), date(2026, 9, 3), "y")
        ]
        matrix = build_matrix(rows)
        assert [(m.work_type, m.sample, m.review, m.standard_days) for m in matrix] == [
            ("x", 6, False, 4),  # 7 September is a national holiday
            ("y", 1, True, 2),
        ]
        assert matrix_as_reference(matrix, "a") == {"x": 4.0}

    def test_rules_and_history(self, advisory, services):
        assert classify_by_rules("Parecer sobre garantia — Cliente", advisory) == "legal_opinion"
        assert classify_by_rules("Reunião com o cliente", advisory) == "other"
        rows = history_from_tasks(services.board.list_tasks("advisory-weekly"), advisory)
        assert len(rows) == 6 and all(r.duration >= 1 for r in rows)

    def test_batch_classification_with_a_fake_client(self, advisory):
        class Batch:
            id, processing_status = "b1", "ended"

        class Result:
            def __init__(self, i, slug):
                self.custom_id = f"t-{i}"

                class Msg:
                    content = [
                        type("B", (), {"type": "text", "text": json.dumps({"work_type": slug})})()
                    ]

                self.result = type("R", (), {"type": "succeeded", "message": Msg()})()

        class Batches:
            def __init__(self):
                self.requests = None

            def create(self, requests):
                self.requests = requests
                return Batch()

            def retrieve(self, _id):
                return Batch()

            def results(self, _id):
                return [Result(0, "consulting"), Result(1, "legal_opinion")]

        client = type("C", (), {"messages": type("M", (), {"batches": Batches()})()})()
        mapping = classify_by_batch(
            ["Parecer X", "Consulta Y", "Consulta Y"],
            advisory,
            client=client,
            model="claude-haiku-4-5",
            poll_seconds=0,
        )
        assert mapping == {"Consulta Y": "consulting", "Parecer X": "legal_opinion"}
        req = client.messages.batches.requests
        assert (
            len(req) == 2
            and req[0]["params"]["output_config"]["format"]["schema"]["properties"]["work_type"][
                "enum"
            ][0]
            == "existing_case"
        )
