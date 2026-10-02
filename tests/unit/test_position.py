"""Position context from tax lots: weights, cost pending, long-term timing, tax estimate (F09; UX-11)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.configs import load_all
from parakh.holdings.lots import Lot
from parakh.holdings.position import positions_from_lots

RATES = load_all().portfolio.tax
ASOF = dt.date(2026, 9, 30)


def lot(i: str, isin: str, qty: float, price: float | None, bought: dt.date) -> Lot:
    return Lot(i, "acct", isin, qty, bought, bought, price, "cli")


def test_cost_pending_is_never_guessed() -> None:
    pos = positions_from_lots(
        [lot("1", "A", 10, None, dt.date(2025, 1, 1))], {"A": 100.0}, ASOF, RATES
    )["A"]
    assert (
        pos.cost_pending
        and pos.avg_cost_inr is None
        and pos.pnl_pct is None
        and pos.tax_if_sold_now_inr is None
    )
    assert pos.market_value_inr == 1000.0


def test_weights_use_only_holdings_with_a_price() -> None:
    lots = [
        lot("1", "A", 10, 90.0, dt.date(2025, 1, 1)),
        lot("2", "B", 30, 50.0, dt.date(2025, 1, 1)),
        lot("3", "NOPRICE", 5, 10.0, dt.date(2025, 1, 1)),
    ]
    out = positions_from_lots(lots, {"A": 100.0, "B": 100.0}, ASOF, RATES)
    assert out["A"].weight_pct == pytest.approx(25.0) and out["B"].weight_pct == pytest.approx(75.0)
    assert "NOPRICE" not in out or out["NOPRICE"].weight_pct is None


def test_long_term_split_and_days_to_the_next_one() -> None:
    lots = [
        lot("1", "A", 10, 90.0, dt.date(2025, 1, 1)),
        lot("2", "A", 10, 95.0, ASOF - dt.timedelta(days=335)),
    ]
    pos = positions_from_lots(lots, {"A": 100.0}, ASOF, RATES)["A"]
    assert pos.lots == 2 and pos.lots_long_term == 1 and pos.qty_long_term == 10
    assert (
        pos.days_to_long_term == RATES.long_term_days + 1 - 335
    )  # long term once held more than a year
    assert pos.pnl_pct == pytest.approx((100 - 92.5) / 92.5 * 100)
