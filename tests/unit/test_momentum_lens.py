"""T-MOM-10…: momentum metrics, history rules, signals and the lens (AC-F05.1–9)."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from parakh.analytics.momentum_build import momentum_context_parts, momentum_inputs
from parakh.analytics.momentum_calc import Calc, exclude_listing, make_bars
from parakh.analytics.signals.momentum import SIGNAL_DEFS, evaluate_signals
from parakh.configs import load_file
from parakh.configs.lens_models import MomentumConfig
from parakh.lenses.base import LensConfig, StockContext
from parakh.lenses.momentum import MomentumLens, cap_weights
from tests.helpers.prices import make_index, make_prices

ASOF = dt.date(2026, 10, 30)
CFG = load_file("momentum.yaml", MomentumConfig)
M = "MET.momentum."


def _context(
    prices: pd.DataFrame,
    cap: str = "mid",
    listed_on: dt.date | None = None,
    bench: pd.Series | None = None,
) -> tuple[StockContext, Calc]:
    inp = momentum_inputs("INE000000000", "TEST", cap, ASOF, prices, CFG, listed_on, bench=bench)
    values, reasons, extras = momentum_context_parts(inp, CFG)
    c = Calc(inp, CFG)
    ctx = StockContext(
        isin="INE000000000",
        symbol="TEST",
        asof=ASOF,
        profile="standard",
        cap=cap,
        metrics=values,
        na_reasons=reasons,
        extras=extras,
    )
    return ctx, c


@pytest.mark.ac("AC-F05.7")
def test_first_20_sessions_after_listing_are_excluded() -> None:
    """T-MOM-10: history that starts at listing loses its first 20 sessions; older history is kept."""
    young = make_prices(100)
    listed = young["trade_date"].iloc[0]
    bars, dropped = exclude_listing(make_bars(young, ASOF), listed, CFG)
    assert dropped == 20 and len(bars) == 80
    old = make_prices(400)
    _, dropped_old = exclude_listing(make_bars(old, ASOF), dt.date(2015, 11, 10), CFG)
    assert dropped_old == 0


@pytest.mark.ac("AC-F05.8")
def test_missing_history_is_na_with_a_reason_never_zero() -> None:
    """T-MOM-11: 100 sessions: 1M/3M exist, 6M/12M/200 DMA are N/A with reasons."""
    ctx, _ = _context(make_prices(100), bench=make_index(make_prices(100)))
    assert ctx.metrics[M + "excess_return_1m"] is not None
    assert ctx.metrics[M + "excess_return_3m"] is not None
    for key in ("excess_return_6m", "excess_return_12m", "mom_12_1", "dma200", "dma150"):
        assert ctx.metrics[M + key] is None
        assert "needs" in ctx.na_reasons[M + key]
    assert ctx.metrics[M + "dma50"] is not None


@pytest.mark.ac("AC-F05.8")
def test_200_dma_signals_never_fire_before_200_sessions() -> None:
    """T-MOM-12: M06, M10, M11, M21 and M24 report 'cannot evaluate' with 150 sessions."""
    _, c = _context(make_prices(150))
    states = {s.id: s for s in evaluate_signals(c)}
    for sid in ("M06", "M10", "M11", "M21", "M24"):
        assert states[sid].status == "cannot_evaluate", sid


@pytest.mark.ac("AC-F05.8")
def test_since_listing_high_is_labelled() -> None:
    """T-MOM-13: with 126–251 sessions the 52-week high is since listing and the flag says so."""
    ctx, _ = _context(make_prices(200))
    assert ctx.metrics[M + "pct_from_52w_high"] is not None
    assert any("since listing" in f for f in ctx.extras["flags"])
    ctx_full, _ = _context(make_prices(400))
    assert not any("since listing" in f for f in ctx_full.extras["flags"])


@pytest.mark.ac("AC-F05.9")
def test_under_126_sessions_the_lens_is_informational_and_low_confidence() -> None:
    """T-MOM-14"""
    ctx, _ = _context(make_prices(110))
    res = MomentumLens().evaluate(ctx, LensConfig(lens_version="1"))
    assert res.informational and res.confidence == "Low"
    assert any("limited history" in f for f in res.flags)


@pytest.mark.ac("AC-F05.9")
def test_126_to_251_sessions_caps_confidence_and_reports_template_x_of_y() -> None:
    """T-MOM-15"""
    ctx, _ = _context(make_prices(220), bench=make_index(make_prices(220)))
    res = MomentumLens().evaluate(ctx, LensConfig(lens_version="1"))
    assert not res.informational
    assert res.confidence in ("Med", "Low")
    tt = res.details["trend_template"]
    assert tt["computable"] < 8 and tt["of"] == 8


@pytest.mark.ac("AC-F05.1")
def test_benchmark_follows_the_cap() -> None:
    """T-MOM-16: mid caps are measured against Nifty Midcap 150, large against Nifty 100."""
    mid, _ = _context(make_prices(300), cap="mid")
    large, _ = _context(make_prices(300), cap="large")
    assert (
        MomentumLens().evaluate(mid, LensConfig(lens_version="1")).details["benchmark"]
        == "NIFTY MIDCAP 150"
    )
    assert (
        MomentumLens().evaluate(large, LensConfig(lens_version="1")).details["benchmark"]
        == "NIFTY 100"
    )


def test_cap_weights_shift_and_still_sum_to_100() -> None:
    """T-MOM-17"""
    for cap in ("large", "mid", "small"):
        assert sum(cap_weights(CFG, cap).values()) == pytest.approx(100)
    assert cap_weights(CFG, "large")["rs"] == 35


def test_a_smooth_uptrend_scores_strong_and_a_decline_scores_weak() -> None:
    """T-MOM-18"""
    up = make_prices(400, drift=0.0012, vol=0.006)
    ctx, _ = _context(up, bench=make_index(up, drift=0.0002))
    res = MomentumLens().evaluate(ctx, LensConfig(lens_version="1"))
    assert res.score is not None and res.score > 60
    assert res.view in ("STRONG", "NEUTRAL")
    assert res.details["stage"] == 2
    down = make_prices(400, drift=-0.0015, vol=0.006)
    ctx_d, _ = _context(down, bench=make_index(down, drift=0.0002))
    res_d = MomentumLens().evaluate(ctx_d, LensConfig(lens_version="1"))
    assert res_d.view == "WEAK"


def test_rs_percentile_unavailable_is_flagged_not_failed() -> None:
    """T-MOM-19: pilot mode has no segment, so the criterion is skipped and the template is x/y."""
    up = make_prices(400, drift=0.0012, vol=0.006)
    ctx, _ = _context(up, bench=make_index(up))
    res = MomentumLens().evaluate(ctx, LensConfig(lens_version="1"))
    assert ctx.metrics[M + "rs_percentile"] is None
    assert res.details["trend_template"]["computable"] == 7


@pytest.mark.ac("AC-F05.6")
def test_a_fired_signal_records_date_price_and_confirmation() -> None:
    """T-MOM-20: a high-volume breakout fires M03 with its date, price and confirmation status."""
    p = make_prices(300, drift=0.0, vol=0.004)
    p.loc[p.index[-1], ["close", "adj_close", "high"]] = p["close"].max() * 1.05
    p.loc[p.index[-1], "volume"] = p["volume"].mean() * 4
    _, c = _context(p, cap="large")
    s = {x.id: x for x in evaluate_signals(c)}["M03"]
    assert s.status == "fired" and s.date == p["trade_date"].iloc[-1] and s.price is not None
    assert s.confirmed is False  # one close beyond the level is not yet two


def test_every_registered_signal_has_a_definition_and_runs_on_short_history() -> None:
    """T-MOM-21"""
    _, c = _context(make_prices(30))
    states = evaluate_signals(c)
    assert {s.id for s in states} == set(SIGNAL_DEFS)
    assert all(s.status in ("fired", "not_fired", "cannot_evaluate") for s in states)


def test_stock_split_does_not_create_an_artificial_drop() -> None:
    """T-MOM-22 (AC-F02.2 carried into the lens): adjusted prices give the same DMA either side of a split."""
    p = make_prices(300, drift=0.0004)
    split = p.copy()
    cut = 150
    split.loc[: cut - 1, ["open", "high", "low", "close"]] *= 2  # pre-split raw prices were 2x
    split.loc[: cut - 1, "volume"] /= 2
    # adj_close holds the adjusted series, as stored by the price job
    ctx_a, _ = _context(p)
    ctx_b, _ = _context(split)
    assert ctx_b.metrics[M + "dma200"] == pytest.approx(ctx_a.metrics[M + "dma200"], rel=1e-9)
