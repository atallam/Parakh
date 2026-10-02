"""Intrinsic-value maths for the value lens (plan 01 §2.6): pure functions, no I/O.

All "cash flow" inputs are per share. The two-stage model grows the cash flow at `g` for
`explicit_years`, fades the growth linearly to `terminal_g` over `fade_years`, then capitalises
the final year with a Gordon growth terminal value.
"""

from __future__ import annotations

import math


def dcf_value(
    cf0: float,
    g: float,
    coe: float,
    terminal_g: float,
    explicit_years: int,
    fade_years: int,
) -> float | None:
    """Present value per share of a two-stage cash-flow stream; None if it is undefined."""
    if cf0 <= 0 or coe <= terminal_g:
        return None
    cf, pv, t = cf0, 0.0, 0
    for _ in range(explicit_years):
        t += 1
        cf *= 1 + g
        pv += cf / (1 + coe) ** t
    for k in range(1, fade_years + 1):
        t += 1
        cf *= 1 + g + (terminal_g - g) * k / fade_years
        pv += cf / (1 + coe) ** t
    terminal = cf * (1 + terminal_g) / (coe - terminal_g)
    return pv + terminal / (1 + coe) ** t


def implied_growth(
    price: float,
    cf0: float,
    coe: float,
    terminal_g: float,
    explicit_years: int,
    fade_years: int,
    max_g: float,
    min_g: float = -0.2,
) -> float | None:
    """Reverse DCF: the growth the price assumes (bisection). None when no growth in range fits."""
    if price <= 0 or cf0 <= 0:
        return None

    def f(g: float) -> float:
        v = dcf_value(cf0, g, coe, terminal_g, explicit_years, fade_years)
        return (v if v is not None else math.nan) - price

    lo, hi = min_g, max_g
    flo, fhi = f(lo), f(hi)
    if math.isnan(flo) or math.isnan(fhi) or flo > 0 or fhi < 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def graham_number(eps: float, bvps: float, multiplier: float) -> float | None:
    """√(22.5 × EPS × BVPS); None for non-positive inputs."""
    if eps <= 0 or bvps <= 0:
        return None
    return math.sqrt(multiplier * eps * bvps)


def cagr(first: float, last: float, years: float) -> float | None:
    """Compound annual growth; None if either end is non-positive or years ≤ 0."""
    if first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def expected_irr(
    price: float, eps: float, growth: float, exit_pe: float, years: int, dividend_yield: float
) -> float | None:
    """Annualised return from EPS growth, exit multiple and dividend yield over `years`."""
    if price <= 0 or eps <= 0 or exit_pe <= 0:
        return None
    end = eps * (1 + growth) ** years * exit_pe
    if end <= 0:
        return None
    return (end / price) ** (1 / years) - 1 + dividend_yield
