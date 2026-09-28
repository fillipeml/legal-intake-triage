from legal_intake.filters import (
    channel_of,
    clean_body,
    forms_responder,
    is_auto_generated,
    is_auto_reply,
    is_forwarded_subject,
    route_message,
    strip_html,
)
from legal_intake.models import Channel


def test_subject_shapes():
    assert is_forwarded_subject("ENC: contrato")
    assert is_forwarded_subject("Fwd: contrato")
    assert is_forwarded_subject("RES: contrato")
    assert not is_forwarded_subject("RE: contrato")
    assert (
        channel_of("[Forms/WhatsApp] Demanda registrada por x@lawfirm.example") == Channel.WHATSAPP
    )
    assert channel_of("[Forms/Reunião] Demanda registrada por x@lawfirm.example") == Channel.MEETING
    assert channel_of("[Forms/Fax] Demanda") == Channel.OTHER
    assert channel_of("Contrato") == Channel.EMAIL
    assert (
        forms_responder("[Forms/Telefone] Demanda registrada por Ana.Ribeiro@lawfirm.example")
        == "ana.ribeiro@lawfirm.example"
    )
    assert forms_responder("[Forms/Telefone] Demanda registrada por ninguém") is None
    assert forms_responder("Contrato") is None


def test_noise_detectors():
    assert is_auto_generated("noreply@x.example")
    assert is_auto_generated("MAILER-DAEMON@x.example")
    assert not is_auto_generated("juridico@x.example")
    assert is_auto_reply("Resposta Automática: ausente")
    assert is_auto_reply("Automatic reply: out of office")
    assert not is_auto_reply("RE: Resposta ao cliente")


def test_routes():
    external = route_message(
        "cliente@x.example", "Contrato", is_internal=False, is_intake_account=False
    )
    assert (
        external.kind == "demand" and not external.forwarded and external.channel == Channel.EMAIL
    )

    forward = route_message(
        "ana@lawfirm.example", "ENC: Contrato", is_internal=True, is_intake_account=False
    )
    assert (
        forward.kind == "demand"
        and forward.forwarded
        and forward.forwarded_by == "ana@lawfirm.example"
    )

    internal = route_message(
        "ana@lawfirm.example", "Reunião", is_internal=True, is_intake_account=False
    )
    assert internal.kind == "closing_candidate"

    form = route_message(
        "intake@lawfirm.example",
        "[Forms/WhatsApp] Demanda registrada por ana@lawfirm.example",
        is_internal=True,
        is_intake_account=True,
    )
    assert (
        form.kind == "demand"
        and form.channel == Channel.WHATSAPP
        and form.forwarded_by == "ana@lawfirm.example"
    )

    fake_form = route_message(
        "spam@x.example",
        "[Forms/WhatsApp] Demanda registrada por ana@lawfirm.example",
        is_internal=False,
        is_intake_account=False,
    )
    assert fake_form.kind == "skip"

    assert (
        route_message(
            "noreply@x.example", "Boletim", is_internal=False, is_intake_account=False
        ).skip
        == "auto-generated sender"
    )
    assert (
        route_message(
            "c@x.example", "Out of office", is_internal=False, is_intake_account=False
        ).skip
        == "automatic reply"
    )


def test_body_cleaning():
    html = "<html><style>p{}</style><body><p>Prezados,</p><p>Segue &amp; obrigado<br>Tchau</p><script>x()</script></body></html>"
    assert strip_html(html) == "Prezados,\n\nSegue & obrigado\nTchau"
    assert clean_body("a" * 50, 10) == "a" * 10
    assert clean_body("<p>oi</p>", 100) == "oi"
