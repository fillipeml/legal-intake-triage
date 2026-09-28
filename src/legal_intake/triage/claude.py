"""The triage against the Claude API: one call per demand, a structured output enforced by
the package's schema with the area's taxonomy, a cached system prompt per area, thinking
off on purpose (a short, deterministic classification; switch it on if the adjustment rate
climbs)."""

from __future__ import annotations

import json
from typing import Any

from ..models import TriagePackage
from .prompts import output_schema, system_prompt, user_message
from .types import TriageInput, TriageOutput


class TriageError(RuntimeError):
    pass


class ClaudeTriager:
    kind = "claude"

    def __init__(self, api_key: str, model: str, firm_name: str, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.firm_name = firm_name
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise TriageError("ANTHROPIC_API_KEY is not set (or use DEMO_MODE=true)")
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def triage(self, item: TriageInput) -> TriageOutput:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=2048,
            thinking={"type": "disabled"},
            system=[
                {
                    "type": "text",
                    "text": system_prompt(item.area, self.firm_name),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": output_schema(item.area)}},
            messages=[{"role": "user", "content": user_message(item)}],
        )
        if response.stop_reason == "max_tokens":
            raise TriageError("the triage was cut short by the output limit")
        if response.stop_reason == "refusal":
            raise TriageError("the model declined to triage this message")
        text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
        try:
            package = TriagePackage.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise TriageError(f"the model's answer does not fit the package: {exc}") from exc
        usage = getattr(response, "usage", None)
        return TriageOutput(
            package=package,
            model=self.model,
            usage=(
                {
                    "input_tokens": getattr(usage, "input_tokens", 0),
                    "output_tokens": getattr(usage, "output_tokens", 0),
                    "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                    "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0)
                    or 0,
                }
                if usage
                else None
            ),
        )
