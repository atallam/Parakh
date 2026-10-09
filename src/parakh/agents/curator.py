"""AGENT.watchlist_curator: proposals for the watchlist, never changes (F25; plan 06 §7; AG-03).

The agent calls `portfolio.propose_*` itself through parakh-mcp. Those tools write only to the
proposal store. The monthly step below then ingests valid proposals through the same capacity,
minimum-stay, mute and dedupe rules as the rule-based suggestions, so an agent cannot get around them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from parakh.agents.roster import agent_enabled, build_spec, run_agent
from parakh.agents.runtime.base import AgentRunner, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.configs import ConfigBundle
from parakh.services.watchlist import WatchlistService

AGENT_ID = "AGENT.watchlist_curator"
VERSION = "0.1.0"


class CuratorOutput(BaseModel):
    proposals_made: int = Field(ge=0, le=20)
    notes: str = Field(default="", max_length=500)


@dataclass
class CuratorResult:
    status: Literal["ok", "pending", "skipped"]
    proposed: int = 0
    ingested: int = 0
    dropped: int = 0
    reason: str = ""


def curate(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    service: WatchlistService,
    *,
    period: str,
    room: dict[str, int],
    today: dt.date,
) -> CuratorResult:
    """Run the agent, then ingest what it proposed (capped at `agent_proposals.max_per_run`)."""
    if not agent_enabled(bundle, AGENT_ID):
        return CuratorResult("skipped", reason="agent disabled")
    spec = build_spec(AGENT_ID, bundle, version=VERSION, output_model=CuratorOutput)
    task = AgentTask(
        task_id=f"{ctx.run_id}.curator",
        kind="curate_watchlist",
        inputs={
            "period": period,
            "room_large": str(room.get("large", 0)),
            "room_mid": str(room.get("mid", 0)),
            "room_small": str(room.get("small", 0)),
        },
    )
    result = run_agent(runner, spec, task, ctx, sink, bundle)
    if result.status != "ok" or result.output is None:
        return CuratorResult("pending", reason=result.reason or result.status)
    out = CuratorOutput.model_validate(result.output)
    acts = service.ingest_proposals(today=today)
    ingested = sum(1 for a in acts if a.kind == "suggested")
    dropped = sum(1 for p in service.proposals.all() if p.payload.get("dropped"))
    return CuratorResult("ok", out.proposals_made, ingested, dropped)
