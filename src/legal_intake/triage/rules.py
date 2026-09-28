"""A rules-based triager: keyword taxonomy, directory match, the distribution rules and a
template reply. It is the offline baseline the evaluation measures the model against, and
what the demo uses for a message without a recorded reading."""

from __future__ import annotations

import re
import unicodedata

from ..models import DUE_DATE_MARKER, NOT_IDENTIFIED, Complexity, Confidence, TriagePackage
from ..suggest import suggest_lawyer
from .types import TriageInput, TriageOutput

URGENT_WORDS = (
    "ainda hoje",
    "hoje",
    "amanhã",
    "amanha",
    "urgente",
    "urgência",
    "urgencia",
    "vence sexta",
    "até sexta",
    "imediat",
)
HIGH_WORDS = (
    "parecer",
    "due diligence",
    "diagnóstico",
    "diagnostico",
    "acordo de sócios",
    "acordo de socios",
    "legal opinion",
    "reestrutura",
    "múltiplos",
    "multiplos",
    "vários contratos",
    "varios contratos",
)
LOW_WORDS = (
    "dúvida",
    "duvida",
    "consulta",
    "orientação",
    "orientacao",
    "esclarecimento",
    "procuração",
    "procuracao",
    "termo simples",
)
GREETING_RE = re.compile(r"^(prezad[oa]s?|bom dia|boa tarde|boa noite|ol[aá])[,!.\s]", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b")
DEADLINE_RE = re.compile(
    r"(até (?:o dia |a |as )?[^.,;\n]{2,30}|prazo[^.,;\n]{2,40}|audiência[^.,;\n]{2,40}"
    r"|assembleia[^.,;\n]{2,40}|dia \d{1,2}(?:/\d{1,2})?)",
    re.I,
)


def normalise(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


class RuleTriager:
    kind = "rules"

    def triage(self, item: TriageInput) -> TriageOutput:
        area = item.area
        text = f"{item.message.subject}\n{item.body}"
        norm = normalise(text)

        # client: the sender's domain, or an e-mail quoted in a forwarded body, or a name
        client_name, confidence = NOT_IDENTIFIED, Confidence.LOW
        candidates = [item.message.sender] + re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", item.body)
        for email in candidates:
            found = area.client_for(email)
            if found:
                client_name, confidence = found.name, Confidence.HIGH
                break
        if client_name == NOT_IDENTIFIED:
            for c in area.clients:
                if normalise(c.name) in norm:
                    client_name, confidence = c.name, Confidence.MEDIUM
                    break

        # work type: the first keyword that matches, most specific first, per the taxonomy order
        work_type = "other"
        for t in area.taxonomy:
            if any(normalise(k) in norm for k in t.keywords):
                work_type = t.slug
                break

        # complexity and days
        if any(normalise(w) in norm for w in URGENT_WORDS):
            complexity = Complexity.URGENT
        elif any(normalise(w) in norm for w in HIGH_WORDS):
            complexity = Complexity.HIGH
        elif any(normalise(w) in norm for w in LOW_WORDS) or work_type in ("consulting", "other"):
            complexity = Complexity.LOW
        else:
            complexity = Complexity.MEDIUM
        days = area.deadline_scale[complexity]
        m = DEADLINE_RE.search(text)
        explicit = (
            m.group(1).strip()
            if m
            else (DATE_RE.search(text).group(1) if DATE_RE.search(text) else NOT_IDENTIFIED)
        )

        suggestion = suggest_lawyer(
            area, client_name=client_name, forwarded_by=item.forwarded_by, load=item.load
        )
        title = area.work_type(work_type).title if area.work_type(work_type) else work_type
        summary = self._summary(item, title, client_name)
        package = TriagePackage(
            client=client_name,
            client_confidence=confidence,
            work_type=work_type,
            summary=summary,
            suggested_lawyer=suggestion.lawyer,
            lawyer_rationale=suggestion.rationale,
            complexity=complexity,
            suggested_days=days,
            explicit_deadline=explicit,
            reply_draft=self._reply(item, client_name),
        )
        return TriageOutput(package=package, model="rules")

    @staticmethod
    def _summary(item: TriageInput, title: str, client: str) -> str:
        body = re.sub(r"\s+", " ", item.body).strip()
        first = (
            re.split(r"(?<=[.!?])\s", body, maxsplit=1)[0][:220] if body else item.message.subject
        )
        who = client if client != NOT_IDENTIFIED else "an unidentified client"
        return f"{title} requested by {who}. Subject: {item.message.subject}. {first}"

    @staticmethod
    def _reply(item: TriageInput, client: str) -> str:
        name = client if client != NOT_IDENTIFIED else "cliente"
        return (
            f"Prezado(a) {name},\n\n"
            f'Confirmamos o recebimento da sua solicitação sobre "{item.message.subject}". '
            f"Nossa equipe já está analisando o pedido e retornaremos até {DUE_DATE_MARKER}.\n\n"
            f"Permanecemos à disposição.\n\nEquipe {item.area.name} — {{firm}}"
        )
