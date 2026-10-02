"""Shareholding pattern and pledge: both XBRL taxonomies, the exchange summary, and the job.

Fixtures are real filings trimmed to the category totals (no named holders).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from parakh.adapters.shareholding import (
    ShareholdingFormatError,
    parse_shp_master,
    parse_shp_xbrl,
)
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.orchestration.shareholding import load_shareholding

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "shareholding"
BUNDLE = load_all()
MM = "INE101A01026"
ASOF = dt.date(2026, 10, 2)


def _xml(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


MASTER = json.loads(_xml("shp_master_MM.json"))


def test_current_taxonomy_fractions_and_split_institutions() -> None:
    """T-SHP-01: M&M, 30 Jun 2026: 18.45% promoter as on the exchange; pledge of 40,000 shares."""
    s = parse_shp_xbrl(_xml("shp_MM_2026-06-30.xml"))
    assert s.period_end == dt.date(2026, 6, 30) and s.total_shares == 1_243_528_831
    assert s.promoter_pct == 18.45 and s.public_pct == 78.08  # SCRR base, as filed
    assert s.fii_shares == 426_538_111 and s.dii_shares == 399_202_986
    assert s.mf_shares == 221_962_050
    assert s.promoter_pledged_shares == 40_000 and s.promoter_encumbered_shares == 40_000
    assert s.pledge_pct == pytest.approx(0.0177, abs=1e-4)  # of the promoters' own holding


def test_old_taxonomy_whole_percentages_and_one_institutions_line() -> None:
    """T-SHP-02: Sep 2021 filing: percentages are ignored, counts read, institutions split by FPI."""
    s = parse_shp_xbrl(_xml("shp_MM_2021-09-30.xml"))
    assert s.period_end == dt.date(2021, 9, 30)
    assert s.promoter_pct == 19.46 and s.promoter_pledged_shares == 152_000
    assert s.fii_shares is not None and s.dii_shares is not None
    assert s.fii_shares + s.dii_shares == 796_228_128


def test_a_company_without_a_promoter_has_zero_not_missing() -> None:
    """T-SHP-03: HDFC Bank has no promoter context: 0% promoter and 0% pledge."""
    s = parse_shp_xbrl(_xml("shp_HDFCBANK_2026-06-30.xml"))
    assert s.promoter_shares == 0 and s.promoter_pct == 0 and s.pledge_pct == 0
    assert s.fii_pct is not None and s.fii_pct > 30
    with pytest.raises(ShareholdingFormatError):
        parse_shp_xbrl("<xbrli:xbrl></xbrli:xbrl>")


def test_master_lists_one_filing_per_period_newest_first() -> None:
    """T-SHP-04: 20 quarters for M&M; a young listing also has its listing-date pattern."""
    filings = parse_shp_master(MASTER)
    assert len(filings) == 20 and filings[0].period_end == dt.date(2026, 6, 30)
    assert filings[0].reported_on == dt.date(2026, 7, 20) and filings[0].promoter_pct == 18.45
    young = parse_shp_master(json.loads(_xml("shp_master_SHADOWFAX.json")))
    assert [f.period_end.isoformat() for f in young] == ["2026-06-30", "2026-03-31", "2026-01-23"]
    revised = [
        {**MASTER[0], "broadcastDate": "05-AUG-2026 10:00:00", "pr_and_prgrp": "18.40"},
        MASTER[0],
    ]
    assert parse_shp_master(revised)[0].promoter_pct == 18.40  # the later filing wins


class Fetcher:
    def __init__(self, promoter: str | None = None) -> None:
        self.downloads = 0
        self.promoter = promoter

    def shareholding_master(self, symbol: str) -> list[dict[str, Any]]:
        row = dict(MASTER[0])
        if self.promoter:
            row["pr_and_prgrp"] = self.promoter
        return [row]

    def shareholding_xbrl(self, url: str) -> str:
        self.downloads += 1
        return _xml("shp_MM_2026-06-30.xml")


class MemoryWriter:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def stored_shareholding(self, isin: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["isin"] == isin]

    def write_shareholding(self, rows: list[dict[str, Any]]) -> None:
        self.rows += rows


@pytest.mark.ac("AC-F02.3")
def test_job_stores_the_filing_date_beside_every_quarter() -> None:
    """T-SHP-05: the row carries reported_on, source and hash; the tie-out to the exchange passes."""
    writer = MemoryWriter()
    ctx, outcome, report = load_shareholding(BUNDLE, Fetcher(), ["M&M"], ASOF, writer)
    assert outcome.status.startswith("SUCCESS") and report.status == "pass"
    (row,) = writer.rows
    assert (row["isin"], row["period_end"], row["reported_on"]) == (MM, "2026-06-30", "2026-07-20")
    assert row["source_id"] == "nse_archives" and row["raw_hash"].startswith("sha256:")
    assert row["run_id"] == ctx.run_id and row["promoter_pct"] == pytest.approx(18.45, abs=0.005)
    assert {r.check_id for r in report.dq} == {
        "DQ.shareholding.readable",
        "DQ.shareholding.promoter_tieout",
        "DQ.shareholding.coverage",
        "DQ.shareholding.freshness",
    }


@pytest.mark.ac("AC-F02.5")
def test_a_second_load_downloads_nothing() -> None:
    """T-SHP-06: a stored filing is not fetched again."""
    writer, fetcher = MemoryWriter(), Fetcher()
    load_shareholding(BUNDLE, fetcher, ["M&M"], ASOF, writer)
    _, _, again = load_shareholding(BUNDLE, fetcher, ["M&M"], ASOF, writer)
    assert fetcher.downloads == 1 and len(writer.rows) == 1
    assert again.loads[0].added == 0 and again.loads[0].quarters == 1 and again.status == "pass"


@pytest.mark.ac("AC-F02.4")
def test_a_disagreement_with_the_exchange_summary_fails_and_is_audited() -> None:
    """T-SHP-07: XBRL says 18.45%, the summary 25%: the check fails, with an audit event."""
    ctx, _, report = load_shareholding(BUNDLE, Fetcher("25.00"), ["M&M"], ASOF, MemoryWriter())
    assert report.status == "fail"
    events = [e for e in get_sink().events_for_run(ctx.run_id)]
    assert any(
        e.event_type == AUD.DATA_VALIDATION_FAIL and e.reason == "DQ.shareholding.promoter_tieout"
        for e in events
    )
    stale = dt.date(2027, 3, 1)
    _, _, late = load_shareholding(BUNDLE, Fetcher(), ["M&M"], stale, MemoryWriter())
    assert late.status == "warn"


def test_a_listing_day_pattern_is_keyed_by_the_exchange_date() -> None:
    """T-SHP-08: the XBRL says 3 Jul, the exchange list 30 Jun: stored under 30 Jun; a quarter
    apart is refused (first pilot load, 2 Oct 2026)."""

    class Shifted(Fetcher):
        def __init__(self, to: str) -> None:
            super().__init__()
            self.to = to

        def shareholding_xbrl(self, url: str) -> str:
            return super().shareholding_xbrl(url).replace("2026-06-30", self.to)

    writer = MemoryWriter()
    _, _, near = load_shareholding(BUNDLE, Shifted("2026-07-03"), ["M&M"], ASOF, writer)
    assert near.status == "pass" and writer.rows[0]["period_end"] == "2026-06-30"
    _, _, far = load_shareholding(BUNDLE, Shifted("2026-03-31"), ["M&M"], ASOF, MemoryWriter())
    assert far.status == "fail"
    assert parse_shp_master([{**MASTER[0], "revisedData": "Revised"}])[0].revised
