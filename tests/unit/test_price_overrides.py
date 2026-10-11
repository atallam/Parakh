"""Accepted real moves and manual bonus adjustments for prices (data_quality.yaml)."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd

from parakh.adapters.prices import apply_price_adjustments
from parakh.configs import load_all
from parakh.quality.prices import check_prices

ISIN = "INE338I01027"


def _frame(closes: dict[dt.date, float]) -> pd.DataFrame:
    days = sorted(closes)
    c = [closes[d] for d in days]
    return pd.DataFrame(
        {
            "isin": ISIN,
            "trade_date": days,
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "adj_close": c,
            "volume": [1000] * len(days),
            "source": "yfinance",
        }
    )


def _adj(divisor: float = 4.0) -> SimpleNamespace:
    return SimpleNamespace(isin=ISIN, before=dt.date(2024, 1, 1), divisor=divisor)


def test_bonus_adjustment_divides_earlier_rows_only() -> None:
    frame = _frame(
        {dt.date(2023, 12, 28): 1200.0, dt.date(2023, 12, 29): 1240.0, dt.date(2024, 1, 1): 310.0}
    )
    out, notes = apply_price_adjustments(frame, ISIN, [_adj()])
    assert list(out["close"]) == [300.0, 310.0, 310.0]
    assert list(out["volume"]) == [4000, 4000, 1000]
    assert len(notes) == 1 and "divided by 4" in notes[0]


def test_adjustment_is_skipped_once_the_source_is_fixed() -> None:
    fixed = _frame({dt.date(2023, 12, 29): 310.0, dt.date(2024, 1, 1): 312.0})
    out, notes = apply_price_adjustments(fixed, ISIN, [_adj()])
    assert list(out["close"]) == [310.0, 312.0]
    assert "skipped" in notes[0]


def test_other_isins_are_untouched() -> None:
    frame = _frame({dt.date(2023, 12, 29): 1240.0, dt.date(2024, 1, 1): 310.0})
    out, notes = apply_price_adjustments(frame, "INE000000000", [_adj()])
    assert out.equals(frame) and notes == []


def test_configured_overrides_clear_the_known_real_moves() -> None:
    cfg = load_all().data_quality.prices
    assert {m.isin for m in cfg.accepted_moves} == {"INE095A01012", "INE528G01035"}
    assert [a.isin for a in cfg.manual_adjustments] == [ISIN]
    yes = "INE528G01035"
    day = dt.date(2020, 3, 6)
    frame = _frame({dt.date(2020, 3, 5): 36.8, day: 16.15}).assign(isin=yes)
    results = check_prices(frame, yes, day, dt.date(2005, 7, 12), [], cfg)
    gaps = next(r for r in results if r.check_id == "DQ.prices.gaps")
    assert gaps.status == "pass" and gaps.detail["accepted"] == 1
