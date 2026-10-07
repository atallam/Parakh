"""Example pipeline: summarise, then a human-review checkpoint (C7.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Required, TypedDict

from parakh.agents.summarizer import summarize
from parakh.audit.review_queue import default_queue
from parakh.config import get_settings
from parakh.llm.client import LLMClient
from parakh.llm.schemas import Summary
from parakh.observability.tracing import observation
from parakh.privacy import redact_pii


class PipelineState(TypedDict, total=False):
    text: Required[str]
    summary: Summary | None
    needs_review: bool
    review_reason: str


@dataclass(frozen=True)
class PipelineResult:
    summary: Summary | None
    needs_review: bool
    review_reason: str = ""

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> PipelineResult:
        return cls(
            summary=state.get("summary"),
            needs_review=bool(state.get("needs_review", True)),
            review_reason=state.get("review_reason", ""),
        )


def summarize_step(state: Mapping[str, Any], client: LLMClient | None = None) -> dict[str, Any]:
    return {"summary": summarize(state["text"], client=client)}


def review_gate(state: Mapping[str, Any]) -> dict[str, Any]:
    """Low-confidence or missing output waits for a human instead of flowing on."""
    summary = state.get("summary")
    threshold = get_settings().confidence_review_below
    if summary is None:
        return {"needs_review": True, "review_reason": "no output (LLM unavailable)"}
    if summary.confidence < threshold:
        reason = f"confidence {summary.confidence:.2f} below {threshold:.2f}"
        default_queue().add(kind="summary", payload=summary.model_dump(), reason=reason)
        return {"needs_review": True, "review_reason": reason}
    return {"needs_review": False}


def run_pipeline(text: str, client: LLMClient | None = None) -> PipelineResult:
    """One trace per pipeline run: summarise (which traces its own LLM calls), then the gate."""
    state: dict[str, Any] = {"text": text}
    with observation(
        "run-summary-pipeline", as_type="chain", input={"text": redact_pii(text)}
    ) as run:
        state.update(summarize_step(state, client))
        with observation("review-summary", as_type="evaluator") as gate:
            state.update(review_gate(state))
            gate.update(
                output={"needs_review": state["needs_review"], "reason": state.get("review_reason")}
            )
        result = PipelineResult.from_state(state)
        run.update(
            output={
                "summary": result.summary.model_dump() if result.summary else None,
                "needs_review": result.needs_review,
                "review_reason": result.review_reason,
            }
        )
    return result
