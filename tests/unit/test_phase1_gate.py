"""Phase 1 exit gate: point-in-time reads and data confidence (AC-F02.3, AC-F02.4)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from parakh.configs import load_all
from parakh.quality import DqResult, confidence
from parakh.quality.prices import check_prices
from parakh.storage.point_in_time import SHAREHOLDING_KEY, visible_asof

BUNDLE = load_all()
LAG = BUNDLE.data_quality.fundamentals.assumed_report_lag_days
MM = "INE101A01026"


def _fact(period_end: str, reported_on: str | None, value: float, version: int = 1) -> dict:
    return {
        "isin": MM,
        "metric_id": "quarters.Sales",
        "period_type": "quarter",
        "period_end": period_end,
        "source_id": "screener_export",
        "reported_on": reported_on,
        "value": value,
        "version": version,
    }


@pytest.mark.ac("AC-F02.3")
def test_a_score_for_date_d_sees_only_what_was_reported_by_d() -> None:
    """T-PIT-01: the June quarter (reported 31 Jul) is invisible on 30 Jul and visible on 31 Jul."""
    rows = [_fact("2026-03-31", "2026-05-05", 100.0), _fact("2026-06-30", "2026-07-31", 110.0)]
    before = visible_asof(rows, dt.date(2026, 7, 30), LAG)
    assert [r["period_end"] for r in before] == ["2026-03-31"]
    on_the_day = visible_asof(rows, dt.date(2026, 7, 31), LAG)
    assert sorted(r["period_end"] for r in on_the_day) == ["2026-03-31", "2026-06-30"]


@pytest.mark.ac("AC-F02.3")
def test_a_later_restatement_does_not_leak_into_an_earlier_date() -> None:
    """T-PIT-02: version 2 (restated 10 Nov) is used from 10 Nov; before that, version 1."""
    rows = [
        _fact("2026-06-30", "2026-07-31", 110.0),
        _fact("2026-06-30", "2026-11-10", 108.0, version=2),
    ]
    assert visible_asof(rows, dt.date(2026, 10, 30), LAG)[0]["value"] == 110.0
    assert visible_asof(rows, dt.date(2026, 11, 10), LAG)[0]["value"] == 108.0


@pytest.mark.ac("AC-F02.3")
def test_an_undated_figure_waits_for_the_latest_legal_filing_date() -> None:
    """T-PIT-03: FY2017 with no filing date on record is public 60 days after 31 Mar 2017."""
    rows = [_fact("2017-03-31", None, 50.0)]
    assert visible_asof(rows, dt.date(2017, 5, 29), LAG) == []
    assert len(visible_asof(rows, dt.date(2017, 5, 30), LAG)) == 1
    shp = [
        {
            "isin": MM,
            "period_end": "2026-06-30",
            "reported_on": "2026-07-20",
            "promoter_pct": 18.45,
        },
        {
            "isin": MM,
            "period_end": "2026-06-30",
            "reported_on": "2026-08-05",
            "promoter_pct": 18.40,
        },
    ]
    seen = visible_asof(shp, dt.date(2026, 8, 1), LAG, SHAREHOLDING_KEY)
    assert [r["promoter_pct"] for r in seen] == [18.45]
    assert visible_asof(shp, dt.date(2026, 8, 5), LAG, SHAREHOLDING_KEY)[0]["promoter_pct"] == 18.40


def _prices(closes: dict[dt.date, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "isin": MM,
            "trade_date": list(closes),
            "open": list(closes.values()),
            "high": list(closes.values()),
            "low": list(closes.values()),
            "close": list(closes.values()),
            "adj_close": list(closes.values()),
            "volume": 1000,
            "source": "yfinance",
        }
    )


@pytest.mark.ac("AC-F02.4")
def test_a_negative_price_or_a_stalled_feed_makes_confidence_low() -> None:
    """T-DQ-20: failed validation is named, and the stock is never scored silently."""
    today = dt.date(2026, 9, 30)
    cfg = BUNDLE.data_quality.prices
    listed = dt.date(2026, 9, 21)
    days = [dt.date(2026, 9, d) for d in (21, 22, 23, 24, 25, 28, 29, 30)]
    good = check_prices(_prices({d: 100.0 for d in days}), MM, today, listed, [], cfg)
    assert confidence(good).level == "high"

    negative = {d: 100.0 for d in days} | {days[3]: -5.0}
    bad = confidence(check_prices(_prices(negative), MM, today, listed, [], cfg))
    assert bad.level == "low" and "DQ.prices.schema" in bad.reasons

    stalled = {d: 100.0 for d in days[:3]}  # nothing after 23 Sep: 5 trading days missing
    late = confidence(check_prices(_prices(stalled), MM, today, listed, [], cfg))
    assert late.level == "low" and late.reasons == ("DQ.prices.stale",)

    assert confidence([DqResult("DQ.reference.index_size_x", "*", "warn")]).level == "medium"


def test_scorecard_takes_the_newest_run_and_names_what_failed() -> None:
    """T-DQ-21: an old failure fixed by a later run no longer counts; a warning is half a pass."""
    from parakh.quality.scorecard import scorecard

    def row(run: str, check: str, isin: str, status: str) -> dict:
        return {"run_id": run, "check_id": check, "isin": isin, "status": status, "detail": {}}

    rows = [
        row("01A", "DQ.prices.stale", MM, "fail"),
        row("01B", "DQ.prices.stale", MM, "pass"),
        row("01B", "DQ.prices.schema", MM, "pass"),
        row("01B", "DQ.fundamentals.tieout", MM, "pass"),
        row("01C", "DQ.reference.index_size_nifty_smallcap_250", "*", "warn"),
        row("01C", "DQ.shareholding.coverage", "INE040A01034", "fail"),
    ]
    card = scorecard(rows, {MM: "M&M", "INE040A01034": "HDFCBANK"})
    assert [r.symbol for r in card.rows] == ["HDFCBANK", "M&M", "(run-level)"]
    mm = card.rows[1]
    assert mm.areas == {"prices": "pass", "fundamentals": "pass"} and mm.confidence.level == "high"
    assert card.rows[0].confidence.reasons == ("DQ.shareholding.coverage",)
    assert card.checks == 5 and card.score_pct == 70.0  # (3 + 0.5) of 5
