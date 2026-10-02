"""Pure price-indicator functions (plan 02 §3). No I/O, no config; every function takes arrays.

Conventions: arrays are chronological and end at the as-of session. A function that does not
have enough history returns None (the caller records why); it never pads or guesses.
"""

from __future__ import annotations

import math

import numpy as np

Array = np.ndarray


def sma(x: Array, n: int) -> float | None:
    return float(x[-n:].mean()) if len(x) >= n else None


def sma_series(x: Array, n: int) -> Array:
    """Rolling mean; the first n-1 entries are NaN."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        csum = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1 :] = (csum[n:] - csum[:-n]) / n
    return out


def ret(x: Array, n: int) -> float | None:
    """Return over the last n sessions; needs n+1 closes."""
    if len(x) < n + 1 or x[-1 - n] <= 0:
        return None
    return float(x[-1] / x[-1 - n] - 1)


def ret_12_1(x: Array, year: int = 252, skip: int = 21) -> float | None:
    """12-1 momentum: return from t-year to t-skip, ignoring the latest month."""
    if len(x) < year + 1 or x[-1 - year] <= 0:
        return None
    return float(x[-1 - skip] / x[-1 - year] - 1)


def ann_vol(x: Array, window: int, trading_days: int = 252) -> float | None:
    """Annualised standard deviation of daily log returns over the last `window` returns."""
    if len(x) < window + 1:
        return None
    r = np.diff(np.log(x[-(window + 1) :]))
    return float(r.std(ddof=1) * math.sqrt(trading_days))


def slope(x: Array, n: int) -> float | None:
    """Fractional change of the last value over n sessions (used for MA and RS slopes)."""
    if len(x) < n + 1 or not np.isfinite(x[-1 - n]) or x[-1 - n] == 0:
        return None
    if not np.isfinite(x[-1]):
        return None
    return float(x[-1] / x[-1 - n] - 1)


def rsi(x: Array, n: int = 14) -> Array:
    """Wilder's RSI series (NaN until n+1 closes)."""
    out = np.full(len(x), np.nan)
    if len(x) < n + 1:
        return out
    d = np.diff(x)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag, al = gain[:n].mean(), loss[:n].mean()
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + gain[i]) / n
        al = (al * (n - 1) + loss[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def atr(high: Array, low: Array, close: Array, n: int = 14) -> float | None:
    """Wilder's average true range at the last session."""
    if len(close) < n + 1:
        return None
    prev = close[:-1]
    tr = np.maximum.reduce([high[1:] - low[1:], np.abs(high[1:] - prev), np.abs(low[1:] - prev)])
    a = tr[:n].mean()
    for v in tr[n:]:
        a = (a * (n - 1) + v) / n
    return float(a)


def obv(close: Array, volume: Array) -> Array:
    sign = np.sign(np.diff(close, prepend=close[0]))
    return np.cumsum(sign * volume)


def up_down_volume_ratio(close: Array, volume: Array, window: int) -> float | None:
    """Volume on up-days ÷ volume on down-days over the last `window` sessions."""
    if len(close) < window + 1:
        return None
    d = np.diff(close[-(window + 1) :])
    v = volume[-window:]
    up, down = v[d > 0].sum(), v[d < 0].sum()
    if down == 0:
        return None if up == 0 else float("inf")
    return float(up / down)


def rs_line(close: Array, bench: Array) -> Array:
    """Price ÷ benchmark, element-wise (both already aligned on dates)."""
    return close / bench


def mansfield(rs: Array, window: int = 252) -> float | None:
    """Mansfield relative strength: (RS ÷ its 52-week average − 1) × 100."""
    avg = sma(rs, window)
    if avg is None or avg == 0:
        return None
    return float((rs[-1] / avg - 1) * 100)


def percentile_rank(value: float, population: list[float]) -> float | None:
    """Share of the population at or below value, as 0–100; needs ≥ 2 peers."""
    peers = [p for p in population if np.isfinite(p)]
    if len(peers) < 2:
        return None
    return float(100 * sum(1 for p in peers if p <= value) / len(peers))


def stage(
    close: Array, ma150: Array, slope_sessions: int, flat_tol: float, prior: int
) -> int | None:
    """Weinstein stage from the 150 DMA (30-week average): 1 basing, 2 advancing, 3 topping, 4 declining."""
    if (
        np.isnan(ma150[-1])
        or len(ma150) < slope_sessions + 1
        or np.isnan(ma150[-1 - slope_sessions])
    ):
        return None
    chg = ma150[-1] / ma150[-1 - slope_sessions] - 1
    if chg > flat_tol:
        return 2
    if chg < -flat_tol:
        return 4
    older = ma150[-1 - prior] if len(ma150) > prior and not np.isnan(ma150[-1 - prior]) else None
    if older is None:
        return 1 if close[-1] <= ma150[-1] else 3
    return 3 if ma150[-1] >= older else 1


def drawdown_from_peak(x: Array, window: int) -> float | None:
    if len(x) < window:
        return None
    peak = x[-window:].max()
    return float(x[-1] / peak - 1)
