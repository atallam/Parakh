"""XIRR, drawdown, HHI against hand-computed cases (F10 v2; AC-F10.4)."""

from __future__ import annotations

import datetime as dt
import math

import pytest

from parakh.holdings.xirr import benchmark_xirr, hhi, max_drawdown, top_n_share, xirr
from parakh.services.risk import portfolio_risk

D = dt.date


@pytest.mark.ac("AC-F10.4")
def test_xirr_one_year_twenty_percent() -> None:
    # 100 in on 1 Jan 2025, 120 out on 1 Jan 2026 (365 days): exactly 20%
    assert xirr([(D(2025, 1, 1), -100), (D(2026, 1, 1), 120)]) == pytest.approx(0.20, abs=1e-6)


@pytest.mark.ac("AC-F10.4")
def test_xirr_two_lots_hand_computed() -> None:
    # -100 on day 0, -100 on day 365, +230 on day 730 (2 years).
    # Solve -100 - 100/(1+r) + 230/(1+r)^2 = 0, with x = 1+r: 100x^2 + 100x - 230 = 0
    x = (-100 + math.sqrt(100**2 + 4 * 100 * 230)) / (2 * 100)
    got = xirr([(D(2024, 1, 1), -100), (D(2024, 12, 31), -100), (D(2025, 12, 31), 230)])
    assert got == pytest.approx(x - 1, abs=1e-5)


def test_xirr_refuses_what_it_cannot_say() -> None:
    assert xirr([(D(2025, 1, 1), -100)]) is None
    assert xirr([(D(2025, 1, 1), -100), (D(2026, 1, 1), -50)]) is None  # no inflow
    assert xirr([(D(2025, 1, 1), -100), (D(2025, 1, 3), 101)]) is None  # two days is noise


def test_a_loss_gives_a_negative_rate() -> None:
    assert xirr([(D(2025, 1, 1), -100), (D(2026, 1, 1), 80)]) == pytest.approx(-0.20, abs=1e-6)


@pytest.mark.ac("AC-F10.4")
def test_max_drawdown() -> None:
    assert max_drawdown([100, 120, 90, 110]) == pytest.approx(-0.25)
    assert max_drawdown([1, 2, 3]) == 0.0
    assert max_drawdown([5]) is None


@pytest.mark.ac("AC-F10.4")
def test_hhi_and_top_five() -> None:
    assert hhi([40, 30, 20, 10]) == pytest.approx(0.30)
    assert hhi([100]) == pytest.approx(1.0)
    assert hhi([]) is None
    assert top_n_share([30, 25, 20, 10, 8, 4, 3], 5) == pytest.approx(93.0)


def test_benchmark_xirr_matches_the_index_return() -> None:
    series = {D(2025, 1, 1): 100.0, D(2026, 1, 1): 110.0}
    # one lot on the first day: the benchmark simply grew 10% in 365 days
    assert benchmark_xirr([(D(2025, 1, 1), 5000.0)], series, D(2026, 1, 1)) == pytest.approx(
        0.10, abs=1e-6
    )
    assert (
        benchmark_xirr([(D(2024, 6, 1), 5000.0)], series, D(2026, 1, 1)) is None
    )  # before the series


def test_portfolio_risk_block() -> None:
    rows = [
        {"weight_pct": 50.0, "drawdown_pct": -12.0},
        {"weight_pct": 50.0, "drawdown_pct": -30.0},
    ]
    r = portfolio_risk(rows)
    assert r["hhi"] == 0.5 and r["effective_n"] == 2.0 and r["worst_drawdown_pct"] == -30.0
    assert portfolio_risk([])["hhi"] is None
