"""XIRR, the benchmark comparison and portfolio risk numbers (F10 v2). Pure functions, no I/O.

    xirr([(date(2024,1,1), -100.0), (date(2025,1,1), 120.0)])        # 0.2  (20% a year)
    max_drawdown([100, 120, 90, 110])                                # -0.25
    hhi([40, 30, 20, 10])                                            # 0.30  (weights in percent)

XIRR solves sum(cf / (1+r)^(days/365)) = 0 by bisection, which cannot diverge. It returns None
when there is no sign change (all outflows or all inflows) or the span is under a week, because a
rate over a few days is noise, not information.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

MIN_SPAN_DAYS = 7


def _npv(rate: float, flows: Sequence[tuple[dt.date, float]], t0: dt.date) -> float:
    return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.0) for d, cf in flows)


def xirr(flows: Sequence[tuple[dt.date, float]]) -> float | None:
    if len(flows) < 2:
        return None
    flows = sorted(flows, key=lambda x: x[0])
    if not (any(cf < 0 for _, cf in flows) and any(cf > 0 for _, cf in flows)):
        return None
    if (flows[-1][0] - flows[0][0]).days < MIN_SPAN_DAYS:
        return None
    t0 = flows[0][0]
    lo, hi = -0.999, 10.0
    f_lo, f_hi = _npv(lo, flows, t0), _npv(hi, flows, t0)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, flows, t0)
        if abs(f_mid) < 1e-9 or (hi - lo) < 1e-12:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def max_drawdown(values: Sequence[float]) -> float | None:
    """Largest peak-to-trough fall as a negative fraction; None for fewer than two values."""
    vals = [v for v in values if v is not None and v > 0]
    if len(vals) < 2:
        return None
    peak, worst = vals[0], 0.0
    for v in vals:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1.0)
    return worst


def hhi(weights_pct: Sequence[float]) -> float | None:
    """Herfindahl-Hirschman index of weights given in percent, scaled 0..1 (1 = one stock)."""
    total = sum(w for w in weights_pct if w and w > 0)
    if total <= 0:
        return None
    return sum((w / total) ** 2 for w in weights_pct if w and w > 0)


def top_n_share(weights_pct: Sequence[float], n: int = 5) -> float | None:
    total = sum(w for w in weights_pct if w and w > 0)
    if total <= 0:
        return None
    return sum(sorted((w for w in weights_pct if w and w > 0), reverse=True)[:n]) / total * 100.0


def benchmark_xirr(
    lots: Sequence[tuple[dt.date, float]], series: dict[dt.date, float], asof: dt.date
) -> float | None:
    """The XIRR you would have had putting each lot's rupees into the index on the same day.

    `lots` is (trade date, rupees invested). The index level on a date is the last close on or before
    it; a lot older than the series start is skipped and the answer is None if any is.
    """
    if not lots or not series:
        return None
    days = sorted(series)
    end = max((d for d in days if d <= asof), default=None)
    if end is None:
        return None
    units = 0.0
    flows: list[tuple[dt.date, float]] = []
    for d, amount in lots:
        on_or_before = [x for x in days if x <= d]
        if not on_or_before:
            return None
        units += amount / series[on_or_before[-1]]
        flows.append((d, -amount))
    flows.append((asof, units * series[end]))
    return xirr(flows)
