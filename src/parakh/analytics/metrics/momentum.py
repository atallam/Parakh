"""Momentum metrics (plan 02 §3). Each takes a `Calc` and returns a `Measure` (value or reason).

Registered under `MET.momentum.*`; the momentum lens declares them as required metrics and the
catalogue (docs/METRICS.md) is generated from the docstrings.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from parakh.analytics import indicators as ind
from parakh.analytics.momentum_calc import Calc, Measure
from parakh.registry import register_metric

MomentumFn = Callable[[Calc], Measure]
MOMENTUM_METRICS: dict[str, MomentumFn] = {}
LENS = ["LENS.momentum"]


def momentum_metric(ident: str, unit: str, inputs: list[str]) -> Callable[[MomentumFn], MomentumFn]:
    def deco(fn: MomentumFn) -> MomentumFn:
        register_metric(id=ident, unit=unit, inputs=inputs, used_by=LENS)(fn)  # type: ignore[arg-type]
        MOMENTUM_METRICS[ident] = fn
        return fn

    return deco


def _ret_pair(c: Calc, sessions: int, key: str) -> tuple[float, float] | Measure:
    if (why := c.short_reason(key, sessions + 1)) is not None:
        return Measure.na(why)
    b = c.inp.bench
    if b is None:
        return Measure.na(c.inp.bench_reason)
    s, bm = ind.ret(c.close, sessions), ind.ret(b[np.isfinite(b)], sessions)
    if s is None or bm is None:
        return Measure.na("benchmark history is shorter than the stock's")
    return s, bm


def _excess(c: Calc, sessions: int, key: str) -> Measure:
    r = _ret_pair(c, sessions, key)
    return r if isinstance(r, Measure) else Measure(r[0] - r[1])


@momentum_metric("MET.momentum.excess_return_1m", "ratio", ["prices.adj_close", "index.close"])
def excess_return_1m(c: Calc) -> Measure:
    """Stock return minus benchmark return over 1 month (21 sessions).

    Formula:   (P_t / P_t-21 − 1) − (B_t / B_t-21 − 1)
    Meaning:   Short-horizon outperformance against the cap-matched benchmark.
    Pitfalls:  Noisy; the 12-1 measure skips this month on purpose.
    Source:    prices (adjusted close), index series; plan 02 §3.1
    """
    return _excess(c, 21, "excess_return_1m")


@momentum_metric("MET.momentum.excess_return_3m", "ratio", ["prices.adj_close", "index.close"])
def excess_return_3m(c: Calc) -> Measure:
    """Stock return minus benchmark return over 3 months (63 sessions).

    Formula:   (P_t / P_t-63 − 1) − (B_t / B_t-63 − 1)
    Meaning:   Medium-horizon outperformance against the benchmark.
    Pitfalls:  Needs 64 closes after the listing exclusion; N/A before that.
    Source:    prices (adjusted close), index series; plan 02 §3.1
    """
    return _excess(c, 63, "excess_return_3m")


@momentum_metric("MET.momentum.excess_return_6m", "ratio", ["prices.adj_close", "index.close"])
def excess_return_6m(c: Calc) -> Measure:
    """Stock return minus benchmark return over 6 months (126 sessions).

    Formula:   (P_t / P_t-126 − 1) − (B_t / B_t-126 − 1)
    Meaning:   The shortest horizon that still carries momentum information.
    Pitfalls:  Needs 127 closes after the listing exclusion; N/A before that.
    Source:    prices (adjusted close), index series; plan 02 §3.1
    """
    return _excess(c, 126, "excess_return_6m")


@momentum_metric("MET.momentum.excess_return_12m", "ratio", ["prices.adj_close", "index.close"])
def excess_return_12m(c: Calc) -> Measure:
    """Stock return minus benchmark return over 12 months (252 sessions).

    Formula:   (P_t / P_t-252 − 1) − (B_t / B_t-252 − 1)
    Meaning:   Long-horizon outperformance; includes the latest month.
    Pitfalls:  Needs 253 closes after the listing exclusion; young listings show N/A.
    Source:    prices (adjusted close), index series; plan 02 §3.1
    """
    return _excess(c, 252, "excess_return_12m")


@momentum_metric("MET.momentum.mom_12_1", "ratio", ["prices.adj_close"])
def mom_12_1(c: Calc) -> Measure:
    """12-1 momentum: return from 12 months ago to 1 month ago, skipping the latest month.

    Formula:   P_t-21 / P_t-252 − 1
    Meaning:   The standard academic momentum measure; skipping the last month avoids reversal.
    Pitfalls:  Needs 253 closes after the listing exclusion; young listings are ranked on 6M
               volatility-adjusted momentum instead (plan 02 §3.9).
    Source:    prices (adjusted close); plan 02 §3.1
    """
    if (why := c.short_reason("mom_12_1", c.need("mom_12_1") + 1)) is not None:
        return Measure.na(why)
    v = ind.ret_12_1(c.close)
    return Measure(v) if v is not None else Measure.na("price history too short")


@momentum_metric("MET.momentum.absolute_return_12m", "ratio", ["prices.adj_close"])
def absolute_return_12m(c: Calc) -> Measure:
    """The stock's own 12-month return, for the dual-momentum filter.

    Formula:   P_t / P_t-252 − 1
    Meaning:   A BUY must also beat a liquid-fund return, not only the benchmark (plan 02 §11 #1).
    Pitfalls:  Needs 253 closes; N/A for young listings, in which case the filter is skipped.
    Source:    prices (adjusted close); plan 02 §11
    """
    if (why := c.short_reason("excess_return_12m", 253)) is not None:
        return Measure.na(why)
    v = ind.ret(c.close, 252)
    return Measure(v) if v is not None else Measure.na("price history too short")


@momentum_metric("MET.momentum.mansfield_rs", "score", ["prices.adj_close", "index.close"])
def mansfield_rs(c: Calc) -> Measure:
    """Mansfield relative strength: RS line against its own 52-week average.

    Formula:   (RS_t ÷ SMA252(RS) − 1) × 100, with RS = price ÷ benchmark
    Meaning:   Above zero means the stock outperforms its own RS average.
    Pitfalls:  Needs 252 sessions of RS; N/A without a benchmark series.
    Source:    prices, index series; plan 02 §3.1
    """
    if (why := c.short_reason("mansfield_rs")) is not None:
        return Measure.na(why)
    rs = c.rs()
    if rs is None:
        return Measure.na(c.inp.bench_reason)
    v = ind.mansfield(rs[np.isfinite(rs)], 252)
    return (
        Measure(v)
        if v is not None
        else Measure.na("benchmark history is shorter than 252 sessions")
    )


@momentum_metric("MET.momentum.rs_slope_50d", "ratio", ["prices.adj_close", "index.close"])
def rs_slope_50d(c: Calc) -> Measure:
    """Change in the RS line over the last 50 sessions.

    Formula:   RS_t ÷ RS_t-50 − 1
    Meaning:   A rising RS line means the stock is outperforming now, not only over the year.
    Pitfalls:  Needs a benchmark series and 51 sessions.
    Source:    prices, index series; plan 02 §3.1
    """
    if (why := c.short_reason("rs_slope_50d")) is not None:
        return Measure.na(why)
    rs = c.rs()
    if rs is None:
        return Measure.na(c.inp.bench_reason)
    v = ind.slope(rs, 50)
    return Measure(v) if v is not None else Measure.na("benchmark history too short")


@momentum_metric(
    "MET.momentum.rs_percentile", "score", ["prices.adj_close", "segment.constituents"]
)
def rs_percentile(c: Calc) -> Measure:
    """Rank of the stock's momentum among its segment's constituents, 0–100.

    Formula:   100 × share of peers with 12-1 momentum at or below the stock's
    Meaning:   "Top 20% of midcaps" says more than "+30%".
    Pitfalls:  Needs the segment's constituent prices (loaded from the Phase 4 scale-up);
               N/A in pilot mode, and the Trend Template then reports x/y.
    Source:    prices of index constituents; plan 02 §3.1
    """
    m = mom_12_1(c)
    if m.value is None:
        return Measure.na(m.reason or "momentum unavailable")
    if len(c.inp.segment_mom) < 2:
        return Measure.na("segment prices not loaded (pilot universe)")
    p = ind.percentile_rank(m.value, c.inp.segment_mom)
    return Measure(p) if p is not None else Measure.na("too few peers")


@momentum_metric("MET.momentum.volatility_1y", "ratio", ["prices.adj_close"])
def volatility_1y(c: Calc) -> Measure:
    """Annualised volatility of daily log returns over the last year.

    Formula:   stdev(ln(P_t / P_t-1), 252 sessions) × √252
    Meaning:   Scales raw momentum so smooth trends rank above erratic ones.
    Pitfalls:  Under 252 sessions it uses the window since the listing exclusion if that is at
               least 126 sessions (flagged "short window"); otherwise N/A.
    Source:    prices (adjusted close); plan 02 §3.2, §3.9
    """
    window = c.cfg.volatility_window
    if c.n >= window + 1:
        v = ind.ann_vol(c.close, window)
    elif c.n - 1 >= c.cfg.history.since_listing_min_sessions:
        v = ind.ann_vol(c.close, c.n - 1)
        c.flags.append("volatility uses a short window since listing")
    else:
        return Measure.na(c.short_reason("volatility") or "price history too short")
    return Measure(v) if v is not None else Measure.na("price history too short")


def _vol_adj(c: Calc, sessions: int, key: str) -> Measure:
    if (why := c.short_reason(key, sessions + 1)) is not None:
        return Measure.na(why)
    r = ind.ret(c.close, sessions)
    vol = volatility_1y(c)
    if r is None or vol.value is None or vol.value == 0:
        return Measure.na(vol.reason or "volatility unavailable")
    return Measure(r / vol.value)


@momentum_metric("MET.momentum.vol_adj_6m", "ratio", ["prices.adj_close"])
def vol_adj_6m(c: Calc) -> Measure:
    """6-month return divided by annualised volatility.

    Formula:   (P_t / P_t-126 − 1) ÷ volatility_1y
    Meaning:   Rewards smooth advances; closer to how NSE's momentum indices rank.
    Pitfalls:  Scored on absolute bands until the segment universe is loaded; the z-score across
               the segment replaces it at the Phase 4 scale-up.
    Source:    prices (adjusted close); plan 02 §3.2
    """
    return _vol_adj(c, 126, "excess_return_6m")


@momentum_metric("MET.momentum.vol_adj_12m", "ratio", ["prices.adj_close"])
def vol_adj_12m(c: Calc) -> Measure:
    """12-month return divided by annualised volatility.

    Formula:   (P_t / P_t-252 − 1) ÷ volatility_1y
    Meaning:   The long-horizon twin of vol_adj_6m.
    Pitfalls:  Needs 253 closes after the listing exclusion; N/A for young listings.
    Source:    prices (adjusted close); plan 02 §3.2
    """
    return _vol_adj(c, 252, "excess_return_12m")


@momentum_metric("MET.momentum.dma50", "inr", ["prices.adj_close"])
def dma50(c: Calc) -> Measure:
    """50-day simple moving average of the adjusted close.

    Formula:   mean(P, last 50 sessions)
    Meaning:   Tactical trend line; also anchors the entry-timing overlay.
    Pitfalls:  Needs 50 sessions.
    Source:    prices (adjusted close); plan 02 §3.3
    """
    v = c.ma(50, "dma50")
    return Measure(v) if v is not None else Measure.na(c.short_reason("dma50") or "n/a")


@momentum_metric("MET.momentum.dma150", "inr", ["prices.adj_close"])
def dma150(c: Calc) -> Measure:
    """150-day simple moving average (about 30 weeks), the Weinstein stage line.

    Formula:   mean(P, last 150 sessions)
    Meaning:   Defines the stage and Trend Template items 1, 2 and 4.
    Pitfalls:  Needs 150 sessions.
    Source:    prices (adjusted close); plan 02 §3.3
    """
    v = c.ma(150, "dma150")
    return Measure(v) if v is not None else Measure.na(c.short_reason("dma150") or "n/a")


@momentum_metric("MET.momentum.dma200", "inr", ["prices.adj_close"])
def dma200(c: Calc) -> Measure:
    """200-day simple moving average of the adjusted close.

    Formula:   mean(P, last 200 sessions)
    Meaning:   The strategic trend line; M06, M10, M11, M21 and M24 depend on it.
    Pitfalls:  Needs 200 sessions; none of those signals fire before that (AC-F05.8).
    Source:    prices (adjusted close); plan 02 §3.3
    """
    v = c.ma(200, "dma200")
    return Measure(v) if v is not None else Measure.na(c.short_reason("dma200") or "n/a")


@momentum_metric("MET.momentum.dma200_slope", "ratio", ["prices.adj_close"])
def dma200_slope(c: Calc) -> Measure:
    """Change in the 200 DMA over the last 20 sessions.

    Formula:   DMA200_t ÷ DMA200_t-20 − 1
    Meaning:   A flat or falling 200 DMA weakens every other bullish reading.
    Pitfalls:  Needs 220 sessions.
    Source:    prices (adjusted close); plan 02 §3.3
    """
    if (why := c.short_reason("dma200_slope")) is not None:
        return Measure.na(why)
    v = ind.slope(c.ma_series(200), 20)
    return Measure(v) if v is not None else Measure.na("200 DMA history too short")


@momentum_metric("MET.momentum.pct_above_200", "ratio", ["prices.adj_close"])
def pct_above_200(c: Calc) -> Measure:
    """Distance of the price above its 200 DMA.

    Formula:   P_t ÷ DMA200_t − 1
    Meaning:   5–30% above is healthy; beyond the cap threshold it is over-extended (M24).
    Pitfalls:  Needs 200 sessions.
    Source:    prices (adjusted close); plan 02 §3.3
    """
    m = dma200(c)
    if m.value is None:
        return Measure.na(m.reason or "n/a")
    return Measure(float(c.close[-1] / m.value - 1))


@momentum_metric("MET.momentum.extension_points", "score", ["prices.adj_close"])
def extension_points(c: Calc) -> Measure:
    """0–1 credit for where the price sits relative to its 200 DMA, given the cap's threshold.

    Formula:   0 at or below the 200 DMA, ramping to 1 at 5% above, 1 up to the cap
               threshold, then falling linearly to 0 at twice the threshold
    Meaning:   Rewards a healthy position and penalises both weakness and over-extension.
    Pitfalls:  The 5% ramp start is a fixed starting point; cap thresholds come from config.
    Source:    prices; plan 02 §3.3, §6
    """
    p = pct_above_200(c)
    if p.value is None:
        return Measure.na(p.reason or "n/a")
    over = c.cfg.cap_settings[c.inp.cap].over_extension  # type: ignore[index]
    x = p.value
    ramp = 0.05
    if x <= 0:
        return Measure(0.0)
    if x < ramp:
        return Measure(x / ramp)
    if x <= over:
        return Measure(1.0)
    return Measure(max(0.0, 1 - (x - over) / over))


def _hi_lo(c: Calc) -> tuple[float, float, bool] | None:
    w = c.sessions_for_window("high_52w")
    if w is None:
        return None
    window, since = w
    seg = c.close[-window:]
    return float(seg.max()), float(seg.min()), since


@momentum_metric("MET.momentum.pct_from_52w_high", "ratio", ["prices.adj_close"])
def pct_from_52w_high(c: Calc) -> Measure:
    """Distance below the 52-week high close (negative or zero).

    Formula:   P_t ÷ max(P, last 252 sessions) − 1
    Meaning:   Stocks within 10–15% of their high show stronger continuation.
    Pitfalls:  With 126–251 sessions it uses the since-listing high and says so (AC-F05.8).
    Source:    prices (adjusted close); plan 02 §3.4, §3.9
    """
    hl = _hi_lo(c)
    if hl is None:
        return Measure.na(c.short_reason("high_52w") or "n/a")
    if hl[2]:
        c.flags.append("52-week high is since listing")
    return Measure(float(c.close[-1] / hl[0] - 1))


@momentum_metric("MET.momentum.pct_above_52w_low", "ratio", ["prices.adj_close"])
def pct_above_52w_low(c: Calc) -> Measure:
    """Distance above the 52-week low close.

    Formula:   P_t ÷ min(P, last 252 sessions) − 1
    Meaning:   Minervini Trend Template item 6 wants at least 30%.
    Pitfalls:  With 126–251 sessions it uses the since-listing low and says so.
    Source:    prices (adjusted close); plan 02 §3.6, §3.9
    """
    hl = _hi_lo(c)
    if hl is None:
        return Measure.na(c.short_reason("high_52w") or "n/a")
    return Measure(float(c.close[-1] / hl[1] - 1))


def template_items(c: Calc) -> list[tuple[str, bool | None]]:
    """The eight Minervini criteria as (label, passed or None when not computable)."""
    cfg = c.cfg.trend_template
    p = float(c.close[-1])
    m50, m150, m200 = dma50(c).value, dma150(c).value, dma200(c).value
    items: list[tuple[str, bool | None]] = []
    items.append(
        (
            "price above 150 and 200 DMA",
            None if m150 is None or m200 is None else p > m150 and p > m200,
        )
    )
    items.append(("150 DMA above 200 DMA", None if m150 is None or m200 is None else m150 > m200))
    rising: bool | None = None
    if c.n >= c.need("dma200_slope") + 1 and c.cfg.trend_template.ma200_rising_sessions:
        s = c.ma_series(200)
        k = cfg.ma200_rising_sessions
        rising = bool(s[-1] > s[-1 - k]) if np.isfinite(s[-1 - k]) else None
    items.append(("200 DMA rising for a month", rising))
    items.append(
        (
            "50 DMA above 150 and 200 DMA",
            None if None in (m50, m150, m200) else bool(m50 > m150 and m50 > m200),  # type: ignore[operator]
        )
    )
    items.append(("price above 50 DMA", None if m50 is None else p > m50))
    lo = pct_above_52w_low(c).value
    items.append(
        (
            f"price {cfg.above_52w_low:.0%}+ above 52-week low",
            None if lo is None else lo >= cfg.above_52w_low,
        )
    )
    hi = pct_from_52w_high(c).value
    items.append(
        (
            f"price within {cfg.within_52w_high:.0%} of 52-week high",
            None if hi is None else hi >= -cfg.within_52w_high,
        )
    )
    rp = rs_percentile(c).value
    if rp is None:
        items.append((f"RS percentile at least {int(cfg.rs_percentile_min)}", None))
    else:
        items.append(
            (f"RS percentile at least {int(cfg.rs_percentile_min)}", rp >= cfg.rs_percentile_min)
        )
    return items


def template_score(c: Calc) -> tuple[int, int]:
    """(criteria passed, criteria computable)."""
    items = template_items(c)
    known = [ok for _, ok in items if ok is not None]
    return sum(1 for ok in known if ok), len(known)


@momentum_metric(
    "MET.momentum.trend_template_score", "count", ["prices.adj_close", "segment.constituents"]
)
def trend_template_score(c: Calc) -> Measure:
    """Minervini Trend Template criteria passed (reported as x of y computable).

    Formula:   count of the eight criteria that hold, among those that can be computed
    Meaning:   8 of 8 is a textbook Stage 2 uptrend.
    Pitfalls:  Criteria without enough history, or without a segment, are excluded from y
               rather than failed (plan 02 §3.9); at least 3 must be computable.
    Source:    prices, constituents; plan 02 §3.6
    """
    x, y = template_score(c)
    if y < 3:
        return Measure.na(f"only {y} of 8 Trend Template criteria computable")
    return Measure(float(x))


@momentum_metric(
    "MET.momentum.trend_template_fraction", "ratio", ["prices.adj_close", "segment.constituents"]
)
def trend_template_fraction(c: Calc) -> Measure:
    """Share of computable Trend Template criteria that hold.

    Formula:   passed ÷ computable
    Meaning:   Lets the trend sub-score compare stocks with different history lengths fairly.
    Pitfalls:  At least 3 criteria must be computable.
    Source:    prices, constituents; plan 02 §3.6
    """
    x, y = template_score(c)
    if y < 3:
        return Measure.na(f"only {y} of 8 Trend Template criteria computable")
    return Measure(x / y)


def current_stage(c: Calc) -> int | None:
    if c.short_reason("dma150") is not None:
        return None
    st = c.cfg.stage
    return ind.stage(
        c.close, c.ma_series(150), st.slope_sessions, st.flat_tolerance, st.prior_trend_sessions
    )


@momentum_metric("MET.momentum.stage", "count", ["prices.adj_close"])
def stage_metric(c: Calc) -> Measure:
    """Weinstein stage from the 150 DMA: 1 basing, 2 advancing, 3 topping, 4 declining.

    Formula:   150 DMA change over a month: rising → 2, falling → 4, flat → 3 after an advance
               or 1 after a decline
    Meaning:   Stage 2 is the only stage to buy in.
    Pitfalls:  Needs 150 sessions plus a month of slope; a rising average with price below it
               is still Stage 2 (a pullback).
    Source:    prices (adjusted close); plan 02 §3.3
    """
    s = current_stage(c)
    if s is None:
        return Measure.na(
            c.short_reason("dma150", c.need("dma150") + c.cfg.stage.slope_sessions) or "n/a"
        )
    return Measure(float(s))


@momentum_metric("MET.momentum.stage_points", "score", ["prices.adj_close"])
def stage_points(c: Calc) -> Measure:
    """0–1 credit for the Weinstein stage, from config.

    Formula:   points[stage] with 1 → 0.25, 2 → 1, 3 → 0.4, 4 → 0
    Meaning:   Feeds the trend sub-score.
    Pitfalls:  The mapping is a starting point to be calibrated.
    Source:    prices; plan 02 §3.3
    """
    s = stage_metric(c)
    if s.value is None:
        return Measure.na(s.reason or "n/a")
    return Measure(c.cfg.stage.points[int(s.value)])


@momentum_metric("MET.momentum.up_down_volume_ratio", "x", ["prices.volume"])
def up_down_volume_ratio(c: Calc) -> Measure:
    """Volume on up-days divided by volume on down-days over 50 sessions.

    Formula:   Σ volume (close up) ÷ Σ volume (close down), last 50 sessions
    Meaning:   Above 1 suggests accumulation; below 1 distribution.
    Pitfalls:  Capped at 5 so one one-sided window cannot dominate.
    Source:    prices (volume); plan 02 §3.5
    """
    if (why := c.short_reason("volume_50d", 51)) is not None:
        return Measure.na(why)
    v = ind.up_down_volume_ratio(c.close, c.inp.bars.volume, 50)
    return Measure(min(v, 5.0)) if v is not None else Measure.na("no down-days in the window")


@momentum_metric("MET.momentum.obv_slope", "ratio", ["prices.adj_close", "prices.volume"])
def obv_slope(c: Calc) -> Measure:
    """On-balance volume change over 50 sessions, scaled by the window's total volume.

    Formula:   (OBV_t − OBV_t-50) ÷ Σ volume (last 50)
    Meaning:   Positive confirms the price trend with volume.
    Pitfalls:  Bounded in [−1, 1]; delivery % (the India-specific edge) is a later source.
    Source:    prices (volume); plan 02 §3.5
    """
    if (why := c.short_reason("volume_50d", 51)) is not None:
        return Measure.na(why)
    o = ind.obv(c.close, c.inp.bars.volume)
    total = float(c.inp.bars.volume[-50:].sum())
    if total == 0:
        return Measure.na("no traded volume in the window")
    return Measure(float((o[-1] - o[-51]) / total))


@momentum_metric("MET.momentum.earnings_accel", "score", ["fundamentals.quarterly"])
def earnings_accel(c: Calc) -> Measure:
    """Acceleration of year-on-year earnings growth, in percentage points.

    Formula:   latest quarter's YoY net-profit growth − mean of the previous three quarters'
    Meaning:   Price momentum backed by accelerating earnings persists better.
    Pitfalls:  Needs seven quarters of results; undefined on a loss base. Computed from
               point-in-time fundamentals by the input builder, not from prices.
    Source:    fundamentals (quarterly P&L); plan 02 §3.8
    """
    return c.inp.earnings_accel


@momentum_metric("MET.momentum.atr_14", "inr", ["prices.high", "prices.low", "prices.adj_close"])
def atr_14(c: Calc) -> Measure:
    """Wilder's 14-day average true range.

    Formula:   Wilder smoothing of max(H−L, |H−C_prev|, |L−C_prev|)
    Meaning:   Sizes the trailing stop (cap multiple × ATR).
    Pitfalls:  Uses adjusted highs and lows; needs 15 sessions.
    Source:    prices; plan 02 §6
    """
    b = c.inp.bars
    v = ind.atr(b.high, b.low, b.close, c.cfg.atr_window)
    return (
        Measure(v) if v is not None else Measure.na(f"{c.n} sessions; needs {c.cfg.atr_window + 1}")
    )


@momentum_metric("MET.momentum.sessions", "count", ["prices.adj_close"])
def sessions(c: Calc) -> Measure:
    """Trading sessions of price history after the listing exclusion.

    Formula:   count of sessions in the series used for scoring
    Meaning:   Drives the limited-history rules (informational below 126, Med cap below 252).
    Pitfalls:  The first 20 sessions after listing are excluded and not counted.
    Source:    prices; plan 02 §3.9
    """
    return Measure(float(c.n))


@momentum_metric("MET.momentum.avg_traded_value_cr", "cr", ["prices.close", "prices.volume"])
def avg_traded_value_cr(c: Calc) -> Measure:
    """Average daily traded value over the last 50 sessions, in ₹ crore.

    Formula:   mean(close × volume, 50 sessions) ÷ 10^7
    Meaning:   The liquidity filter: you must be able to exit at the stop, not 5% below it.
    Pitfalls:  Uses the adjusted close, so value is approximate for stocks with recent splits.
    Source:    prices; plan 02 §3.8, §6
    """
    if c.n < 50:
        return Measure.na(f"{c.n} sessions; needs 50")
    b = c.inp.bars
    return Measure(float((b.close[-50:] * b.volume[-50:]).mean() / 1e7))


@momentum_metric("MET.momentum.peak_close_52w", "inr", ["prices.adj_close"])
def peak_close_52w(c: Calc) -> Measure:
    """Highest adjusted close in the window used for the 52-week high.

    Formula:   max(P, last 252 sessions), or since listing with 126–251 sessions
    Meaning:   The reference for the trailing stop (cap percentage or ATR multiple).
    Pitfalls:  For a holding, the stop should trail from the peak since purchase, which the
               holdings view (F10) applies; this is the stock-level default.
    Source:    prices; plan 02 §6, §7
    """
    hl = _hi_lo(c)
    return Measure(hl[0]) if hl is not None else Measure.na(c.short_reason("high_52w") or "n/a")


def compute_all(c: Calc) -> tuple[dict[str, float | None], dict[str, str]]:
    """Every momentum metric for this stock: (values, N/A reasons)."""
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for ident, fn in MOMENTUM_METRICS.items():
        m = fn(c)
        values[ident] = m.value
        if m.value is None:
            reasons[ident] = m.reason or "not available"
    return values, reasons
