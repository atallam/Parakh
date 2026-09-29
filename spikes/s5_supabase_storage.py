"""Spike ⑤: SupabaseRepository + Parquet in Supabase Storage + DuckDB, on a real Supabase stack.

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY (CI takes them from `supabase status` of the local
stack; later the real `parakh` project). Proves:
1. a run's audit outbox syncs to Postgres, so the run ends SUCCESS (not SUCCESS_AUDIT_PENDING);
2. re-sending the same events is harmless (ON CONFLICT DO NOTHING on the append-only table);
3. UPDATE through the API is rejected by the trigger;
4. runs and run_steps upsert;
5. Parquet round-trips through a private Storage bucket and DuckDB reads it back.
"""

from __future__ import annotations

import datetime as dt
import os
import tempfile
from pathlib import Path

import pandas as pd
from _common import Recorder
from supabase import create_client

from parakh.audit.emit import AuditSink
from parakh.audit.manifest import read_manifest
from parakh.orchestration.jobs import run_dummy
from parakh.storage.prices import ParquetPriceStore, SupabaseBlobs
from parakh.storage.supabase_repo import SupabaseAuditSyncer, SupabaseRepository


def main() -> None:
    rec = Recorder("s5")
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    repo = SupabaseRepository(client)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PARAKH_STATE_DIR"] = tmp
        sink = AuditSink(Path(tmp) / "audit", syncer=SupabaseAuditSyncer(repo))
        ctx, outcome = run_dummy(sink=sink)
        rec.note(
            probe="audit.sync",
            ok=outcome.status == "SUCCESS",
            status=outcome.status,
            pending=outcome.audit_pending,
        )
        manifest = read_manifest(ctx.run_id)
        assert manifest is not None
        repo.save_run(manifest)
        runs = client.table("runs").select("run_id,status").eq("run_id", ctx.run_id).execute().data
        steps = client.table("run_steps").select("step_id").eq("run_id", ctx.run_id).execute().data
        rec.note(
            probe="runs.upsert", ok=len(runs) == 1 and len(steps) == 3, runs=runs, steps=len(steps)
        )
        n_before = repo.count_audit_events(ctx.run_id)
        repo.insert_audit_events(sink.events_for_run(ctx.run_id))
        rec.note(
            probe="audit.resend_idempotent",
            ok=n_before == repo.count_audit_events(ctx.run_id) == 2,
            count=n_before,
        )
        try:
            client.table("audit_events").update({"reason": "tamper"}).eq(
                "run_id", ctx.run_id
            ).execute()
            rec.note(probe="audit.update_rejected", ok=False, detail="update succeeded")
        except Exception as exc:
            rec.note(
                probe="audit.update_rejected", ok="append-only" in str(exc), detail=str(exc)[:200]
            )

        blobs = SupabaseBlobs(client, bucket="prices")
        blobs.ensure_bucket()
        days = pd.bdate_range("2025-12-24", "2026-01-06")
        frame = pd.DataFrame(
            [
                {
                    "isin": isin,
                    "trade_date": d.date(),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0 + i,
                    "adj_close": 100.0 + i,
                    "volume": 1000 + i,
                    "source": "spike",
                }
                for isin in ("INE040A01034", "INE249Z01020")
                for i, d in enumerate(days)
            ]
        )
        store = ParquetPriceStore(blobs, Path(tmp) / "cache")
        paths = store.write(frame)
        fresh = ParquetPriceStore(blobs, Path(tmp) / "cache2")  # empty cache: must download
        back = fresh.query(
            ["INE040A01034", "INE249Z01020"], dt.date(2025, 12, 1), dt.date(2026, 1, 31)
        )
        rec.note(
            probe="parquet.roundtrip", ok=len(back) == len(frame), written=paths, rows=len(back)
        )
    rec.save()
    failed = [r for r in rec.rows if r.get("ok") is False]
    if failed:
        raise SystemExit(f"{len(failed)} probe(s) failed")


if __name__ == "__main__":
    main()
