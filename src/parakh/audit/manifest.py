"""Run manifest: `<state>/runs/<run_id>/manifest.json` (plan 10 §5).

Records what ran, on what code and config, every step's status and I/O hashes, and the audit
chain head, so `replay` (Phase 5) can re-run it and "why did it say BUY in March?" has an answer.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from parakh.config import state_dir

if TYPE_CHECKING:
    from parakh.audit.context import RunContext
    from parakh.audit.emit import AuditSink


class StepView(BaseModel):
    step_id: str
    name: str
    seq: int
    status: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    duration_ms: float | None
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    error: str | None


class RunManifest(BaseModel):
    manifest_version: int = 1
    run_id: str
    mode: str
    env: str
    asof: dt.date
    trigger: str
    triggered_by: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime
    code_version: str
    config_hash: str
    framework_version: str
    lens_versions: dict[str, str] = {}
    policy_version: str | None = None
    prompt_versions: dict[str, str] = {}
    steps: list[StepView]
    audit_events: int
    audit_pending: int
    audit_chain_head: str
    audit_sink: str
    llm_tokens: int = 0
    alerts_sent: int = 0
    alerts_suppressed: int = 0
    agent_runs: int = 0
    failed_steps: int = 0


def runs_dir() -> Path:
    return state_dir() / "runs"


def manifest_path(run_id: str) -> Path:
    return runs_dir() / run_id / "manifest.json"


def _counts(events: list[Any]) -> tuple[int, int, int, int]:
    """(alerts_sent, alerts_suppressed, agent_runs, llm_tokens)."""
    """Run-summary counts from the run's own audit events (AC-F19.1)."""
    from parakh.audit.events import AUD

    sent = [e for e in events if e.event_type == AUD.ALERT_SENT]
    agent_end = [e for e in events if e.event_type == AUD.AGENT_END]
    tokens = sum(
        int(e.details.get("tokens_in") or 0) + int(e.details.get("tokens_out") or 0)
        for e in agent_end
    )
    suppressed = sum(1 for e in events if e.event_type == AUD.ALERT_SUPPRESSED)
    return len(sent), suppressed, len(agent_end), tokens


def write_manifest(ctx: RunContext, status: str, sink: AuditSink, pending: int) -> RunManifest:
    events = sink.events_for_run(ctx.run_id)
    sent, suppressed, agent_runs, tokens = _counts(events)
    manifest = RunManifest(
        alerts_sent=sent,
        alerts_suppressed=suppressed,
        agent_runs=agent_runs,
        llm_tokens=tokens,
        failed_steps=sum(1 for s in ctx.steps if s.status not in ("ok", "SUCCESS")),
        run_id=ctx.run_id,
        mode=ctx.mode,
        env=ctx.env,
        asof=ctx.asof,
        trigger=ctx.trigger,
        triggered_by=ctx.actor,
        status=status,
        started_at=ctx.started_at,
        finished_at=dt.datetime.now(dt.UTC),
        code_version=ctx.code_version,
        config_hash=ctx.config_hash,
        framework_version=ctx.framework_version,
        lens_versions=ctx.lens_versions,
        policy_version=ctx.policy_version,
        steps=[
            StepView(
                step_id=s.step_id,
                name=s.name,
                seq=s.seq,
                status=s.status,
                started_at=s.started_at,
                ended_at=s.ended_at,
                duration_ms=s.duration_ms,
                inputs=s.inputs,
                outputs=s.outputs,
                error=s.error,
            )
            for s in ctx.steps
        ],
        audit_events=len(events),
        audit_pending=pending,
        audit_chain_head=sink.head(),
        audit_sink=getattr(sink.syncer, "name", type(sink.syncer).__name__),
    )
    path = manifest_path(ctx.run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def read_manifest(run_id: str) -> RunManifest | None:
    path = manifest_path(run_id)
    if not path.exists():
        return None
    return RunManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def list_run_ids() -> list[str]:
    root = runs_dir()
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "manifest.json").exists())
