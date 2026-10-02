"""T-MOM-01…: indicator maths against independent references (AC-F05.2, AC-F05.5)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from parakh.analytics import indicators as ind

# The worked RSI example from Wilder's method as published by StockCharts (14 periods).
CLOSES = np.array(
    [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
        45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
        45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13,
    ]
)  # fmt: skip


@pytest.mark.ac("AC-F05.5")
def test_rsi_matches_the_published_worked_example() -> None:
    """T-MOM-01: first RSI 70.46 on the 15th close, then 66.25, 66.48 (StockCharts)."""
    r = ind.rsi(CLOSES, 14)
    assert r[14] == pytest.approx(70.46, abs=0.05)
    assert r[15] == pytest.approx(66.25, abs=0.05)
    assert r[16] == pytest.approx(66.48, abs=0.05)


def _slow_atr(h: list[float], low: list[float], c: list[float], n: int) -> float:
    tr = [
        max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1])) for i in range(1, len(c))
    ]
    a = sum(tr[:n]) / n
    for v in tr[n:]:
        a = (a * (n - 1) + v) / n
    return a


@pytest.mark.ac("AC-F05.5")
def test_atr_matches_a_plain_loop() -> None:
    """T-MOM-02: vectorised ATR equals an independent loop implementation."""
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, 80))
    h, lo = c + rng.uniform(0.2, 1.5, 80), c - rng.uniform(0.2, 1.5, 80)
    assert ind.atr(h, lo, c, 14) == pytest.approx(
        _slow_atr(list(h), list(lo), list(c), 14), rel=1e-9
    )


@pytest.mark.ac("AC-F05.5")
def test_sma_series_matches_rolling_mean_to_tolerance() -> None:
    """T-MOM-03: moving averages within 0.1% (plan 14 §4.1)."""
    x = np.linspace(100, 200, 300) + np.sin(np.arange(300))
    out = ind.sma_series(x, 50)
    for i in (49, 120, 299):
        assert out[i] == pytest.approx(x[i - 49 : i + 1].mean(), rel=1e-12)
    assert np.isnan(out[48])


@pytest.mark.ac("AC-F05.2")
def test_12_1_momentum_ignores_the_latest_month() -> None:
    """T-MOM-04: a spike in the last 21 sessions does not move 12-1 momentum."""
    base = np.linspace(100, 150, 300)
    spiked = base.copy()
    spiked[-10:] *= 1.5
    assert ind.ret_12_1(base) == pytest.approx(ind.ret_12_1(spiked))
    assert ind.ret(base, 252) != pytest.approx(ind.ret(spiked, 252))
    assert ind.ret_12_1(base[:200]) is None


def test_return_needs_n_plus_one_closes_and_vol_annualises() -> None:
    """T-MOM-05"""
    x = np.array([100.0, 101, 102])
    assert ind.ret(x, 2) == pytest.approx(0.02)
    assert ind.ret(x, 3) is None
    rng = np.random.default_rng(0)
    p = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    v = ind.ann_vol(p, 252)
    assert v is not None and v == pytest.approx(0.01 * math.sqrt(252), rel=0.15)


def test_percentile_rank_and_mansfield() -> None:
    """T-MOM-06"""
    assert ind.percentile_rank(0.5, [0.1, 0.2, 0.5, 0.9]) == 75.0
    assert ind.percentile_rank(0.5, [0.1]) is None
    rs = np.concatenate([np.ones(251), [1.1]])
    assert ind.mansfield(rs, 252) == pytest.approx((1.1 / rs.mean() - 1) * 100)
    assert ind.mansfield(rs[:100], 252) is None


def test_obv_and_up_down_volume() -> None:
    """T-MOM-07"""
    close = np.array([10.0, 11, 10, 12, 12])
    vol = np.array([5.0, 10, 20, 40, 7])
    assert list(ind.obv(close, vol)) == [0, 10, -10, 30, 30]
    assert ind.up_down_volume_ratio(close, vol, 4) == pytest.approx((10 + 40) / 20)
