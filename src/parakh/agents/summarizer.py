"""Example agent. Copy this shape for real agents, then delete it."""

from __future__ import annotations

import re

import structlog
from pydantic import ValidationError

from parakh.llm.client import LLMClient, LLMUnavailable
from parakh.llm.schemas import Summary
from parakh.observability.tracing import observation
from parakh.privacy import redact_pii
from parakh.prompts import render_prompt

AGENT_NAME = "summarizer"
log = structlog.get_logger(__name__)


class AgentFailed(Exception):
    """The agent could not produce a valid output within its iteration cap."""


def extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may be wrapped in prose or a code fence."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def summarize(text: str, client: LLMClient | None = None) -> Summary | None:
    """Summarise `text`. Returns None if the LLM is unavailable (graceful degradation, C3.5)."""
    client = client or LLMClient(agent_name=AGENT_NAME)
    text = redact_pii(text)  # no PII reaches the cloud model (C6.3)
    # A `chain` groups the validate-and-retry attempts; each attempt is one generation inside it.
    with observation("summarize-text", as_type="chain", input={"text": text}) as run:
        summary = _summarize(text, client)
        run.update(output=summary.model_dump() if summary else {"degraded": "llm_unavailable"})
    return summary


def _summarize(text: str, client: LLMClient) -> Summary | None:
    system, prompt = render_prompt("summarize", text=text)
    feedback = ""
    max_iterations = client.settings.llm_max_iterations  # hard cap (C3.1)
    for attempt in range(1, max_iterations + 1):
        try:
            response = client.complete(
                prompt_id="summarize", system=system, prompt=prompt + feedback
            )
        except LLMUnavailable:
            log.warning("agent.degraded", agent_name=AGENT_NAME, reason="llm_unavailable")
            return None
        try:
            return Summary.model_validate_json(extract_json(response.text))  # (C3.4)
        except ValidationError as exc:
            log.warning("agent.invalid_output", agent_name=AGENT_NAME, attempt=attempt)
            problems = exc.errors()[:3]
            feedback = f"\n\nYour previous reply was invalid: {problems}. Reply with JSON only."
    raise AgentFailed(f"{AGENT_NAME}: no valid output after {max_iterations} attempts")
