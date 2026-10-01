"""XBRL map, filing lists, fundamentals load job and versioning (no network). T-FUN-01…"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from parakh.adapters.xbrl import (
    NET_COST,
    Filing,
    first_reported,
    parse_financial_results,
    parse_integrated_filings,
    parse_xbrl,
    screener_lines,
    screener_quarter,
)
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.orchestration.fundamentals import load_fundamentals
from parakh.quality.fundamentals import normalize_name, tieout
from parakh.storage.supabase_repo import plan_fundamental_inserts

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
NSE = SRC / "nse"
MM_EXPORT = (SRC / "screener" / "MM_export_2026-09-27.xlsx").read_bytes()
BUNDLE = load_all()
CFG = BUNDLE.data_quality.fundamentals


def _xbrl(name: str) -> str:
    return (NSE / name).read_text(encoding="utf-8")


def test_indas_map_ties_mm_to_the_paisa() -> None:
    """T-FUN-01: Dec 2024 (old feed) and Jun 2026 (integrated filing) against Screener."""
    dec = screener_lines(parse_xbrl(_xbrl("xbrl_MM_2024-12-31_consolidated.xml")))
    screener_dec = screener_quarter(
        {"Sales": 41470.05, "Expenses": 33239.32, "Other Income": 718.59, "Depreciation": 1495.17,
         "Interest": 2362.16, "Profit before tax": 5091.99, "Tax": 1467.51, "Net profit": 3180.58}
    )  # fmt: skip
    compared, bad = tieout(screener_dec, dec, CFG)
    assert bad == [] and len(compared) == 7
    jun = parse_xbrl(_xbrl("xbrl_MM_2026-06-30_consolidated.xml"))
    assert (jun.period_end, jun.consolidated, jun.taxonomy) == (dt.date(2026, 6, 30), True, "indas")
    lines = screener_lines(jun)
    assert lines["Profit before tax"] == 7628.09  # 7,260.60 + 367.49 associates
    assert lines[NET_COST] == pytest.approx(
        47360.43 - 1121.33
    )  # Screener's split differs by ₹262 Cr


def test_bank_map_ties_hdfc_bank() -> None:
    """T-FUN-02: banks file a different taxonomy."""
    x = parse_xbrl(_xbrl("xbrl_HDFCBANK_2026-06-30_consolidated.xml"))
    assert x.taxonomy == "banking"
    screener = screener_quarter(
        {"Sales": 90575.33, "Expenses": 58291.57, "Other Income": 42535.03, "Interest": 47625.63,
         "Profit before tax": 27193.16, "Tax": 6810.47, "Net profit": 19244.71}
    )  # fmt: skip
    compared, bad = tieout(screener, screener_lines(x), CFG)
    assert bad == [] and {"Sales", "Expenses", "Net profit"} <= set(compared)


def test_a_wrong_line_is_a_mismatch() -> None:
    """T-FUN-03"""
    _, bad = tieout({"Sales": 41480.05}, {"Sales": 41470.05}, CFG)
    assert bad and bad[0]["diff_cr"] == 10.0


def test_filing_lists_and_reported_on() -> None:
    """T-FUN-04: the old feed ends Dec 2024; the integrated filing carries Mar 2025 on."""
    old = parse_financial_results(
        json.loads((NSE / "financial_results_MM_2026-09-29.json").read_text(encoding="utf-8"))
    )
    new = parse_integrated_filings(
        json.loads((NSE / "integrated_filing_MM_2026-10-01.json").read_text(encoding="utf-8"))
    )
    assert max(f.period_end for f in old) == dt.date(2024, 12, 31)
    assert min(f.period_end for f in new) == dt.date(2025, 3, 31) and len(new) == 12
    when = first_reported(old + new)
    assert when[dt.date(2026, 6, 30)] == dt.datetime(
        2026, 7, 30, 16, 11, 10
    )  # standalone, 1 s earlier


def test_names_match_across_spellings() -> None:
    """T-FUN-05: the export's COMPANY NAME vs universe.yaml."""
    assert normalize_name("MAHINDRA & MAHINDRA LTD") == normalize_name("Mahindra & Mahindra Ltd")
    assert normalize_name("INTERGLOBE AVIATION LTD") == normalize_name(
        "InterGlobe Aviation Limited"
    )


class RecordedFilings:
    """M&M filings from the recorded feeds; only filings whose XBRL is recorded are listed."""

    XML = {
        "INDAS_119053_1374435_07022025041001.xml": "xbrl_MM_2024-12-31_consolidated.xml",
        "INTEGRATED_FILING_INDAS_1705129_30072026041119_WEB.xml": "xbrl_MM_2026-06-30_consolidated.xml",
    }

    def __init__(self) -> None:
        old = json.loads((NSE / "financial_results_MM_2026-09-29.json").read_text(encoding="utf-8"))
        new = json.loads((NSE / "integrated_filing_MM_2026-10-01.json").read_text(encoding="utf-8"))
        self.all = parse_financial_results(old) + parse_integrated_filings(new)

    def filings(self, symbol: str) -> list[Filing]:
        return [f for f in self.all if f.xbrl_url.rsplit("/", 1)[-1] in self.XML]

    def xbrl(self, url: str) -> str:
        return _xbrl(self.XML[url.rsplit("/", 1)[-1]])


class MemoryWriter:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def write_fundamentals(self, rows: list[dict[str, Any]], run_id: str) -> tuple[int, int]:
        self.rows.extend(rows)
        return len(rows), 0


def test_load_job_checks_stamps_and_writes() -> None:
    """T-FUN-06 (AC-F02 shape): M&M export → 460 facts with lineage, XBRL tie-out passes."""
    bundle = load_all()
    deep = bundle.data_quality.fundamentals.model_copy(update={"xbrl_quarters": 10})
    bundle = dataclasses.replace(
        bundle, data_quality=bundle.data_quality.model_copy(update={"fundamentals": deep})
    )
    writer = MemoryWriter()
    ctx, outcome, (load,) = load_fundamentals(
        bundle, [MM_EXPORT], RecordedFilings(), writer, today=dt.date(2026, 9, 30)
    )
    status = {r.check_id: r.status for r in load.dq}
    assert load.symbol == "M&M" and load.facts == 460 == len(writer.rows)
    assert status["DQ.fundamentals.history"] == "pass"
    assert status["DQ.fundamentals.recency"] == "pass"
    assert status["DQ.fundamentals.export"] == "warn"  # blank META share count, trust shares
    tie = next(r for r in load.dq if r.check_id == "DQ.fundamentals.xbrl_tieout")
    assert tie.status == "pass" and tie.detail["compared_quarters"] == 2
    assert {q["source"] for q in tie.detail["quarters"]} == {"nse_results", "nse_integrated"}
    row = next(
        r
        for r in writer.rows
        if r["metric_id"] == "quarterly_pl.Sales" and r["period_end"] == "2026-06-30"
    )
    assert row["reported_on"] == "2026-07-30" and row["raw_hash"].startswith("sha256:")
    assert row["source_id"] == "screener_export" and row["period_type"] == "quarter"
    types = [e.event_type for e in get_sink().events_for_run(ctx.run_id)]
    assert types.count(AUD.RUN_START) == 1 and AUD.DATA_FETCH in types


def test_an_unknown_company_is_skipped_and_audited() -> None:
    """T-FUN-07"""
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(MM_EXPORT))
    wb["Data Sheet"]["B1"] = "SOME OTHER COMPANY LTD"
    buf = io.BytesIO()
    wb.save(buf)
    ctx, outcome, loads = load_fundamentals(BUNDLE, [buf.getvalue()], today=dt.date(2026, 9, 30))
    assert loads == [] and outcome.summary["unmatched"] == 1
    assert any(
        e.reason == "DQ.fundamentals.unmatched" for e in get_sink().events_for_run(ctx.run_id)
    )


def test_versioning_skips_unchanged_and_appends_restatements() -> None:
    """T-FUN-08: fundamentals are append-only; a changed value is a new version."""
    row = {"isin": "INE101A01026", "metric_id": "annual_pl.Sales", "period_type": "annual",
           "period_end": "2026-03-31", "source_id": "screener_export", "value": 100.0}  # fmt: skip
    key = tuple(row[k] for k in ("isin", "metric_id", "period_type", "period_end", "source_id"))
    new, restated = plan_fundamental_inserts([row], {}, "R1")
    assert restated == 0 and new[0]["version"] == 1
    assert plan_fundamental_inserts([row], {key: (1, 100.0)}, "R2") == ([], 0)
    new, restated = plan_fundamental_inserts([{**row, "value": 101.0}], {key: (1, 100.0)}, "R3")
    assert restated == 1 and new[0]["version"] == 2 and new[0]["run_id"] == "R3"


def test_a_filing_without_a_broadcast_date_uses_its_creation_date() -> None:
    """T-FUN-09: seen on the first real load (2 Oct 2026)."""
    row = {"symbol": "X", "qe_Date": "30-JUN-2026", "consolidated": "Consolidated",
           "broadcast_Date": None, "creation_Date": "01-Aug-2026 10:00:00", "xbrl": "https://a/b.xml"}  # fmt: skip
    (f,) = parse_integrated_filings({"data": [row]})
    assert f.broadcast_at == dt.datetime(2026, 8, 1, 10, 0)
    assert parse_integrated_filings({"data": [{**row, "creation_Date": None}]}) == []
