# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Momentum calculation context: price bars, the listing exclusion and a memoising `Calc`.

`Calc` holds one stock's aligned price arrays and hands out measures lazily. A `Measure` is a
value or a reason it is missing (UX-05: ❔ N/A with its reason, never zero). `Calc.truncate(k)`
returns the same stock as of k sessions earlier, which the signals use for 2-close confirmation
and for "was X k sessions ago" tests.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from parakh.configs.lens_models import MomentumConfig


@dataclass(frozen=True)
class Measure:
    value: float | None
    reason: str | None = None  # set when value is None

    @staticmethod
    def na(reason: str) -> Measure:
        return Measure(None, reason)


@dataclass(frozen=True)
class Bars:
    dates: np.ndarray  # datetime.date objects, ascending
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray  # split/bonus-adjusted
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.close)


def make_bars(frame: pd.DataFrame, asof: dt.date) -> Bars:
    """Bars up to the as-of date from a price frame (plan 05 PRICE_COLUMNS), adjusted.

    High, low and open are scaled by adj_close ÷ close so a split or bonus leaves no artificial
    gap (AC-F02.2 carried into the lens).
    """
    f = frame.copy()
    f["trade_date"] = pd.to_datetime(f["trade_date"]).dt.date
    f = f[f["trade_date"] <= asof].sort_values("trade_date")
    f = f.dropna(subset=["close"])
    f = f[f["close"] > 0]
    adj = f["adj_close"].where(f["adj_close"].notna(), f["close"])
    k = (adj / f["close"]).to_numpy(float)
    return Bars(
        dates=f["trade_date"].to_numpy(),
        open=f["open"].to_numpy(float) * k,
        high=f["high"].to_numpy(float) * k,
        low=f["low"].to_numpy(float) * k,
        close=adj.to_numpy(float),
        volume=f["volume"].to_numpy(float),
    )


def exclude_listing(bars: Bars, listed_on: dt.date | None, cfg: MomentumConfig) -> tuple[Bars, int]:
    """Drop the first sessions after listing (plan 02 §3.9, AC-F05.7).

    Applies only when the stored history starts at listing: a stock with ten years of data that
    listed in 2015 keeps every session. Returns the trimmed bars and how many were dropped.
    """
    h = cfg.history
    if listed_on is None or len(bars) == 0 or h.listing_exclusion_sessions == 0:
        return bars, 0
    first = bars.dates[0]
    if (first - listed_on).days > h.listing_window_days:
        return bars, 0
    n = min(h.listing_exclusion_sessions, len(bars))
    s = slice(n, None)
    return (
        Bars(bars.dates[s], bars.open[s], bars.high[s], bars.low[s], bars.close[s], bars.volume[s]),
        n,
    )


def align(series: pd.Series | None, dates: np.ndarray) -> np.ndarray | None:
    """Benchmark closes on the stock's dates (forward-filled up to 5 sessions); None if unusable."""
    if series is None or len(series) == 0 or len(dates) == 0:
        return None
    s = series.copy()
    s.index = pd.to_datetime(s.index).date
    out = s.reindex(list(dates)).ffill(limit=5).to_numpy(float)
    if not np.isfinite(out[-1]):
        return None
    # leading gaps (benchmark starts later) are left as NaN; callers use the finite tail
    return out


@dataclass
class MomentumInputs:
    isin: str
    symbol: str
    cap: str
    asof: dt.date
    bars: Bars
    excluded_sessions: int = 0
    bench: np.ndarray | None = None  # aligned to bars.dates
    sector: np.ndarray | None = None
    segment_mom: list[float] = field(default_factory=list)  # peers' 12-1 (or 6M vol-adj) values
    results_dates: list[dt.date] = field(default_factory=list)  # exchange broadcast dates
    earnings_accel: Measure = field(
        default_factory=lambda: Measure.na("quarterly results not loaded")
    )
    bench_reason: str = "benchmark series not loaded"
    sector_reason: str = "sector index series not loaded"


@dataclass
class Calc:
    """Lazily computed, memoised measures for one stock at one as-of session."""

    inp: MomentumInputs
    cfg: MomentumConfig
    _cache: dict[str, object] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    # -- plumbing -----------------------------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.inp.bars)

    @property
    def close(self) -> np.ndarray:
        return self.inp.bars.close

    def memo[T](self, key: str, fn: callable[[], T]) -> T:  # type: ignore[valid-type]
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]  # type: ignore[return-value]

    def truncate(self, k: int) -> Calc:
        """The same stock k sessions earlier (k=0 returns self)."""
        if k <= 0:
            return self
        b = self.inp.bars
        cut = slice(0, max(0, len(b) - k))
        nb = Bars(b.dates[cut], b.open[cut], b.high[cut], b.low[cut], b.close[cut], b.volume[cut])
        inp = MomentumInputs(
            self.inp.isin,
            self.inp.symbol,
            self.inp.cap,
            self.inp.asof,
            nb,
            self.inp.excluded_sessions,
            None if self.inp.bench is None else self.inp.bench[cut],
            None if self.inp.sector is None else self.inp.sector[cut],
            self.inp.segment_mom,
            self.inp.results_dates,
            self.inp.earnings_accel,
            self.inp.bench_reason,
            self.inp.sector_reason,
        )
        return Calc(inp, self.cfg)

    # -- history gates ------------------------------------------------------------------------
    def need(self, key: str) -> int:
        return self.cfg.history.min_sessions[key]

    def short_reason(self, key: str, closes_needed: int | None = None) -> str | None:
        """Reason a measure can't be computed yet, or None when history suffices."""
        need = self.need(key)
        have = self.n
        want = closes_needed if closes_needed is not None else need
        if have >= want:
            return None
        listed = " after the listing exclusion" if self.inp.excluded_sessions else ""
        return f"{have} sessions{listed}; needs {need}"

    def sessions_for_window(self, key: str) -> tuple[int, bool] | None:
        """Window for 52-week measures: the full year, or since-listing if long enough.

        Returns (window, is_since_listing) or None when even the substitute is too short.
        """
        full = self.need(key)
        if self.n >= full:
            return full, False
        if self.n >= self.cfg.history.since_listing_min_sessions:
            return self.n, True
        return None

    # -- common series ------------------------------------------------------------------------
    def ma_series(self, window: int) -> np.ndarray:
        from parakh.analytics.indicators import sma_series

        return self.memo(f"ma{window}", lambda: sma_series(self.close, window))

    def ma(self, window: int, key: str) -> float | None:
        if self.n < self.need(key):
            return None
        v = self.ma_series(window)[-1]
        return float(v) if np.isfinite(v) else None

    def rs(self) -> np.ndarray | None:
        b = self.inp.bench
        if b is None:
            return None
        ok = np.isfinite(b)
        if not ok.any():
            return None
        out = np.full(len(b), np.nan)
        out[ok] = self.close[ok] / b[ok]
        return out
