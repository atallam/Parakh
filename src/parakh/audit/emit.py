"""Emit audit events: hash-chained, written first to a local JSONL outbox (plan 10 §4.2, §4.3).

    sink = get_sink()
    sink.emit(ctx, AUD.RUN_START, entity_type="run", entity_id=ctx.run_id)

- `record_hash = sha256(prev_hash + canonical_json(record))`; editing any past line breaks
  `verify_chain()` from that line on.
- The outbox is `<state>/audit/outbox/<YYYY-MM-DD>.jsonl` (UTC date). A syncer flushes it to the
  Supabase `audit_events` table (Phase 1). Until an event is synced, a run can't finish as
  SUCCESS; it ends `SUCCESS_AUDIT_PENDING` and the next job retries (AC-F21.5).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import structlog

from parakh.audit.context import RunContext
from parakh.audit.events import AUD, AuditEvent, Channel, trading_date_ist
from parakh.audit.ids import new_ulid
from parakh.config import state_dir

GENESIS = "sha256:" + "0" * 64
log = structlog.get_logger(__name__)


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def chain_hash(prev_hash: str, record: dict[str, Any]) -> str:
    body = (prev_hash + canonical_json(record)).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


class AuditSyncer(Protocol):
    """Flushes outbox events to durable storage. Returns the number of events now synced."""

    def flush(self, events: list[AuditEvent]) -> int: ...


class NoSyncer:
    """Phase 0: no database yet, so nothing is ever synced (runs end SUCCESS_AUDIT_PENDING)."""

    name = "none (Supabase flush arrives in Phase 1)"

    def flush(self, events: list[AuditEvent]) -> int:
        return 0


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    events: int
    head: str
    first_bad_event: str | None = None


class AuditSink:
    """Append-only, hash-chained audit outbox. Thread-safe within one process."""

    def __init__(self, root: Path, syncer: AuditSyncer | None = None) -> None:
        self.root = root
        self.outbox = root / "outbox"
        self.head_file = root / "chain_head.json"
        self.syncer: AuditSyncer = syncer or NoSyncer()
        self._lock = threading.Lock()

    # -- writing -----------------------------------------------------------------------
    def _head(self) -> str:
        if self.head_file.exists():
            return json.loads(self.head_file.read_text(encoding="utf-8"))["hash"]
        return GENESIS

    def emit(
        self,
        ctx: RunContext,
        event_type: AUD,
        *,
        step_id: str | None = None,
        channel: Channel | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        isin: str | None = None,
        action: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        evidence_ref: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        now = dt.datetime.now(dt.UTC)
        event = AuditEvent(
            event_id=new_ulid(),
            event_type=event_type,
            ts_utc=now,
            trading_date_ist=trading_date_ist(now),
            run_id=ctx.run_id,
            step_id=step_id,
            actor_type=ctx.actor_type,
            actor_id=ctx.actor_id,
            channel=channel,
            entity_type=entity_type,
            entity_id=entity_id,
            isin=isin,
            action=action,
            before=before,
            after=after,
            reason=reason,
            evidence_ref=evidence_ref,
            details=details or {},
            code_version=ctx.code_version,
            config_hash=ctx.config_hash,
            framework_version=ctx.framework_version,
        )
        with self._lock:
            prev = self._head()
            event.prev_hash = prev
            event.record_hash = chain_hash(prev, event.hashable())
            self.outbox.mkdir(parents=True, exist_ok=True)
            path = self.outbox / f"{now.date().isoformat()}.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(canonical_json(event.model_dump(mode="json")) + "\n")
            tmp = self.head_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"hash": event.record_hash, "event_id": event.event_id}),
                encoding="utf-8",
            )
            tmp.replace(self.head_file)
        log.info("audit.emit", event_type=event_type.value, event_id=event.event_id)
        return event

    # -- reading and checking ------------------------------------------------------------
    def events(self) -> list[AuditEvent]:
        """All outbox events in chain order."""
        out: list[AuditEvent] = []
        for path in sorted(self.outbox.glob("*.jsonl")) if self.outbox.exists() else []:
            with path.open(encoding="utf-8") as fh:
                out.extend(AuditEvent.model_validate_json(line) for line in fh if line.strip())
        return out

    def events_for_run(self, run_id: str) -> list[AuditEvent]:
        return [e for e in self.events() if e.run_id == run_id]

    def head(self) -> str:
        return self._head()

    def verify_chain(self) -> ChainCheck:
        """Recompute every hash from genesis (AC-F21.4's daily integrity check uses this)."""
        prev = GENESIS
        events = self.events()
        for event in events:
            if event.prev_hash != prev or chain_hash(prev, event.hashable()) != event.record_hash:
                return ChainCheck(False, len(events), prev, first_bad_event=event.event_id)
            prev = event.record_hash
        return ChainCheck(True, len(events), prev)

    def flush(self, run_id: str) -> tuple[int, int]:
        """Try to sync this run's events. Returns (synced, pending)."""
        events = self.events_for_run(run_id)
        synced = self.syncer.flush(events)
        return synced, len(events) - synced


_default: AuditSink | None = None
_default_lock = threading.Lock()


def get_sink() -> AuditSink:
    """The process-wide sink under `<state>/audit/`."""
    global _default
    with _default_lock:
        root = state_dir() / "audit"
        if _default is None or _default.root != root:
            _default = AuditSink(root)
        return _default


def reset_sink() -> None:
    """Tests: forget the cached sink so a new state dir takes effect."""
    global _default
    with _default_lock:
        _default = None
