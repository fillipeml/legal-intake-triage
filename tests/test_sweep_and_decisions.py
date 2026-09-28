"""The pipelines over the fixture inbox and the seeded state."""

from datetime import datetime

import pytest

from legal_intake.clock import now
from legal_intake.models import ClosedVia, Complexity, Decision, DemandStatus
from legal_intake.pipeline.closing import sync_from_board
from legal_intake.pipeline.decision import DecisionError, decide, effective_days
from legal_intake.pipeline.intake import sweep
from legal_intake.pipeline.metrics import closed_via_gap, compute_metrics
from tests.conftest import demand_id_for


@pytest.fixture
def swept(services):
    summary = sweep(services)
    return services, summary


class TestSweep:
    def test_every_route_of_the_fixture_inbox(self, swept):
        services, s = swept
        assert s.messages == 14 and s.failed == []
        assert (
            len(s.registered) == 8
            and s.duplicates == 2
            and len(s.skipped) == 3
            and len(s.closed) == 1
        )
        reasons = " | ".join(s.skipped)
        assert (
            "internal message that is not a forward" in reasons
            and "auto-generated" in reasons
            and "automatic reply" in reasons
        )
        assert s.closed[0].startswith(
            "d-seed-1 closed by the reply of carla.mendes@lawfirm.example"
        )
        seed1 = services.registry.get("d-seed-1")
        assert seed1.status == DemandStatus.DONE and seed1.closed_via == ClosedVia.EMAIL
        assert seed1.replied_at == datetime.fromisoformat("2026-09-19T17:45:00-03:00")
        assert services.board.get("t-seed-1").percent_complete == 100
        # the client's reply in the other seeded thread neither closes nor duplicates
        assert services.registry.get("d-seed-2").status == DemandStatus.IN_EXECUTION

    def test_cards_go_to_the_right_people(self, swept):
        services, s = swept
        by_demand = {c["demand"]: c["to"] for c in s.cards}
        assert by_demand[demand_id_for("m01")] == [
            "bruno.costa@lawfirm.example"
        ]  # the client's lead
        assert by_demand[demand_id_for("m02")] == [
            "ana.ribeiro@lawfirm.example",
            "bruno.costa@lawfirm.example",
        ]  # no lead: the heads
        assert by_demand[demand_id_for("m04")] == [
            "diego.souza@lawfirm.example"
        ]  # the form's responder
        assert by_demand[demand_id_for("m09")] == ["ana.ribeiro@lawfirm.example"]
        assert by_demand[demand_id_for("m12")] == ["igor.lima@lawfirm.example"]  # the forwarder
        assert by_demand[demand_id_for("m13")] == [
            "helena.duarte@lawfirm.example"
        ]  # external straight to the list: the head
        for to in by_demand.values():
            assert all(a.endswith("@lawfirm.example") for a in to)

    def test_what_the_triage_and_the_checks_recorded(self, swept):
        services, _ = swept
        m03 = services.registry.get(demand_id_for("m03"))
        assert (
            m03.forwarded_by == "carla.mendes@lawfirm.example" and m03.ai_lawyer == "Carla Mendes"
        )
        assert m03.channel.value == "email" and m03.triage_model == "fixture:m03"
        m04 = services.registry.get(demand_id_for("m04"))
        assert m04.channel.value == "whatsapp" and m04.forwarded_by == "diego.souza@lawfirm.example"
        m14 = services.registry.get(demand_id_for("m14"))
        assert m14.ai_work_type == "other" and any(
            "no lawyer suggested" in n for n in m14.triage_notes
        )
        m09 = services.registry.get(demand_id_for("m09"))
        assert m09.ai_complexity == Complexity.URGENT and m09.ai_days == 1

    def test_second_sweep_does_nothing(self, swept):
        services, _ = swept
        again = sweep(services)
        assert again.already_processed == 14 and again.registered == [] and again.closed == []
        assert len(services.registry.list()) == 9 + 8

    def test_the_card_is_a_reply_in_the_thread_with_the_adaptive_card(self, swept):
        services, s = swept
        sent = services.mailer.sent
        cards = [x for x in sent if x["kind"] == "card"]
        assert len(cards) == 8 and all(c["thread"].startswith("conv-") for c in cards)
        text = (services.settings.state_dir / "outbox" / cards[0]["file"]).read_text(
            encoding="utf-8"
        )
        assert (
            "application/adaptivecard+json" in text
            and '"Input.ChoiceSet"' in text
            and "/cards/d-" in text
        )


class TestDecision:
    def test_approve_as_suggested(self, swept):
        services, _ = swept
        out = decide(
            services,
            Decision(
                demand_id=demand_id_for("m01"),
                action="approve",
                validated_by="Bruno.Costa@lawfirm.example",
            ),
        )
        d = out.demand
        assert (
            d.status == DemandStatus.IN_EXECUTION
            and d.adjusted is False
            and d.validated_by == "bruno.costa@lawfirm.example"
        )
        assert str(d.due_date) == "2026-09-28"  # five business days from Monday 21
        task = services.board.get(out.task_id)
        assert (
            task.bucket == "Construtora Exemplo"
            and task.assignee == "Carla Mendes"
            and task.label == "category2"
        )
        assert task.checklist[0] == "Gather information" and task.title.startswith(
            "[Construtora Exemplo] Contract review — "
        )
        assert "28/09/2026" in task.description and "[DUE_DATE]" not in task.description
        assert out.reply == "draft to advisory@lawfirm.example"
        draft = [x for x in services.mailer.sent if x["kind"] == "mail"][-1]
        assert draft["to"] == ["advisory@lawfirm.example"] and draft["subject"].startswith(
            "[DRAFT for review] RE:"
        )

    def test_adjustments_are_measured_and_new_clients_get_a_bucket(self, swept):
        services, _ = swept
        out = decide(
            services,
            Decision(
                demand_id=demand_id_for("m02"),
                action="approve",
                validated_by="ana.ribeiro@lawfirm.example",
                client="empresa nova",
                lawyer="Diego Souza",
                complexity=Complexity.HIGH,
            ),
        )
        d = out.demand
        assert (
            d.adjusted is True
            and d.final_lawyer == "Diego Souza"
            and d.final_days == 10
            and str(d.due_date) == "2026-10-05"
        )
        assert services.board.get(out.task_id).bucket == "empresa nova"
        assert "empresa nova" in services.board.buckets("advisory-weekly")
        # a second demand of the same client typed with different casing reuses the bucket
        assert services.board.ensure_bucket("advisory-weekly", "  EMPRESA NOVA ") == "empresa nova"

    def test_explicit_days_win_over_the_scale(self, swept, advisory):
        services, _ = swept
        d = services.registry.get(demand_id_for("m01"))
        assert (
            effective_days(
                advisory,
                d,
                Decision(demand_id=d.id, action="approve", validated_by="x", days=2),
                Complexity.MEDIUM,
            )
            == 2
        )
        assert (
            effective_days(
                advisory,
                d,
                Decision(demand_id=d.id, action="approve", validated_by="x", days=5),
                Complexity.HIGH,
            )
            == 10
        )
        assert (
            effective_days(
                advisory,
                d,
                Decision(demand_id=d.id, action="approve", validated_by="x"),
                Complexity.LOW,
            )
            == 3
        )

    def test_forwarded_and_form_demands_get_no_reply(self, swept):
        services, _ = swept
        assert decide(
            services,
            Decision(
                demand_id=demand_id_for("m03"),
                action="approve",
                validated_by="bruno.costa@lawfirm.example",
            ),
        ).reply.startswith("not sent: forwarded")
        assert decide(
            services,
            Decision(
                demand_id=demand_id_for("m04"),
                action="approve",
                validated_by="diego.souza@lawfirm.example",
            ),
        ).reply.startswith("not sent: forwarded")

    def test_send_mode_replies_to_the_original_sender_only(self, swept, advisory):
        services, _ = swept
        advisory.reply_mode = "send"
        out = decide(
            services,
            Decision(
                demand_id=demand_id_for("m09"),
                action="approve",
                validated_by="ana.ribeiro@lawfirm.example",
            ),
        )
        assert (
            out.reply == "sent to juridico@incorporadora-modelo.example"
            and out.demand.reply_sent_to == "juridico@incorporadora-modelo.example"
        )
        mail = [x for x in services.mailer.sent if x["kind"] == "mail"][-1]
        assert (
            mail["to"] == ["juridico@incorporadora-modelo.example"]
            and mail["from"] == "advisory@lawfirm.example"
        )
        assert str(out.demand.due_date) == "2026-09-22"

    def test_corporate_review_adds_days_and_the_person_sets_the_deadline(self, swept):
        services, _ = swept
        out = decide(
            services,
            Decision(
                demand_id=demand_id_for("m12"),
                action="approve",
                validated_by="igor.lima@lawfirm.example",
                reviewer="Helena Duarte",
                review_days=2,
            ),
        )
        d = out.demand
        assert d.final_days == 10 and d.review_days == 2 and str(d.due_date) == "2026-10-07"
        assert services.board.get(out.task_id).description.startswith(
            "INTERNAL REVIEW: Helena Duarte — 2 business day(s)"
        )
        assert out.reply == "not sent: the area does not reply automatically"
        out2 = decide(
            services,
            Decision(
                demand_id=demand_id_for("m13"),
                action="approve",
                validated_by="helena.duarte@lawfirm.example",
                days=3,
            ),
        )
        assert (
            out2.demand.final_days == 3
            and out2.demand.adjusted is True
            and str(out2.demand.due_date) == "2026-09-24"
        )

    def test_discard_race_and_errors(self, swept):
        services, _ = swept
        first = decide(
            services,
            Decision(
                demand_id=demand_id_for("m14"),
                action="discard",
                validated_by="ana.ribeiro@lawfirm.example",
            ),
        )
        assert first.demand.status == DemandStatus.DISCARDED and first.task_id is None
        second = decide(
            services,
            Decision(
                demand_id=demand_id_for("m14"),
                action="approve",
                validated_by="bruno.costa@lawfirm.example",
            ),
        )
        assert (
            second.already_decided and second.demand.validated_by == "ana.ribeiro@lawfirm.example"
        )
        with pytest.raises(DecisionError, match="not found"):
            decide(services, Decision(demand_id="d-nope", action="approve", validated_by="x"))
        with pytest.raises(DecisionError, match="not a lawyer"):
            decide(
                services,
                Decision(
                    demand_id=demand_id_for("m01"),
                    action="approve",
                    validated_by="x",
                    lawyer="Dr. Nobody",
                ),
            )
        with pytest.raises(DecisionError, match="taxonomy"):
            decide(
                services,
                Decision(
                    demand_id=demand_id_for("m01"),
                    action="approve",
                    validated_by="x",
                    work_type="magic",
                ),
            )
        with pytest.raises(DecisionError, match="reviewer"):
            decide(
                services,
                Decision(
                    demand_id=demand_id_for("m12"),
                    action="approve",
                    validated_by="x",
                    reviewer="Lucas Pires",
                ),
            )
        assert (
            services.registry.get(demand_id_for("m01")).status == DemandStatus.AWAITING_VALIDATION
        )


class TestClosingAndMetrics:
    def test_board_sync_closes_without_a_reply_date(self, swept):
        services, _ = swept
        out = decide(
            services,
            Decision(
                demand_id=demand_id_for("m03"),
                action="approve",
                validated_by="bruno.costa@lawfirm.example",
            ),
        )
        assert sync_from_board(services, now(services.settings)) == []
        services.board.complete(out.task_id, now(services.settings))
        closed = sync_from_board(services, now(services.settings))
        assert len(closed) == 1 and "no reply date" in closed[0]
        d = services.registry.get(out.demand.id)
        assert (
            d.status == DemandStatus.DONE
            and d.closed_via == ClosedVia.BOARD
            and d.replied_at is None
        )

    def test_metrics(self, swept):
        services, _ = swept
        decide(
            services,
            Decision(
                demand_id=demand_id_for("m01"),
                action="approve",
                validated_by="bruno.costa@lawfirm.example",
            ),
        )
        decide(
            services,
            Decision(
                demand_id=demand_id_for("m02"),
                action="approve",
                validated_by="ana.ribeiro@lawfirm.example",
                lawyer="Diego Souza",
            ),
        )
        metrics = compute_metrics(services, services.settings.reference_date)
        adv = metrics.areas[0]
        assert adv.key == "advisory" and adv.demands == 9 + 6
        assert adv.decided == 11 and adv.adjusted == 5 and adv.adjustment_rate == round(5 / 11, 3)
        assert adv.adjusted_fields["lawyer"] == 4
        assert adv.closed_via == {"email": 5, "board": 2}
        assert closed_via_gap(adv) == round(2 / 7, 3)
        assert adv.open_by_lawyer["Diego Souza"] == 6 and adv.by_status["awaiting_validation"] == 4
        assert adv.overdue == 1  # d-seed-2, due 19/09, still in execution
        corp = metrics.areas[1]
        assert corp.decided == 0 and corp.adjustment_rate is None and closed_via_gap(corp) is None
