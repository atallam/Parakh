"""Price store and audit syncer without a network (spike ⑤). T-STO-01…"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

from parakh.audit.emit import AuditSink
from parakh.orchestration.jobs import run_dummy
from parakh.storage.prices import LocalBlobs, ParquetPriceStore, price_path
from parakh.storage.supabase_repo import SupabaseAuditSyncer, SupabaseRepository, audit_row


def _frame() -> pd.DataFrame:
    days = pd.bdate_range("2025-12-29", "2026-01-02")
    return pd.DataFrame(
        [
            {
                "isin": "INE040A01034",
                "trade_date": d.date(),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": float(i),
                "adj_close": float(i),
                "volume": i,
                "source": "test",
            }
            for i, d in enumerate(days)
        ]
    )


def test_parquet_is_split_by_isin_and_year_and_duckdb_reads_it_back(tmp_path: Path) -> None:
    """T-STO-01"""
    blobs = LocalBlobs(tmp_path / "blobs")
    paths = ParquetPriceStore(blobs, tmp_path / "c1").write(_frame())
    assert sorted(paths) == [price_path("INE040A01034", 2025), price_path("INE040A01034", 2026)]
    out = ParquetPriceStore(blobs, tmp_path / "c2").query(
        ["INE040A01034"], dt.date(2025, 12, 30), dt.date(2026, 1, 1)
    )
    assert list(out["close"]) == [1.0, 2.0, 3.0]


class _Table:
    def __init__(self, fail: bool, calls: list[Any]) -> None:
        self.fail, self.calls = fail, calls

    def upsert(self, rows: Any, **kwargs: Any) -> _Table:
        self.calls.append((rows, kwargs))
        return self

    def execute(self) -> None:
        if self.fail:
            raise ConnectionError("supabase unreachable")


class _Client:
    def __init__(self, fail: bool = False) -> None:
        self.fail, self.calls = fail, []

    def table(self, _name: str) -> _Table:
        return _Table(self.fail, self.calls)


def test_synced_run_is_success_and_inserts_never_update(tmp_path: Path) -> None:
    """T-STO-02: ON CONFLICT DO NOTHING, so a resend is never an UPDATE."""
    client = _Client()
    sink = AuditSink(tmp_path / "audit", syncer=SupabaseAuditSyncer(SupabaseRepository(client)))
    _, outcome = run_dummy(sink=sink)
    assert outcome.status == "SUCCESS"
    rows, kwargs = client.calls[0]
    assert kwargs["ignore_duplicates"] is True and len(rows) == 2
    assert set(rows[0]) >= {"event_id", "record_hash", "prev_hash"}


def test_unreachable_supabase_leaves_the_run_audit_pending(tmp_path: Path) -> None:
    """T-STO-03 (AC-F21.5 path): no event is lost; the outbox keeps them for the next job."""
    sink = AuditSink(
        tmp_path / "audit", syncer=SupabaseAuditSyncer(SupabaseRepository(_Client(fail=True)))
    )
    ctx, outcome = run_dummy(sink=sink)
    assert outcome.status == "SUCCESS_AUDIT_PENDING" and outcome.audit_pending == 2
    assert len(sink.events_for_run(ctx.run_id)) == 2


def test_audit_row_matches_the_table_columns(tmp_path: Path) -> None:
    """T-STO-04"""
    sink = AuditSink(tmp_path / "audit")
    ctx, _ = run_dummy(sink=sink)
    row = audit_row(sink.events_for_run(ctx.run_id)[0])
    assert "synced_at" not in row and row["event_type"] == "AUD.RUN.START"
