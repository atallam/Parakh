"""D24 profile inputs: described lines in results XBRL and a holding company's listed stakes.

Fixtures keep the real structure and the real filed amounts (IndiGo FY2026 consolidated; Tech
Mahindra's June 2026 pattern), cut down to the lines read. Totals in the Tech Mahindra file are
round stand-ins; only the M&M row is as filed.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from parakh.adapters.profile_inputs import described_lines, pick
from parakh.adapters.shareholding import company_key, holder_stake, parse_shp_xbrl
from parakh.adapters.xbrl import Filing
from parakh.configs import load_all
from parakh.orchestration.profile_inputs import load_profile_inputs

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "profile"
INDIGO_XML = (FIX / "results_INDIGO_2026-03-31_described.xml").read_text(encoding="utf-8")
TECHM_XML = (FIX / "shp_TECHM_2026-06-30_holder.xml").read_text(encoding="utf-8")
BUNDLE = load_all()
INDIGO, MM, MAZDOCK = "INE646L01027", "INE101A01026", "INE249Z01020"


def test_described_lines_give_the_quarter_and_the_balance_not_the_year_to_date() -> None:
    """T-PRF-01: IndiGo Q4 FY26: rentals ₹762.9 Cr (quarter, not the ₹2,084.7 Cr year);
    lease liabilities ₹64,470.5 Cr + ₹11,472.4 Cr at 31 Mar 2026."""
    lines = described_lines(INDIGO_XML)
    assert pick(lines, "OtherExpenses", "aircraft and engine rentals", "flow") == 762.9
    assert pick(lines, "OtherExpenses", "supplementary rentals", "flow") == 3193.3
    assert (
        pick(lines, "OtherNoncurrentFinancialLiabilities", "lease liabilit", "balance") == 64470.5
    )
    assert pick(lines, "OtherCurrentFinancialLiabilities", "lease liabilit", "balance") == 11472.4
    assert pick(lines, "OtherExpenses", "lease liabilit", "flow") is None
    assert {x.period_end for x in lines} == {dt.date(2026, 3, 31)}


def test_holder_stake_reads_only_the_named_company() -> None:
    """T-PRF-02: M&M holds 24,80,22,598 Tech Mahindra shares = 25.31%; a look-alike group
    company is not added in."""
    scale = parse_shp_xbrl(TECHM_XML).pct_scale
    stake = holder_stake(TECHM_XML, "Mahindra & Mahindra Limited", scale)
    assert stake is not None and stake.shares == 248_022_598 and stake.stake_pct == 25.31
    assert holder_stake(TECHM_XML, "Mahindra and Mahindra Ltd", scale) == stake
    assert holder_stake(TECHM_XML, "Tata Sons Private Limited", scale) is None
    assert company_key("Gromax Agri Equipment Limited (Formerly known as X Limited)") == (
        "gromax agri equipment"
    )


class Results:
    def __init__(self, xml: str = INDIGO_XML) -> None:
        self.xml = xml

    def filings(self, symbol: str) -> list[Filing]:
        when = dt.datetime(2026, 5, 29, 15, 44)
        return [
            Filing(symbol, dt.date(2026, 3, 31), True, when, "u/cons.xml", "nse_integrated"),
            Filing(symbol, dt.date(2026, 3, 31), False, when, "u/sa.xml", "nse_integrated"),
        ]

    def xbrl(self, url: str) -> str:
        assert url == "u/cons.xml"  # the configured basis only
        return self.xml


class Patterns:
    def shareholding_master(self, symbol: str) -> list[dict[str, Any]]:
        return [
            {
                "date": "30-JUN-2026",
                "broadcastDate": "20-JUL-2026 14:07:50",
                "pr_and_prgrp": "34.97",
                "public_val": "65.03",
                "xbrl": f"u/{symbol}.xml",
            }
        ]

    def shareholding_xbrl(self, url: str) -> str:
        return TECHM_XML if url == "u/TECHM.xml" else TECHM_XML.replace("Mahindra &amp;", "X")


class Writer:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def write_fundamentals(self, rows: list[dict[str, Any]], run_id: str) -> tuple[int, int]:
        self.rows += rows
        return len(rows), 0


@pytest.mark.ac("AC-F02.3")
def test_job_stores_filed_values_with_their_broadcast_date() -> None:
    """T-PRF-03: rows are `profile.*` fundamentals from the T1 source, dated when filed; an
    item no filing contains (MAZDOCK's, in an IndiGo file) fails the check, it is not guessed."""
    writer = Writer()
    ctx, outcome, loads = load_profile_inputs(BUNDLE, Results(), Patterns(), writer)
    by = {x.isin: x for x in loads}
    assert set(by) == {INDIGO, MM, MAZDOCK} and outcome.status.startswith("SUCCESS")
    lease = next(
        r for r in writer.rows if r["metric_id"] == "profile.lease_liabilities_noncurrent_cr"
    )
    assert (lease["isin"], lease["period_end"], lease["reported_on"]) == (
        INDIGO,
        "2026-03-31",
        "2026-05-29",
    )
    assert lease["value"] == 64470.5 and lease["source_id"] == "nse_archives"
    assert lease["raw_hash"].startswith("sha256:") and lease["unit"] == "cr"
    assert by[INDIGO].status == "pass"
    assert by[MAZDOCK].status == "fail"
    assert by[MAZDOCK].dq[0].detail["missing"] == ["contract_liabilities_cr", "subcontract_cost_cr"]
    stakes = by[MM].latest()
    assert stakes["profile.stake_pct.TECHM"] == ("2026-06-30", 25.31)
    assert by[MM].dq[0].detail["missing_in_latest_filing"] == [
        "M&MFIN",
        "MAHLIFE",
        "MHRIL",
        "MAHLOG",
        "SWARAJENG",
        "MAHEPC",
    ]
