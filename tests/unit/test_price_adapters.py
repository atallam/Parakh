"""Exchange and Yahoo price parsers, NSE corporate actions, cross-source check. T-ADP-40…"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from parakh.adapters.corporate_actions import (
    CorporateAction,
    parse_nse_corporate_actions,
    parse_nse_subject,
)
from parakh.adapters.prices import (
    PriceSourceError,
    cross_check_closes,
    normalize_yahoo,
    parse_bse_bhavcopy,
    parse_equity_list,
    parse_nse_bhavcopy,
)

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
MM, HDFC, MAZDOCK_NEW, MAZDOCK_OLD = "INE101A01026", "INE040A01034", "INE249Z01020", "INE249Z01012"


def test_nse_bhavcopy_parses_equity_series_unadjusted() -> None:
    """T-ADP-40"""
    frame = parse_nse_bhavcopy((SRC / "nse" / "BhavCopy_NSE_CM_20260928.csv.zip").read_bytes())
    assert set(frame["series"]) <= {"EQ", "BE", "BZ"}
    mm = frame[frame["isin"] == MM].iloc[0]
    assert (mm["symbol"], mm["trade_date"], mm["close"]) == ("M&M", dt.date(2026, 9, 28), 2995.0)
    assert mm["volume"] == 2078624 and mm["source"] == "nse_archives"


def test_bse_bhavcopy_uses_the_same_layout() -> None:
    """T-ADP-41"""
    frame = parse_bse_bhavcopy(
        (SRC / "bse" / "BhavCopy_BSE_CM_20260928_pilot_and_first40.csv").read_bytes()
    )
    assert frame[frame["isin"] == HDFC].iloc[0]["close"] == 718.85
    with pytest.raises(PriceSourceError, match="UDiFF"):
        parse_bse_bhavcopy(b"a,b\n1,2\n")


def test_equity_list_gives_listing_dates() -> None:
    """T-ADP-42 (D24: young listings are bounded by their listing date)."""
    listings = parse_equity_list((SRC / "nse" / "EQUITY_L_2026-09-29.csv").read_bytes())
    assert listings["INE0LEZ01016"].listed_on == dt.date(2025, 5, 6)
    assert listings["INE12UN01015"].listed_on == dt.date(2026, 1, 28)
    assert listings[MAZDOCK_NEW].face_value_inr == 5


def test_nse_corporate_actions_resolve_the_pre_split_isin() -> None:
    """T-ADP-43: the feed keeps INE249Z01012 on every row (spike ④)."""
    rows = json.loads(
        (SRC / "nse" / "corp_actions_MAZDOCK_2026-09-29.json").read_text(encoding="utf-8")
    )
    actions = parse_nse_corporate_actions(rows, {MAZDOCK_OLD: MAZDOCK_NEW}.get)  # type: ignore[arg-type]
    assert {a.isin for a in actions} == {MAZDOCK_NEW}
    split = [a for a in actions if a.type == "split"]
    assert [(a.ex_date, a.ratio) for a in split] == [(dt.date(2024, 12, 27), 2.0)]
    dividends = [a for a in actions if a.type == "dividend"]
    assert len(dividends) == 14
    assert dividends[-1].ex_date == dt.date(2026, 8, 20) and dividends[-1].amount_inr == 4.62


def test_subject_lines() -> None:
    """T-ADP-44"""
    assert parse_nse_subject("Bonus 1:1") == [("bonus", 1.0, None)]
    assert parse_nse_subject("Bonus 3:2") == [("bonus", 1.5, None)]
    assert parse_nse_subject(
        "Dividend - Rs 5 Per Share / Special Dividend - Rs 2.50 Per Share"
    ) == [("dividend", 0.0, 7.5)]
    assert parse_nse_subject("Annual General Meeting") == []


def test_yahoo_history_is_normalised() -> None:
    """T-ADP-45: tz-aware index to IST dates; empty closes dropped, never filled."""
    idx = pd.DatetimeIndex(["2026-09-24", "2026-09-25", "2026-09-28"]).tz_localize("Asia/Kolkata")
    hist = pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0],
            "High": [11.0, 12.0, 13.0],
            "Low": [9.0, 10.0, 11.0],
            "Close": [10.5, np.nan, 12.5],
            "Adj Close": [10.4, np.nan, 12.5],
            "Volume": [100, 0, 300],
        },
        index=idx,
    )
    frame = normalize_yahoo(hist, MM)
    assert list(frame["trade_date"]) == [dt.date(2026, 9, 24), dt.date(2026, 9, 28)]
    assert list(frame.columns) == [
        "isin",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "source",
    ]
    with pytest.raises(PriceSourceError):
        normalize_yahoo(hist.drop(columns="Adj Close"), MM)


def test_cross_check_back_adjusts_the_exchange_close() -> None:
    """T-ADP-46: HDFCBANK's 1:1 bonus (ex 26 Aug 2025): exchange 1,600 before = Yahoo 800."""
    days = [dt.date(2025, 8, 25), dt.date(2025, 8, 26)]
    yahoo = pd.DataFrame({"trade_date": days, "close": [800.0, 805.0]})
    exch = pd.DataFrame({"trade_date": days, "close": [1600.0, 805.0]})
    bonus = CorporateAction(HDFC, dt.date(2025, 8, 26), "bonus", 1.0)
    assert all(c.ok for c in cross_check_closes(yahoo, exch, [bonus], tolerance_pct=1.0))
    missing = cross_check_closes(yahoo, exch, [], tolerance_pct=1.0)
    assert [c.ok for c in missing] == [False, True]
    assert missing[0].diff_pct == pytest.approx(50.0)
