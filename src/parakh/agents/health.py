"""LLM health at the end of a run: the P4 alert (plan 13 P4; AC-F25.2).

    reasons = llm_health(events, bundle.agents.alerts)      # [] when all is well
    msg = render_llm_alert(reasons)                         # one Telegram message, or None

Counted from the audit events of the run: agent runs (`AUD.AGENT.END`), schema failures, budget and
turn-limit stops, suspected injections and unverified quotes. One message per run, never one per stock.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from parakh.audit.events import AUD, AuditEvent
from parakh.configs.models import AgentAlerts
from parakh.notify.telegram import escape
from parakh.notify.templates import Message

COUNTED = (
    AUD.AGENT_END, AUD.LLM_VALIDATION_FAIL, AUD.LLM_BUDGET_STOP, AUD.AGENT_TURN_LIMIT,
    AUD.LLM_INJECTION_SUSPECTED, AUD.LLM_CITATION_UNVERIFIED,
)  # fmt: skip


def llm_health(events: Iterable[AuditEvent], cfg: AgentAlerts) -> list[str]:
    n: Counter[AUD] = Counter(e.event_type for e in events if e.event_type in COUNTED)
    runs = n[AUD.AGENT_END]
    reasons: list[str] = []
    if n[AUD.LLM_BUDGET_STOP]:
        reasons.append(f"{n[AUD.LLM_BUDGET_STOP]} agent run(s) stopped on the token budget")
    if n[AUD.AGENT_TURN_LIMIT]:
        reasons.append(f"{n[AUD.AGENT_TURN_LIMIT]} agent run(s) hit the turn limit")
    if n[AUD.LLM_INJECTION_SUSPECTED]:
        reasons.append(
            f"{n[AUD.LLM_INJECTION_SUSPECTED]} document(s) looked like a prompt injection"
        )
    if runs >= cfg.min_runs:
        fail = n[AUD.LLM_VALIDATION_FAIL] / runs * 100
        if fail > cfg.validation_fail_pct:
            reasons.append(
                f"{fail:.0f}% of outputs failed validation (limit {cfg.validation_fail_pct:g}%)"
            )
        bad = n[AUD.LLM_CITATION_UNVERIFIED] / runs * 100
        if bad > cfg.unverified_citation_pct:
            reasons.append(
                f"{bad:.0f}% of quotes were not in the document (limit {cfg.unverified_citation_pct:g}%)"
            )
    return reasons


def render_llm_alert(reasons: list[str]) -> Message | None:
    if not reasons:
        return None
    lines = ["⚠️ <b>LLM check needed</b>", *(f"• {escape(r)}" for r in reasons[:5]),
             "Affected stocks show “qualitative pending”; nothing was guessed."]  # fmt: skip
    return Message("llm_health", lines)
