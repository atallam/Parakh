"""Step ledger and run lifecycle (plan 10 §5; AC-F21.1).

    with run_lifecycle(ctx) as run:
        with audited_step(ctx, "fetch_prices", source="yfinance") as step:
            frame = adapter.fetch(...)
            step.record_output(rows=len(frame), sha256=frame_hash(frame))

`run_lifecycle` guarantees exactly one `AUD.RUN.START` and one terminal event (`AUD.RUN.END`
or `AUD.RUN.ABORT`) and always writes `runs/<run_id>/manifest.json`, even on failure.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import structlog

from parakh.audit.context import RunContext, StepRecord
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.manifest import write_manifest
from parakh.observability.logging import scrub_text

log = structlog.get_logger(__name__)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass
class StepHandle:
    record: StepRecord

    def record_output(self, **outputs: Any) -> None:
        """Row counts and output hashes, for lineage and replay (plan 10 §5)."""
        self.record.outputs.update(outputs)


@contextmanager
def audited_step(ctx: RunContext, name: str, **inputs: Any) -> Iterator[StepHandle]:
    """Run one pipeline step with timing, status and a ledger row. Exceptions propagate."""
    record = ctx.start_step(name, inputs)
    bound = log.bind(step_id=record.step_id, step=name)
    bound.info("step.start", **inputs)
    try:
        yield StepHandle(record)
    except BaseException as exc:
        record.status = "failed"
        record.error = scrub_text(f"{type(exc).__name__}: {exc}")[:500]
        raise
    else:
        record.status = "ok"
    finally:
        record.ended_at = dt.datetime.now(dt.UTC)
        bound.info("step.end", status=record.status, latency_ms=record.duration_ms)


@dataclass
class RunOutcome:
    status: str = "RUNNING"  # SUCCESS | SUCCESS_AUDIT_PENDING | FAILED
    audit_pending: int = 0
    summary: dict[str, Any] = field(default_factory=dict)


@contextmanager
def run_lifecycle(ctx: RunContext, sink: AuditSink | None = None) -> Iterator[RunOutcome]:
    """START → body → END (or ABORT on error) → flush → manifest."""
    sink = sink or get_sink()
    outcome = RunOutcome()
    sink.emit(
        ctx,
        AUD.RUN_START,
        entity_type="run",
        entity_id=ctx.run_id,
        details={"mode": ctx.mode, "asof": ctx.asof.isoformat(), "trigger": ctx.trigger},
    )
    log.info("run.start", mode=ctx.mode, asof=ctx.asof.isoformat())
    _record(sink.recorder.begin, ctx)
    try:
        yield outcome
    except BaseException as exc:
        outcome.status = "FAILED"
        sink.emit(
            ctx,
            AUD.RUN_ABORT,
            entity_type="run",
            entity_id=ctx.run_id,
            reason=scrub_text(f"{type(exc).__name__}: {exc}")[:500],
        )
        _finish(ctx, sink, outcome)
        raise
    else:
        sink.emit(
            ctx,
            AUD.RUN_END,
            entity_type="run",
            entity_id=ctx.run_id,
            details={"steps": len(ctx.steps), **outcome.summary},
        )
        synced, pending = _finish(ctx, sink, outcome)
        outcome.status = "SUCCESS" if pending == 0 else "SUCCESS_AUDIT_PENDING"
        _record(sink.recorder.end, write_manifest(ctx, outcome.status, sink, pending))
        log.info("run.end", status=outcome.status, synced=synced, audit_pending=pending)


def _finish(ctx: RunContext, sink: AuditSink, outcome: RunOutcome) -> tuple[int, int]:
    synced, pending = sink.flush(ctx.run_id)
    outcome.audit_pending = pending
    if outcome.status == "FAILED":
        _record(sink.recorder.end, write_manifest(ctx, outcome.status, sink, pending))
    return synced, pending


def _record(call: Any, arg: Any) -> None:
    """Mirroring a run must never break it; a failure is logged and the outbox still holds it."""
    try:
        call(arg)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: storage is best-effort here
        log.warning("run.record_failed", error=scrub_text(f"{type(exc).__name__}: {exc}")[:300])
