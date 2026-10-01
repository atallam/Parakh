"""Holdings import (synthetic CAS + broker report, in-memory writer) and the private-files guard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from parakh.adapters.broker_pnl import parse_groww_pnl
from parakh.adapters.cas import from_casparser
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.holdings.lots import Lot
from parakh.orchestration.holdings import ImportPlan, import_holdings

FIX = Path(__file__).resolve().parents[1] / "fixtures"
SEP_RAW = json.loads((FIX / "cas" / "synthetic_cas_2026-09.json").read_text(encoding="utf-8"))
SEP = from_casparser(SEP_RAW, b"k")
BROKER = parse_groww_pnl((FIX / "broker" / "synthetic_groww_pnl.xlsx").read_bytes())
_spec = importlib.util.spec_from_file_location(
    "check_private_files", Path(__file__).resolve().parents[2] / "tools" / "check_private_files.py"
)
assert _spec and _spec.loader
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
problems = _guard.problems


class MemoryWriter:
    def __init__(self) -> None:
        self.statements: set[str] = set()
        self.lots: list[Lot] = []
        self.positions: list[dict[str, Any]] = []
        self.transactions: list[dict[str, Any]] = []

    def statement_exists(self, file_sha256: str) -> bool:
        return file_sha256 in self.statements

    def lots_for_account(self, account_ref: str) -> list[Lot]:
        return [lot for lot in self.lots if lot.account_ref == account_ref]

    def write_holdings(self, plan: ImportPlan, run_id: str) -> None:
        if plan.statement:
            self.statements.add(plan.statement["file_sha256"])
        self.positions += plan.positions
        self.lots += plan.lots
        self.transactions += plan.transactions


@pytest.mark.ac("AC-F03.1")
def test_first_import_seeds_lots_and_stores_positions() -> None:
    """T-HLD-10: positions for all 3 accounts; lots seeded only for the broker's account."""
    writer = MemoryWriter()
    ctx, outcome, r = import_holdings(SEP, "sha256:sep", BROKER, writer)
    assert r.statement_new and r.seeded
    assert r.positions == len({(h.account_ref, h.isin) for h in SEP.holdings})
    assert r.lots_added == 7 and r.cost_pending == 0
    assert dict(r.recon) == {"match": 4} and r.in_transit == 1
    assert len(writer.transactions) == 7
    assert all(row["account_ref"].startswith("acct_") for row in writer.positions)


@pytest.mark.ac("AC-F03.7")
def test_audit_events_carry_counts_never_quantities_or_identifiers() -> None:
    """T-HLD-11"""
    writer = MemoryWriter()
    ctx, _, _ = import_holdings(SEP, "sha256:sep", BROKER, writer)
    text = json.dumps([e.model_dump(mode="json") for e in get_sink().events_for_run(ctx.run_id)])
    assert AUD.HOLDINGS_IMPORT in text
    for value in (*SEP_RAW["investor_info"].values(), *SEP_RAW["_synthetic_pii"].values()):
        assert str(value) not in text
    for a in SEP_RAW["accounts"]:
        assert a["dp_id"] not in text and a["client_id"] not in text
    assert "402.35" not in text and "151.25" not in text  # broker prices


def test_reimport_changes_nothing() -> None:
    """T-HLD-12: same CAS again → no statement, no lots (idempotent)."""
    writer = MemoryWriter()
    import_holdings(SEP, "sha256:sep", BROKER, writer)
    _, _, again = import_holdings(SEP, "sha256:sep", BROKER, writer)
    assert not again.statement_new and again.lots_added == 0 and not again.seeded
    assert dict(again.recon) == {"match": 4}


@pytest.mark.ac("AC-F03.6")
def test_a_new_statement_with_more_shares_creates_one_cost_pending_lot() -> None:
    """T-HLD-13: next month's CAS shows 100 more ITC → one prompt, no guessed cost."""
    writer = MemoryWriter()
    import_holdings(SEP, "sha256:sep", BROKER, writer)
    oct_raw = json.loads(json.dumps(SEP_RAW))
    oct_raw["statement_period"] = {"from_": "01-Oct-2026", "to": "31-Oct-2026"}
    for acct in oct_raw["accounts"]:
        for eq in acct["equities"]:
            if eq["isin"] == "INE154A01025":
                eq["num_shares"] = "500.000"
            if eq["isin"] == "INE12UN01015":
                eq["num_shares"] = "200.000"  # the 30 Sep buy has settled
    october = from_casparser(oct_raw, b"k")
    _, _, r = import_holdings(october, "sha256:oct", BROKER, writer)
    assert r.statement_new and not r.seeded and r.lots_added == 1 and r.cost_pending == 1
    pending = writer.lots[-1]
    assert pending.isin == "INE154A01025" and pending.qty == 100 and pending.price_inr is None


@pytest.mark.ac("AC-F03.4")
def test_private_files_are_refused_at_commit() -> None:
    """T-HLD-14 (pre-commit hook)."""
    blocked = [
        "holdings.yaml",
        "data/holdings_2026.csv",
        "NSDLe-CAS_105567665_AUG_2026.PDF",
        "Stocks_PnL_Report_123_01-07-2025_29-09-2026.xlsx",
        "parakh-backup-key.txt",
        ".env",
        "FILES FOR ANALYSIS/M & M.xlsx",
    ]
    assert len(problems(blocked, read=lambda p: b"")) == len(blocked)
    allowed = [
        "holdings.enc.age",
        "tests/fixtures/cas/synthetic_cas_2026-09.json",
        "tests/fixtures/broker/synthetic_groww_pnl.xlsx",
        "src/parakh/holdings/lots.py",
        ".env.example",
    ]
    assert problems(allowed, read=lambda p: b"print('ok')") == []
    secret = b"AGE-SECRET-KEY-1" + b"Q" * 58
    assert problems(["notes.txt"], read=lambda p: secret) == [
        "notes.txt: contains an age private key"
    ]
