# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false, reportOperatorIssue=false, reportOptionalSubscript=false, reportAssignmentType=false
# why: tests build pandas/numpy fixtures and read optional result fields the assertions already prove are set
"""Synthetic worlds for the calibration tests: persistent drifts, a hand-made score panel, valid ISINs."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from parakh.calibration.panel import PANEL_COLUMNS, month_ends, period_of
from parakh.configs.models import Security


def make_isin(n: int) -> str:
    """A valid ISO 6166 ISIN: `INE` + six digits + 02 + the check digit."""
    body = f"INE{n:06d}01"
    digits = "".join(str(int(ch, 36)) for ch in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return body + str((10 - total % 10) % 10)


def frame(
    isin: str, days: pd.DatetimeIndex, close: np.ndarray, volume: float = 2e6
) -> pd.DataFrame:
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {
            "isin": isin,
            "trade_date": [d.date() for d in days],
            "open": open_,
            "high": np.maximum(open_, close) * 1.003,
            "low": np.minimum(open_, close) * 0.997,
            "close": close,
            "adj_close": close,
            "volume": volume,
            "source": "test",
        }
    )


def world(
    n_stocks: int = 20,
    years: float = 8.0,
    end: dt.date = dt.date(2026, 9, 30),
    seed: int = 7,
    spread: float = 0.0014,
    vol: float = 0.011,
) -> tuple[dict[str, pd.DataFrame], pd.Series, list[str]]:
    """Prices with a persistent per-stock drift (so momentum is real), and a market index."""
    rng = np.random.default_rng(seed)
    n = int(years * 252)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    drifts = np.linspace(-spread, spread, n_stocks)
    rng.shuffle(drifts)
    prices: dict[str, pd.DataFrame] = {}
    isins = []
    for k in range(n_stocks):
        isin = make_isin(k + 1)
        isins.append(isin)
        rets = rng.normal(drifts[k] + 0.0004, vol, n)
        prices[isin] = frame(isin, days, 100 * np.exp(np.cumsum(rets)))
    idx = 1000 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, n)))
    bench = pd.Series(idx, index=[d.date() for d in days])
    return prices, bench, isins


def securities(isins: list[str], cap: str = "large") -> list[Security]:
    return [
        Security(
            symbol=f"S{k + 1}",
            isin=i,
            name=f"Stock {k + 1}",
            cap=cap,
            cap_source="test",
            profile="bank",
        )  # type: ignore[arg-type]
        for k, i in enumerate(isins)
    ]


def trailing_panel(
    prices: dict[str, pd.DataFrame],
    segment: str = "large",
    first: dt.date | None = None,
    member: dict[str, tuple[dt.date, dt.date | None]] | None = None,
) -> pd.DataFrame:
    """A score panel from trailing 12-1 momentum, rank-scaled to 0-100. No lens, so it is fast.

    `member` maps an ISIN to (first month-end it may appear, first month-end it may not).
    """
    arrs = {
        isin: (
            np.array([pd.Timestamp(d).date() for d in f["trade_date"]]),
            f["close"].to_numpy(float),
        )
        for isin, f in prices.items()
    }
    all_days = sorted({d for ds, _ in arrs.values() for d in ds})
    rows = []
    for asof in month_ends(all_days):
        if first and asof < first:
            continue
        vals: dict[str, float] = {}
        last: dict[str, float] = {}
        for isin, (ds, c) in arrs.items():
            n = int(np.searchsorted(ds, asof, side="right"))
            if n < 253:
                continue
            vals[isin] = float(c[n - 22] / c[n - 253] - 1)
            last[isin] = float(c[n - 1])
        order = sorted(vals, key=lambda i: vals[i])
        for r, isin in enumerate(order):
            if member and isin in member:
                lo, hi = member[isin]
                if asof < lo or (hi is not None and asof >= hi):
                    continue
            rows.append(
                {
                    "period": period_of(asof), "asof": asof, "isin": isin, "symbol": isin[-4:],
                    "segment": segment, "member": True, "close": last[isin],
                    "score": 100 * (r + 0.5) / len(order), "view": "NEUTRAL", "confidence": "High",
                    "informational": False, "sessions": 300, "rs_percentile": None, "signals": "",
                    "momentum_hash": "t",
                }
            )  # fmt: skip
    return pd.DataFrame(rows, columns=PANEL_COLUMNS)
