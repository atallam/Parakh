"""AGENT.devils_advocate: exactly three counter-points to a changed or new strong verdict (F07).

It runs only when the verdict changed this month or a new Tier A BUY/SELL appeared (AC-F07.1), so the
cost follows the news. Each point must cite a metric the tools returned or a document id, which the
job checks against the snapshot (AC-F07.3). The agent moves confidence by one level at most and never
changes the verdict (AC-F07.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from parakh.agents.roster import agent_enabled, build_spec, run_agent
from parakh.agents.runtime.base import AgentRunner, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD
from parakh.configs import ConfigBundle

AGENT_ID = "AGENT.devils_advocate"
VERSION = "0.1.0"
STRONG = {"BUY", "SELL"}


class CounterPoint(BaseModel):
    claim: str = Field(max_length=400)
    evidence_metric: str = Field(default="", max_length=80)
    evidence_value: str = Field(default="", max_length=80)
    document_id: str = Field(default="", max_length=100)

    @property
    def has_evidence(self) -> bool:
        return bool((self.evidence_metric and self.evidence_value) or self.document_id)


class DaOutput(BaseModel):
    counter_points: list[CounterPoint]
    confidence_adjustment: Literal[-1, 0, 1] = 0

    @field_validator("counter_points")
    @classmethod
    def _three(cls, v: list[CounterPoint]) -> list[CounterPoint]:
        if len(v) != 3:
            raise ValueError("exactly three counter-points")
        if not all(p.has_evidence for p in v):
            raise ValueError("every counter-point needs evidence")
        return v


@dataclass
class DaResult:
    isin: str
    status: Literal["ok", "pending", "skipped"]
    overlay: dict[str, Any] = field(default_factory=dict)
    confidence_delta: int = 0
    reason: str = ""


def should_run(snap: dict[str, Any], previous: dict[str, Any] | None = None) -> bool:
    """The verdict changed this month, or a new high-confidence BUY/SELL appeared (AC-F07.1)."""
    v = snap.get("verdict", {})
    if v.get("changed") and v.get("prev_verdict") is not None:
        return True
    new_strong = (
        v.get("verdict") in STRONG
        and v.get("confidence") == "High"
        and v.get("prev_verdict") != v.get("verdict")
    )
    return bool(new_strong)


def run_devils_advocate(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    *,
    snap: dict[str, Any],
    previous: dict[str, Any] | None,
) -> DaResult:
    isin = snap["isin"]
    if not agent_enabled(bundle, AGENT_ID):
        return DaResult(isin, "skipped", reason="agent disabled")
    if not should_run(snap, previous):
        return DaResult(isin, "skipped", reason="no verdict change")
    spec = build_spec(AGENT_ID, bundle, version=VERSION, output_model=DaOutput)
    task = AgentTask(
        task_id=f"{ctx.run_id}.da.{isin}",
        kind="counter_case",
        inputs={"isin": isin, "symbol": snap["symbol"], "period": snap["period"]},
    )
    result = run_agent(runner, spec, task, ctx, sink, bundle)
    if result.status != "ok" or result.output is None:
        return DaResult(isin, "pending", reason=result.reason or result.status)
    out = DaOutput.model_validate(result.output)
    sink.emit(
        ctx, AUD.AGENT_PROPOSAL, entity_type="verdict", entity_id=isin, isin=isin,
        details={"agent_id": AGENT_ID, "confidence_adjustment": out.confidence_adjustment},
    )  # fmt: skip
    return DaResult(
        isin,
        "ok",
        {
            "status": "ok",
            "period": snap["period"],
            "counter_points": [p.model_dump() for p in out.counter_points],
            "confidence_adjustment": out.confidence_adjustment,
        },
        out.confidence_adjustment,
    )
