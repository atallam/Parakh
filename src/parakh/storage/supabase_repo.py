"""Supabase repository for operational tables (ADR-004, D11) and the audit outbox syncer.

Uses the service key server-side only. `audit_events` is append-only in the database, so the
syncer inserts with ON CONFLICT DO NOTHING: re-sending an event is harmless and never an
UPDATE (which the trigger would reject). That is what lets a run retry its outbox safely
(AC-F21.5).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from postgrest.types import ReturnMethod

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditEvent
from parakh.audit.manifest import RunManifest
from parakh.quality import DqResult

AUDIT_COLUMNS = {
    "event_id", "event_type", "ts_utc", "trading_date_ist", "run_id", "step_id", "actor_type",
    "actor_id", "channel", "entity_type", "entity_id", "isin", "action", "before", "after",
    "reason", "evidence_ref", "details", "code_version", "config_hash", "framework_version",
    "prev_hash", "record_hash",
}  # fmt: skip
BATCH = 500
PAGE = 1000  # PostgREST's default row cap per request
FUNDAMENTAL_KEY = ("isin", "metric_id", "period_type", "period_end", "source_id")


def plan_fundamental_inserts(
    rows: list[dict[str, Any]], latest: dict[tuple[Any, ...], tuple[int, Any]], run_id: str
) -> tuple[list[dict[str, Any]], int]:
    """Rows to insert given the latest stored (version, value) per key; and how many restate.

    New key → version 1. Same value → skipped. Different value → next version (a restatement:
    the old row stays, so past runs remain reproducible).
    """
    new: list[dict[str, Any]] = []
    restated = 0
    for r in rows:
        key = tuple(r[k] for k in FUNDAMENTAL_KEY)
        value = r["value"]
        if isinstance(value, float) and math.isnan(value):
            value = None
        if key in latest:
            version, old = latest[key]
            same = (old is None and value is None) or (
                old is not None and value is not None and abs(float(old) - float(value)) < 1e-9
            )
            if same:
                continue
            restated += 1
            new.append({**r, "value": value, "version": version + 1, "run_id": run_id})
        else:
            new.append({**r, "value": value, "version": 1, "run_id": run_id})
    return new, restated


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

    def begin_run(self, ctx: RunContext) -> None:
        """A RUNNING row at START, so rows written during the run can reference it."""
        self.client.table("runs").upsert(
            {
                "run_id": ctx.run_id,
                "mode": ctx.mode,
                "env": ctx.env,
                "asof": ctx.asof.isoformat(),
                "trigger_type": ctx.trigger,
                "triggered_by": ctx.actor,
                "started_at": ctx.started_at.isoformat(),
                "status": "RUNNING",
                "code_version": ctx.code_version,
                "config_hash": ctx.config_hash,
                "framework_version": ctx.framework_version,
            },
            on_conflict="run_id",
        ).execute()

    def _all(self, table: str, columns: str, **eq: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            query = self.client.table(table).select(columns)
            for col, value in eq.items():
                query = query.eq(col, value)
            batch = query.range(start, start + PAGE - 1).execute().data or []
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            start += PAGE

    def write_fundamentals(self, rows: list[dict[str, Any]], run_id: str) -> tuple[int, int]:
        """Append-only, versioned (plan 05 §3.4): new keys get version 1, changed values the
        next version (a restatement), unchanged values are skipped. Returns (inserted, restated).
        """
        isins = {r["isin"] for r in rows}
        latest: dict[tuple[Any, ...], tuple[int, Any]] = {}
        for isin in isins:
            for r in self._all(
                "fundamentals", ",".join((*FUNDAMENTAL_KEY, "version", "value")), isin=isin
            ):
                key = tuple(r[k] for k in FUNDAMENTAL_KEY)
                if key not in latest or r["version"] > latest[key][0]:
                    latest[key] = (r["version"], r["value"])
        new, restated = plan_fundamental_inserts(rows, latest, run_id)
        for i in range(0, len(new), BATCH):
            self.client.table("fundamentals").insert(
                new[i : i + BATCH], returning=ReturnMethod.minimal
            ).execute()
        return len(new), restated

    def record_price_files(self, rows: list[dict[str, Any]]) -> int:
        if rows:
            self.client.table("price_files").upsert(
                rows,
                on_conflict="storage_path,sha256",
                ignore_duplicates=True,
                returning=ReturnMethod.minimal,
            ).execute()
        return len(rows)

    def record_dq(self, run_id: str, results: Iterable[DqResult]) -> int:
        rows = [
            {
                "run_id": run_id,
                "isin": r.isin,
                "check_id": r.check_id,
                "status": r.status,
                "detail": r.detail,
            }
            for r in results
        ]
        if rows:
            self.client.table("dq_results").upsert(
                rows, on_conflict="run_id,check_id,isin", returning=ReturnMethod.minimal
            ).execute()
        return len(rows)

    # -- holdings (restricted tables; service role only) -------------------------------------
    def statement_exists(self, file_sha256: str) -> bool:
        rows = (
            self.client.table("cas_statements")
            .select("statement_id")
            .eq("file_sha256", file_sha256)
            .execute()
            .data
        )
        return bool(rows)

    def lots_for_account(self, account_ref: str) -> list[Any]:
        import datetime as dt

        from parakh.holdings.lots import Lot

        rows = self._all(
            "holdings_lots",
            "lot_id,account_ref,isin,qty,trade_date,settle_date,price_inr,source,status",
            account_ref=account_ref,
        )
        return [
            Lot(
                r["lot_id"],
                r["account_ref"],
                r["isin"],
                float(r["qty"]),
                dt.date.fromisoformat(r["trade_date"]),
                dt.date.fromisoformat(r["settle_date"]),
                None if r["price_inr"] is None else float(r["price_inr"]),
                r["source"],
            )
            for r in rows
            if r["status"] == "open"
        ]

    def write_holdings(self, plan: Any, run_id: str) -> None:
        """Statement → positions → lots → transactions (foreign-key order)."""
        from parakh.orchestration.holdings import lot_row

        if plan.statement is not None:
            self.client.table("cas_statements").insert(
                {**plan.statement, "run_id": run_id}
            ).execute()
            if plan.positions:
                self.client.table("cas_positions").insert(
                    plan.positions, returning=ReturnMethod.minimal
                ).execute()
        if plan.lots:
            self.client.table("holdings_lots").insert(
                [lot_row(lot) for lot in plan.lots], returning=ReturnMethod.minimal
            ).execute()
        if plan.transactions:
            self.client.table("transactions").insert(
                plan.transactions, returning=ReturnMethod.minimal
            ).execute()

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


class SupabaseRunRecorder:
    """RunRecorder: mirrors each run into `runs` and `run_steps` (plan 10 §5)."""

    def __init__(self, repo: SupabaseRepository) -> None:
        self.repo = repo

    def begin(self, ctx: RunContext) -> None:
        self.repo.begin_run(ctx)

    def end(self, manifest: RunManifest) -> None:
        self.repo.save_run(manifest)


def connect_supabase(url: str, key: str) -> SupabaseRepository:
    """Wire the process audit sink to Supabase (outbox flush + run mirroring) and return the repo."""
    from supabase import create_client

    from parakh.audit.emit import get_sink

    repo = SupabaseRepository(create_client(url, key))
    sink = get_sink()
    sink.syncer = SupabaseAuditSyncer(repo)
    sink.recorder = SupabaseRunRecorder(repo)
    return repo
