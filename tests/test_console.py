import pytest
from fastapi.testclient import TestClient

from legal_intake.console.app import create_app
from legal_intake.pipeline.intake import sweep
from tests.conftest import demand_id_for


@pytest.fixture
def client(services):
    sweep(services)
    return TestClient(create_app(services))


def test_health_and_pages(client):
    health = client.get("/api/health").json()
    assert (
        health["demo_mode"] is True
        and health["triager"] == "fixture"
        and health["areas"] == ["advisory", "corporate"]
    )
    assert "adjustment rate" in client.get("/").text
    cards = client.get("/cards").text
    assert "Revisão de contrato de fornecimento" in cards and "Decide" in cards
    page = client.get(f"/cards/{demand_id_for('m12')}").text
    assert "Internal review" in page and "Helena Duarte" in page and 'name="reply"' not in page
    assert client.get("/cards/d-missing").status_code == 404


def test_deciding_through_the_form(client, services):
    demand_id = demand_id_for("m01")
    response = client.post(
        f"/cards/{demand_id}",
        data={
            "action": "approve",
            "validated_by": "bruno.costa@lawfirm.example",
            "client": "Construtora Exemplo",
            "work_type": "contract_review",
            "lawyer": "Carla Mendes",
            "complexity": "medium",
            "days": "5",
            "reply": "Prezados, [DUE_DATE].",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303 and response.headers["location"].endswith("outcome=approved")
    page = client.get(f"/cards/{demand_id}?outcome=approved").text
    assert "Approved by bruno.costa@lawfirm.example" in page
    again = client.post(
        f"/cards/{demand_id}",
        data={"action": "discard", "validated_by": "ana.ribeiro@lawfirm.example"},
        follow_redirects=False,
    )
    assert again.headers["location"].endswith("outcome=already")
    nobody = client.post(
        f"/cards/{demand_id_for('m02')}",
        data={"action": "approve", "validated_by": "x@gmail.example"},
        follow_redirects=False,
    )
    assert nobody.headers["location"].endswith("outcome=who")


def test_api_decisions_require_the_secret(services):
    services.settings.console_secret = "s3cret"
    sweep(services)
    client = TestClient(create_app(services))
    body = {
        "demand_id": demand_id_for("m09"),
        "action": "approve",
        "validated_by": "ana.ribeiro@lawfirm.example",
    }
    assert client.post("/api/decisions", json=body).status_code == 401
    ok = client.post("/api/decisions", json=body, headers={"Action-Authorization": "Bearer s3cret"})
    assert (
        ok.status_code == 200
        and ok.headers["CARD-UPDATE-IN-BODY"] == "true"
        and "approved by ana.ribeiro" in ok.json()["body"][0]["text"]
    )
    twice = client.post("/api/decisions", json=body, headers={"Authorization": "Bearer s3cret"})
    assert "already decided" in twice.json()["body"][0]["text"]
    bad = client.post(
        "/api/decisions",
        json={"demand_id": "d-nope", "action": "approve", "validated_by": "x"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert bad.status_code == 400


def test_password_gate(services):
    services.settings.console_password = "pw"
    services.settings.console_secret = "signing"
    client = TestClient(create_app(services))
    assert client.get("/", follow_redirects=False).status_code == 303
    wrong = client.post(
        "/sign-in",
        data={"email": "ana.ribeiro@lawfirm.example", "password": "no", "next": "/cards"},
    )
    assert "Wrong password" in wrong.text
    outside = client.post(
        "/sign-in", data={"email": "ana@gmail.example", "password": "pw", "next": "/"}
    )
    assert "firm's domain" in outside.text
    good = client.post(
        "/sign-in",
        data={"email": "ana.ribeiro@lawfirm.example", "password": "pw", "next": "/cards"},
        follow_redirects=False,
    )
    assert good.status_code == 303 and "intake_session" in good.headers.get("set-cookie", "")
    assert "ana.ribeiro@lawfirm.example" in client.get("/cards").text
    client.post("/sign-out")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_sign_in_does_not_redirect_off_site(services):
    """`next` is attacker-supplied: it rides in the URL of the link the user clicked.

    The guard accepted anything beginning with "/", which includes "//evil.example/x" — a
    protocol-relative URL that the browser resolves to another host. A sign-in page that
    lands the user on someone else's site, having just taken their password, is the shape
    every credential-phishing flow wants.
    """
    services.settings.console_password = "pw"
    services.settings.console_secret = "signing"
    client = TestClient(create_app(services))

    for hostile in ("//evil.example/phish", "///evil.example", "//evil.example"):
        response = client.post(
            "/sign-in",
            data={"email": "ana.ribeiro@lawfirm.example", "password": "pw", "next": hostile},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/", hostile

    ok = client.post(
        "/sign-in",
        data={"email": "ana.ribeiro@lawfirm.example", "password": "pw", "next": "/cards"},
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/cards"
