"""Supabase repository for operational tables (ADR-004, D11) and the audit outbox syncer.

Uses the service key server-side only. `audit_events` is append-only in the database, so the
syncer inserts with ON CONFLICT DO NOTHING: re-sending an event is harmless and never an
UPDATE (which the trigger would reject). That is what lets a run retry its outbox safely
(AC-F21.5).
"""

from __future__ import annotations

from typing import Any

from postgrest.types import ReturnMethod

from parakh.audit.emit import AuditEvent
from parakh.audit.manifest import RunManifest

AUDIT_COLUMNS = {
    "event_id", "event_type", "ts_utc", "trading_date_ist", "run_id", "step_id", "actor_type",
    "actor_id", "channel", "entity_type", "entity_id", "isin", "action", "before", "after",
    "reason", "evidence_ref", "details", "code_version", "config_hash", "framework_version",
    "prev_hash", "record_hash",
}  # fmt: skip
BATCH = 500


def audit_row(event: AuditEvent) -> dict[str, Any]:
    data = event.model_dump(mode="json")
    return {k: v for k, v in data.items() if k in AUDIT_COLUMNS}


class SupabaseRepository:
    def __init__(self, client: Any) -> None:
        self.client = client

    def save_run(self, manifest: RunManifest) -> None:
        """Upsert the run row and its step ledger (runs are updatable; audit is not)."""
        run = {
            "run_id": manifest.run_id,
            "mode": manifest.mode,
            "env": manifest.env,
            "asof": manifest.asof.isoformat(),
            "trigger_type": manifest.trigger,
            "triggered_by": manifest.triggered_by,
            "started_at": manifest.started_at.isoformat(),
            "finished_at": manifest.finished_at.isoformat(),
            "status": manifest.status,
            "code_version": manifest.code_version,
            "config_hash": manifest.config_hash,
            "framework_version": manifest.framework_version,
            "lens_versions": manifest.lens_versions,
            "prompt_versions": manifest.prompt_versions,
            "llm_tokens": manifest.llm_tokens,
            "audit_chain_head": manifest.audit_chain_head,
        }
        self.client.table("runs").upsert(run, on_conflict="run_id").execute()
        steps = [
            {
                "step_id": s.step_id,
                "run_id": manifest.run_id,
                "name": s.name,
                "seq": s.seq,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "status": s.status,
                "output_hashes": {
                    k: v
                    for k, v in s.outputs.items()
                    if isinstance(v, str) and v.startswith("sha256:")
                },
                "rows_out": s.outputs.get("rows")
                if isinstance(s.outputs.get("rows"), int)
                else None,
                "error": s.error,
            }
            for s in manifest.steps
        ]
        if steps:
            self.client.table("run_steps").upsert(steps, on_conflict="step_id").execute()

    def insert_audit_events(self, events: list[AuditEvent]) -> int:
        rows = [audit_row(e) for e in events]
        for i in range(0, len(rows), BATCH):
            self.client.table("audit_events").upsert(
                rows[i : i + BATCH],
                on_conflict="event_id",
                ignore_duplicates=True,
                returning=ReturnMethod.minimal,
            ).execute()
        return len(rows)

    def count_audit_events(self, run_id: str) -> int:
        resp = (
            self.client.table("audit_events")
            .select("event_id", count="exact")
            .eq("run_id", run_id)
            .execute()
        )
        return int(resp.count or 0)


class SupabaseAuditSyncer:
    """AuditSyncer for the outbox (plan 10 §4.3). Any failure leaves events pending."""

    name = "supabase"

    def __init__(self, repo: SupabaseRepository) -> None:
        self.repo = repo

    def flush(self, events: list[AuditEvent]) -> int:
        if not events:
            return 0
        try:
            return self.repo.insert_audit_events(events)
        except Exception:
            return 0
