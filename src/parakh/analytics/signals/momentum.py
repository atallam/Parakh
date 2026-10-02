"""Momentum signal catalogue M01–M26 that price (and results dates) can drive (plan 02 §4).

Each signal is a condition `(Calc) -> True | False | None`; None means the history or data it
needs is missing, and the signal is reported "cannot evaluate" rather than quietly false
(AC-F05.8). `evaluate_signals` adds confirmation: a signal is *confirmed* when its hold
condition is true on the last `confirm_closes` sessions (plan 02 §4).

Not built here, because their data is not loaded until Phase 3 (the event watcher): M09
institutional accumulation (bulk/block deals, delivery %), M27 circuit trap, M28 surveillance,
M29 index inclusion and M30 lock-in expiry. M25 needs last month's RS percentile, which exists
only with the segment universe (Phase 4).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from parakh.analytics import indicators as ind
from parakh.analytics.metrics.momentum import (
    current_stage,
    dma50,
    dma200,
    template_score,
)
from parakh.analytics.momentum_calc import Calc
from parakh.registry import register_signal

Cond = Callable[[Calc], bool | None]


@dataclass(frozen=True)
class SignalDef:
    id: str
    name: str
    severity: str
    cond: Cond
    hold: Cond | None = None  # confirmation test; defaults to cond


SIGNAL_DEFS: dict[str, SignalDef] = {}


def signal(
    ident: str, name: str, severity: str, hold: Cond | None = None
) -> Callable[[Cond], Cond]:
    def deco(fn: Cond) -> Cond:
        register_signal(id=ident, name=name, lens="momentum", severity=severity)(fn)  # type: ignore[arg-type]
        SIGNAL_DEFS[ident] = SignalDef(ident, name, severity, fn, hold)
        return fn

    return deco


# -- helpers ---------------------------------------------------------------------------------
def _window(c: Calc) -> tuple[int, bool] | None:
    return c.sessions_for_window("high_52w")


def _avg_volume(c: Calc, n: int, offset: int = 0) -> float | None:
    v = c.inp.bars.volume
    end = len(v) - offset
    if end < n:
        return None
    return float(v[end - n : end].mean())


def _mansfield_of(rs: np.ndarray) -> float | None:
    fin = rs[np.isfinite(rs)]
    return ind.mansfield(fin, 252)


# -- leading signals -------------------------------------------------------------------------
@signal("M01", "RS line new high before price", "High")
def m01(c: Calc) -> bool | None:
    """RS line makes a 52-week high while price is still below its 52-week high.

    Formula:   RS_t = max(RS over the window) and P_t < max(P over the window)
    Meaning:   A classic early leadership signal.
    Pitfalls:  Needs a benchmark; below 252 sessions it uses the since-listing window and says so.
    Source:    prices, index series; plan 02 §4
    """
    w = _window(c)
    rs = c.rs()
    if w is None or rs is None:
        return None
    win = w[0]
    seg = rs[-win:]
    if not np.isfinite(seg).all():
        return None
    return bool(seg[-1] >= seg.max() and c.close[-1] < c.close[-win:].max())


@signal("M02", "Stage 1 to 2 transition", "High")
def m02(c: Calc) -> bool | None:
    """Price breaks out of a base of at least six weeks above a flattening or rising 150 DMA on volume.

    Formula:   P_t above the base high (30+ sessions, range under 25%) with volume ≥ cap multiple × 50-day average, Stage 2 now, Stage 1 a month ago
    Meaning:   The start of a Stage 2 advance.
    Pitfalls:  Needs 150 sessions plus the stage look-back.
    Source:    prices; plan 02 §4
    """
    sp = c.cfg.signals
    now = current_stage(c)
    before = current_stage(c.truncate(sp.stage_change_sessions))
    avg = _avg_volume(c, sp.breakout_volume_window, 1)
    if now is None or before is None or avg is None or c.n < sp.base_min_sessions + 6:
        return None
    base = c.close[-(sp.base_min_sessions + 5) : -5]
    lo, hi = base.min(), base.max()
    tight = (hi - lo) / lo <= sp.base_max_range
    mult = c.cfg.cap_settings[c.inp.cap].breakout_volume_x  # type: ignore[index]
    return bool(
        now == 2
        and before == 1
        and tight
        and c.close[-1] > hi
        and c.inp.bars.volume[-1] >= mult * avg
    )


@signal("M03", "52-week-high breakout on volume", "High")
def m03(c: Calc) -> bool | None:
    """Close at a new 52-week high with volume at or above the cap multiple of the 50-day average.

    Formula:   P_t > max(P, prior 252 sessions) and volume_t ≥ multiple × avg50 (1.5 / 1.75 / 2.0 by cap)
    Meaning:   Breakouts on heavy volume are the most reliable.
    Pitfalls:  Below 252 sessions it uses the since-listing high and the alert says so.
    Source:    prices; plan 02 §4
    """
    w = _window(c)
    avg = _avg_volume(c, c.cfg.signals.breakout_volume_window, 1)
    if w is None or avg is None or c.n < w[0] + 1:
        return None
    prior = c.close[-(w[0] + 1) : -1].max()
    mult = c.cfg.cap_settings[c.inp.cap].breakout_volume_x  # type: ignore[index]
    return bool(c.close[-1] > prior and c.inp.bars.volume[-1] >= mult * avg)


def _swings(close: np.ndarray, threshold: float) -> list[tuple[int, float, str]]:
    """Zig-zag turning points where the move from the last pivot exceeds `threshold`."""
    pivots: list[tuple[int, float, str]] = []
    direction = ""
    ext_i, ext_v = 0, float(close[0])
    for i in range(1, len(close)):
        v = float(close[i])
        if direction in ("", "up") and v > ext_v:
            ext_i, ext_v, direction = i, v, "up"
        elif direction in ("", "down") and v < ext_v:
            ext_i, ext_v, direction = i, v, "down"
        elif direction == "up" and v <= ext_v * (1 - threshold):
            pivots.append((ext_i, ext_v, "high"))
            ext_i, ext_v, direction = i, v, "down"
        elif direction == "down" and v >= ext_v * (1 + threshold):
            pivots.append((ext_i, ext_v, "low"))
            ext_i, ext_v, direction = i, v, "up"
    return pivots


@signal("M04", "Volatility contraction pattern", "Medium")
def m04(c: Calc) -> bool | None:
    """Three or more successive pullbacks, each shallower than the last, with volume drying up.

    Formula:   pullback depths from a zig-zag (3% threshold) over 80 sessions strictly shrink, and 10-day volume < 50-day volume
    Meaning:   A setup, not yet a trigger.
    Pitfalls:  Zig-zag threshold and look-back are starting points.
    Source:    prices; plan 02 §4
    """
    need = 80
    if c.n < need or (avg50 := _avg_volume(c, 50)) is None:
        return None
    seg = c.close[-need:]
    piv = _swings(seg, 0.03)
    depths = []
    for a, b in zip(piv, piv[1:], strict=False):
        if a[2] == "high" and b[2] == "low":
            depths.append(1 - b[1] / a[1])
    k = c.cfg.signals.vcp_min_pullbacks
    if len(depths) < k:
        return False
    last = depths[-k:]
    shrinking = all(x > y for x, y in zip(last, last[1:], strict=False))
    dry = (_avg_volume(c, 10) or 0) < avg50
    return bool(shrinking and dry)


@signal("M05", "Trend Template newly 8 of 8", "High")
def m05(c: Calc) -> bool | None:
    """The Trend Template score moves to 8 of 8 from 7 or lower a month ago.

    Formula:   score_t = 8 of 8 computable and score_t-21 < 8
    Meaning:   A stock newly meeting every criterion of a textbook uptrend.
    Pitfalls:  Needs all eight criteria computable; in pilot mode the RS percentile is missing,
               so this signal reports "cannot evaluate" until the segment universe exists.
    Source:    prices, constituents; plan 02 §3.6
    """
    x, y = template_score(c)
    if y < 8:
        return None
    px, py = template_score(c.truncate(c.cfg.signals.stage_change_sessions))
    return bool(x == 8 and not (px == 8 and py == 8))


@signal("M06", "200 DMA reclaim", "Medium")
def m06(c: Calc) -> bool | None:
    """Close back above the 200 DMA after at least 20 sessions below it.

    Formula:   last 2 closes above the 200 DMA and at least 20 of the 40 sessions before them below it
    Meaning:   A potential change of trend.
    Pitfalls:  Needs 200 sessions plus the look-back; never fires earlier (AC-F05.8).
    Source:    prices; plan 02 §4
    """
    sp = c.cfg.signals
    if c.n < c.need("dma200") + 42:
        return None
    ma = c.ma_series(200)
    above = c.close[-2:] > ma[-2:]
    prior_below = (c.close[-42:-2] < ma[-42:-2]).sum()
    return bool(above.all() and prior_below >= sp.below_ma_sessions)


@signal("M07", "Sector rotation in", "Medium")
def m07(c: Calc) -> bool | None:
    """The sector index's Mansfield RS against the benchmark crosses above zero.

    Formula:   Mansfield(sector ÷ benchmark) > 0 now and ≤ 0 a month ago
    Meaning:   The stock's sector is starting to lead.
    Pitfalls:  Needs both the sector and benchmark series and 252 sessions.
    Source:    index series; plan 02 §4
    """
    if c.inp.sector is None or c.inp.bench is None or c.n < 273:
        return None
    ratio = c.inp.sector / c.inp.bench
    now = _mansfield_of(ratio)
    before = _mansfield_of(ratio[: -c.cfg.signals.stage_change_sessions])
    if now is None or before is None:
        return None
    return bool(now > 0 and before <= 0)


@signal("M08", "Earnings gap and hold", "High")
def m08(c: Calc) -> bool | None:
    """A results-day gap of 4% or more on at least twice normal volume that holds above the gap-day low for five sessions.

    Formula:   open_r ÷ close_r-1 − 1 ≥ 4% and volume_r ≥ 2 × avg50, then close ≥ low_r on the next five sessions
    Meaning:   Stocks that gap up on results and hold tend to keep drifting.
    Pitfalls:  Uses the exchange broadcast date and tests that day and the next (after-hours
               filings); needs the results dates from fundamentals and 55 sessions.
    Source:    prices, fundamentals reported_on; plan 02 §3.8
    """
    sp = c.cfg.signals
    if not c.inp.results_dates or c.n < 56:
        return None
    dates = list(c.inp.bars.dates)
    recent = [d for d in c.inp.results_dates if d <= c.inp.asof]
    if not recent:
        return False
    last = max(recent)
    idx = next((i for i, d in enumerate(dates) if d >= last), None)
    if idx is None or idx < 51 or len(dates) - idx > 20:
        return False
    b = c.inp.bars
    for j in (idx, idx + 1):
        if j >= len(dates):
            continue
        gap = b.open[j] / b.close[j - 1] - 1
        avg = float(b.volume[j - 50 : j].mean())
        if gap >= sp.gap_threshold and b.volume[j] >= sp.gap_volume_x * avg:
            after = b.close[j : j + sp.gap_hold_sessions + 1]
            if len(after) < sp.gap_hold_sessions + 1:
                return False  # gap seen, hold not yet proven
            return bool((after >= b.low[j]).all())
    return False


# -- confirmation signals --------------------------------------------------------------------
def _cross(c: Calc, up: bool) -> bool | None:
    if c.n < c.need("dma200") + c.cfg.signals.cross_lookback + 1:
        return None
    m50, m200 = c.ma_series(50), c.ma_series(200)
    k = c.cfg.signals.cross_lookback
    now = m50[-1] > m200[-1]
    then = m50[-1 - k] > m200[-1 - k]
    return bool((now and not then) if up else (not now and then))


@signal("M10", "Golden Cross", "Medium")
def m10(c: Calc) -> bool | None:
    """The 50 DMA crosses above the 200 DMA within the last five sessions.

    Formula:   DMA50_t > DMA200_t and DMA50_t-5 ≤ DMA200_t-5
    Meaning:   A lagging confirmation of an uptrend.
    Pitfalls:  Needs 200 sessions; never fires earlier (AC-F05.8).
    Source:    prices; plan 02 §4
    """
    return _cross(c, True)


@signal("M11", "Death Cross", "High")
def m11(c: Calc) -> bool | None:
    """The 50 DMA crosses below the 200 DMA within the last five sessions.

    Formula:   DMA50_t < DMA200_t and DMA50_t-5 ≥ DMA200_t-5
    Meaning:   A lagging warning of a downtrend; high severity for holders.
    Pitfalls:  Needs 200 sessions; never fires earlier (AC-F05.8).
    Source:    prices; plan 02 §4
    """
    return _cross(c, False)


@signal("M12", "50 DMA pullback bounce", "Medium")
def m12(c: Calc) -> bool | None:
    """In Stage 2, price touches the 50 DMA (within 2%) and closes back up on volume.

    Formula:   Stage 2, min(low, last 3) ≤ DMA50 × 1.02, close > DMA50 and > prior close, volume ≥ avg20
    Meaning:   An add-on entry within an advance.
    Pitfalls:  Needs 150 sessions for the stage.
    Source:    prices; plan 02 §4
    """
    st = current_stage(c)
    m50 = dma50(c).value
    avg20 = _avg_volume(c, 20, 1)
    if st is None or m50 is None or avg20 is None:
        return None
    b = c.inp.bars
    touch = b.low[-3:].min() <= m50 * (1 + c.cfg.signals.pullback_touch)
    return bool(
        st == 2
        and touch
        and b.close[-1] > m50
        and b.close[-1] > b.close[-2]
        and b.volume[-1] >= c.cfg.signals.bounce_volume_x * avg20
    )


# -- warning and exit signals ----------------------------------------------------------------
@signal("M20", "50 DMA breakdown", "Medium")
def m20(c: Calc) -> bool | None:
    """Two closes below the 50 DMA on above-average volume.

    Formula:   close < DMA50 on the last 2 sessions and their mean volume > 50-day average
    Meaning:   Tactical exit or tighter stop.
    Pitfalls:  Needs 50 sessions.
    Source:    prices; plan 02 §4
    """
    if c.n < 52:
        return None
    ma = c.ma_series(50)
    avg = _avg_volume(c, 50, 2)
    if avg is None or not np.isfinite(ma[-2:]).all():
        return None
    return bool((c.close[-2:] < ma[-2:]).all() and c.inp.bars.volume[-2:].mean() > avg)


@signal("M21", "200 DMA breakdown", "High")
def m21(c: Calc) -> bool | None:
    """Two closes below the 200 DMA.

    Formula:   close < DMA200 on the last 2 sessions
    Meaning:   A strategic exit signal.
    Pitfalls:  Needs 200 sessions; never fires earlier (AC-F05.8).
    Source:    prices; plan 02 §4
    """
    if c.n < c.need("dma200") + 1:
        return None
    ma = c.ma_series(200)
    return bool((c.close[-2:] < ma[-2:]).all())


@signal("M22", "Stage 2 to 3 (topping)", "High")
def m22(c: Calc) -> bool | None:
    """The 150 DMA flattens after an advance, with distribution days increasing.

    Formula:   Stage 3 now, Stage 2 a month ago, and at least 4 distribution days (down ≥ 0.2% on higher volume) in 25 sessions
    Meaning:   The advance is topping out.
    Pitfalls:  Needs 150 sessions plus the look-back.
    Source:    prices; plan 02 §4
    """
    sp = c.cfg.signals
    now = current_stage(c)
    before = current_stage(c.truncate(sp.stage_change_sessions))
    if now is None or before is None or c.n < sp.distribution_window + 1:
        return None
    b = c.inp.bars
    w = sp.distribution_window
    chg = np.diff(b.close[-(w + 1) :]) / b.close[-(w + 1) : -1]
    vol_up = np.diff(b.volume[-(w + 1) :]) > 0
    days = int(((chg <= -sp.distribution_drop) & vol_up).sum())
    return bool(now == 3 and before == 2 and days >= sp.distribution_days_min)


@signal("M23", "Bearish RSI divergence", "Medium")
def m23(c: Calc) -> bool | None:
    """Price makes a higher high while RSI makes a lower high, near a 52-week high.

    Formula:   max(P, last 10) > max(P, prior 30) while max(RSI, last 10) < max(RSI, prior 30), price within 5% of its high
    Meaning:   Momentum is fading beneath a rising price.
    Pitfalls:  RSI above 70 alone is not a sell signal in a strong uptrend.
    Source:    prices; plan 02 §3.7, §4
    """
    sp = c.cfg.signals
    need = sp.divergence_lookback + 12 + c.cfg.rsi_window
    hl = _window(c)
    if c.n < need or hl is None:
        return None
    r = ind.rsi(c.close, c.cfg.rsi_window)
    p_new, p_old = c.close[-10:].max(), c.close[-(sp.divergence_lookback + 10) : -10].max()
    r_new, r_old = np.nanmax(r[-10:]), np.nanmax(r[-(sp.divergence_lookback + 10) : -10])
    near = c.close[-1] >= c.close[-hl[0] :].max() * (1 - sp.divergence_near_high)
    return bool(near and p_new > p_old and r_new < r_old)


@signal("M24", "Over-extension", "Low")
def m24(c: Calc) -> bool | None:
    """Price more than the cap's threshold above its 200 DMA.

    Formula:   P_t ÷ DMA200_t − 1 > 30% / 40% / 50% (large / mid / small)
    Meaning:   Don't chase; consider trimming.
    Pitfalls:  Needs 200 sessions; never fires earlier (AC-F05.8).
    Source:    prices; plan 02 §4, §6
    """
    m = dma200(c).value
    if m is None:
        return None
    return bool(c.close[-1] / m - 1 > c.cfg.cap_settings[c.inp.cap].over_extension)  # type: ignore[index]


@signal("M26", "Climax run", "Medium")
def m26(c: Calc) -> bool | None:
    """A gain of 25% or more in about three weeks, with the advance's largest volume today.

    Formula:   P_t ÷ min(P, last 15) − 1 ≥ 25% and volume_t = max(volume, last 15)
    Meaning:   Often marks a top.
    Pitfalls:  Rare by design; thresholds are starting points.
    Source:    prices; plan 02 §4
    """
    sp = c.cfg.signals
    if c.n < sp.climax_sessions + 1:
        return None
    seg_c = c.close[-sp.climax_sessions :]
    seg_v = c.inp.bars.volume[-sp.climax_sessions :]
    return bool(seg_c[-1] / seg_c.min() - 1 >= sp.climax_gain and seg_v[-1] >= seg_v.max())


# -- evaluation ------------------------------------------------------------------------------
@dataclass(frozen=True)
class SignalState:
    id: str
    name: str
    severity: str
    status: str  # fired | not_fired | cannot_evaluate
    confirmed: bool = False
    date: dt.date | None = None
    price: float | None = None
    note: str = ""


def evaluate_signals(c: Calc) -> list[SignalState]:
    k = c.cfg.signals.confirm_closes
    out: list[SignalState] = []
    asof_date = c.inp.bars.dates[-1] if len(c.inp.bars) else None
    price = float(c.close[-1]) if len(c.inp.bars) else None
    for ident in sorted(SIGNAL_DEFS):
        d = SIGNAL_DEFS[ident]
        res = d.cond(c)
        if res is None:
            out.append(
                SignalState(
                    ident, d.name, d.severity, "cannot_evaluate", note="not enough history or data"
                )
            )
            continue
        if not res:
            out.append(SignalState(ident, d.name, d.severity, "not_fired"))
            continue
        hold = d.hold or d.cond
        confirmed = all(hold(c.truncate(j)) is True for j in range(k))
        note = (
            "since-listing window" if ident in ("M01", "M03") and c.n < c.need("high_52w") else ""
        )
        out.append(
            SignalState(ident, d.name, d.severity, "fired", confirmed, asof_date, price, note)
        )
    return out
