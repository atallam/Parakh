# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Score-quintile calibration: does a higher score earn a higher forward return? (AC-F17.3)

    rows = attach_forward(panel, book, [3, 6, 12], gap_days)
    cal = calibrate(rows, "score", 6, cfg.quintiles, lens="momentum")
    cal.spread_pct, cal.ic_mean, cal.verdict

Each month-end the stocks are ranked on a lens's score and split into five buckets; the report is the
average forward return of each bucket and the top-minus-bottom spread, averaged over months, plus the
rank correlation (information coefficient, IC) between score and forward return. Monthly observations
of a 6-month return overlap, so the t-statistics divide the effective sample size by the horizon in
months; otherwise they would look five times more convincing than the data allows.

Three honest outcomes besides "it works":
- `insufficient`: too few usable months or too few scored names a month (the 7-stock pilot lands here);
- `inconclusive`: a positive spread that the noise could produce;
- `reversed`: the high scores earned less, which is the finding that should change a weight.
"""

from __future__ import annotations

import bisect
import calendar
import datetime as dt
import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from parakh.calibration.backtest import PriceBook
from parakh.configs.calibration_models import QuintileConfig


def add_months(day: dt.date, n: int) -> dt.date:
    m0 = day.month - 1 + n
    y, m = day.year + m0 // 12, m0 % 12 + 1
    return dt.date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def forward_months(
    book: PriceBook, isin: str, asof: dt.date, months: int, gap_days: int
) -> tuple[float | None, str]:
    """(return, status): matured | delisted | pending | no_data."""
    s = book.series.get(isin)
    if s is None:
        return None, "no_data"
    dates, vals = s
    i = bisect.bisect_right(dates, asof) - 1
    if i < 0 or vals[i] <= 0:
        return None, "no_data"
    target = add_months(asof, months)
    data_end = book.days[-1]
    if target > data_end:
        return None, "pending"
    j = bisect.bisect_right(dates, target) - 1
    if dates[-1] < target and (target - dates[-1]).days > gap_days:
        return vals[-1] / vals[i] - 1, "delisted"
    return vals[j] / vals[i] - 1, "matured"


def attach_forward(
    rows: pd.DataFrame, book: PriceBook, months: list[int], gap_days: int
) -> pd.DataFrame:
    """Add `fwd_<m>m` (a fraction) and `fwd_<m>m_status` for each horizon."""
    out = rows.copy()
    for m in months:
        res = [forward_months(book, r.isin, _d(r.asof), m, gap_days) for r in out.itertuples()]
        out[f"fwd_{m}m"] = [r for r, _ in res]
        out[f"fwd_{m}m_status"] = [s for _, s in res]
    return out


def _d(x: Any) -> dt.date:
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


@dataclass
class Bucket:
    rank: int  # 1 = lowest scores
    mean_pct: float | None
    n: int


@dataclass
class Calibration:
    lens: str
    horizon_months: int
    periods_used: int = 0
    periods_skipped: int = 0
    stocks_per_period: float | None = None
    buckets: list[Bucket] = field(default_factory=list)
    spread_pct: float | None = None  # top bucket minus bottom bucket, mean over periods
    spread_positive_pct: float | None = None  # share of periods with a positive spread
    spread_t: float | None = None
    ic_mean: float | None = None
    ic_t: float | None = None
    monotonic: bool | None = None
    verdict: str = "insufficient"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _t(values: list[float], horizon: int) -> float | None:
    n = len(values)
    if n < 3:
        return None
    sd = float(np.std(values, ddof=1))
    if sd == 0:
        return None
    n_eff = max(1.0, n / max(1, horizon))
    return float(np.mean(values) / (sd / math.sqrt(n_eff)))


def calibrate(
    rows: pd.DataFrame,
    score_col: str,
    horizon_months: int,
    cfg: QuintileConfig,
    *,
    lens: str,
) -> Calibration:
    fwd = f"fwd_{horizon_months}m"
    cal = Calibration(lens, horizon_months)
    if rows.empty or fwd not in rows or score_col not in rows:
        cal.reason = "no scored stock-months with a forward return yet"
        return cal
    per_bucket: list[list[float]] = [[] for _ in range(cfg.buckets)]
    counts = [0] * cfg.buckets
    spreads: list[float] = []
    ics: list[float] = []
    sizes: list[int] = []
    for _period, g in rows.groupby("asof"):
        g = g.dropna(subset=[score_col, fwd])
        if len(g) < cfg.min_stocks_per_period:
            cal.periods_skipped += 1
            continue
        ranks = g[score_col].rank(method="first")
        labels = pd.qcut(ranks, q=cfg.buckets, labels=False)
        means = g.groupby(labels)[fwd].mean()
        if len(means) < cfg.buckets:
            cal.periods_skipped += 1
            continue
        for b in range(cfg.buckets):
            per_bucket[b].append(float(means.iloc[b]))
            counts[b] += int((labels == b).sum())
        spreads.append(float(means.iloc[-1] - means.iloc[0]))
        ic = g[score_col].rank().corr(g[fwd].rank())  # Spearman, without scipy
        if ic is not None and np.isfinite(ic):
            ics.append(float(ic))
        sizes.append(len(g))
    cal.periods_used = len(spreads)
    if not spreads:
        cal.reason = (
            f"no month had {cfg.min_stocks_per_period} or more scored stocks with a "
            f"{horizon_months}-month forward return ({cal.periods_skipped} skipped)"
        )
        return cal
    cal.stocks_per_period = float(np.mean(sizes))
    cal.buckets = [
        Bucket(b + 1, float(np.mean(v)) * 100 if v else None, counts[b])
        for b, v in enumerate(per_bucket)
    ]
    cal.spread_pct = float(np.mean(spreads)) * 100
    cal.spread_positive_pct = 100 * float(np.mean([s > 0 for s in spreads]))
    cal.spread_t = _t(spreads, horizon_months)
    if ics:
        cal.ic_mean = float(np.mean(ics))
        cal.ic_t = _t(ics, horizon_months)
    means_only = [b.mean_pct for b in cal.buckets if b.mean_pct is not None]
    cal.monotonic = all(a <= b for a, b in zip(means_only, means_only[1:], strict=False))
    if cal.periods_used < cfg.min_periods:
        cal.verdict = "insufficient"
        cal.reason = (
            f"{cal.periods_used} usable month-ends; {cfg.min_periods} are needed before a "
            "spread is a finding"
        )
    elif cal.ic_t is not None and cal.ic_t >= cfg.min_ic_t_stat and cal.spread_pct > 0:
        cal.verdict = "confirmed"
        cal.reason = "higher scores earned more, beyond what luck explains"
    elif cal.ic_t is not None and cal.ic_t <= -cfg.min_ic_t_stat:
        cal.verdict = "reversed"
        cal.reason = "higher scores earned less, beyond what luck explains"
    else:
        cal.verdict = "inconclusive"
        cal.reason = "the spread is within what noise could produce"
    return cal


@dataclass
class VerdictRow:
    verdict: str
    n: int
    mean_pct: float | None
    hit_rate_pct: float | None


def by_verdict(
    rows: pd.DataFrame, horizon_months: int, verdict_col: str = "verdict"
) -> list[VerdictRow]:
    """Mean forward return and the share of positive outcomes per verdict (plan 04 §2)."""
    fwd = f"fwd_{horizon_months}m"
    if rows.empty or fwd not in rows or verdict_col not in rows:
        return []
    out = []
    for v, g in rows.dropna(subset=[fwd]).groupby(verdict_col):
        out.append(
            VerdictRow(str(v), len(g), float(g[fwd].mean()) * 100, 100 * float((g[fwd] > 0).mean()))
        )
    return sorted(out, key=lambda r: -(r.mean_pct or -1e9))
