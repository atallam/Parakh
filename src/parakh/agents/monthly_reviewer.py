"""AGENT.monthly_reviewer: "top 5 things to look at" after the monthly run (plan 15 §5; F25.3).

The agent reads `reports.what_changed` and friends and returns a validated list of items and a short
narrative. This module then enforces what a prompt cannot: only stocks the report listed may be
named (in the items and in the narrative), notes pass `sanitize_note`, and amounts never appear.
If anything fails the monthly summary says "review pending" and nothing else changes (AC-F25.3).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from parakh.agents.roster import agent_enabled, build_spec, run_agent
from parakh.agents.runtime.base import AgentRunner, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.configs import ConfigBundle
from parakh.notify.templates import ReviewItem, render_monthly_review, sanitize_note

AGENT_ID = "AGENT.monthly_reviewer"
VERSION = "0.1.0"
MAX_ITEMS = 5
_AMOUNT = re.compile(r"(₹|\bRs\.?\s?\d|\bINR\b|\b\d[\d,]*\s?(cr|crore|lakh|lakhs)\b)", re.I)


class ReviewItemOut(BaseModel):
    symbol: str = Field(max_length=20)
    tag: Literal["act", "watch", "info"]
    note: str = Field(max_length=400)


class MonthlyReviewOutput(BaseModel):
    items: list[ReviewItemOut] = Field(max_length=MAX_ITEMS)
    narrative: str = Field(max_length=3000)


@dataclass
class ReviewOutcome:
    status: Literal["ok", "pending", "failed", "disabled"]
    items: list[ReviewItem] = field(default_factory=list)
    narrative_html: str | None = None
    reason: str = ""

    @property
    def pending(self) -> bool:
        return self.status != "ok"


def _pilot_symbols(bundle: ConfigBundle) -> set[str]:
    return {s.symbol for s in bundle.universe.pilot}


def validate_output(
    out: MonthlyReviewOutput, allowed: set[str], bundle: ConfigBundle
) -> tuple[list[ReviewItem], str | None, str]:
    """(items, narrative_html, problem). A problem means the whole review is pending."""
    items: list[ReviewItem] = []
    for it in out.items[:MAX_ITEMS]:
        sym = it.symbol.upper()
        if sym not in allowed:
            return [], None, f"names {sym}, which what_changed did not list"
        note = sanitize_note(it.note, include_amounts=bundle.notify.include_amounts)
        if note is None:
            return [], None, f"the note for {sym} contains an amount, link or nothing"
        items.append(ReviewItem(sym, it.tag, note))
    if not items:
        return [], None, "no items"
    text = out.narrative
    if not bundle.notify.include_amounts and _AMOUNT.search(text):
        return [], None, "the narrative contains an amount"
    mentioned = {
        t for t in re.findall(r"\b[A-Z][A-Z0-9&-]{2,}\b", text) if t in _pilot_symbols(bundle)
    }
    stray = sorted(mentioned - allowed)
    if stray:
        return [], None, f"the narrative names {', '.join(stray)}, which what_changed did not list"
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return items, "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs), ""


def run_review(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    *,
    period: str,
    allowed_symbols: set[str],
) -> ReviewOutcome:
    if not agent_enabled(bundle, AGENT_ID):
        return ReviewOutcome("disabled", reason="agent not enabled")
    if not allowed_symbols:
        return ReviewOutcome("ok", [], "<p>Nothing changed this month.</p>", "nothing to review")
    spec = build_spec(AGENT_ID, bundle, version=VERSION, output_model=MonthlyReviewOutput)
    task = AgentTask(
        task_id=f"{ctx.run_id}.review", kind="monthly_review", inputs={"period": period}
    )
    result = run_agent(runner, spec, task, ctx, sink, bundle)
    if result.status != "ok" or result.output is None:
        return ReviewOutcome(result.status, reason=result.reason or result.status)
    out = MonthlyReviewOutput.model_validate(result.output)
    items, narrative, problem = validate_output(out, {s.upper() for s in allowed_symbols}, bundle)
    if problem:
        return ReviewOutcome("pending", reason=problem)
    return ReviewOutcome("ok", items, narrative)


def review_message(outcome: ReviewOutcome, period: str, bundle: ConfigBundle):  # type: ignore[no-untyped-def]
    return render_monthly_review(
        outcome.items, period=period, include_amounts=bundle.notify.include_amounts
    )
