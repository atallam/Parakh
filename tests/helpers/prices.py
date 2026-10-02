"""Synthetic price frames for lens tests (no network, deterministic)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd


def make_prices(
    n: int,
    end: dt.date = dt.date(2026, 10, 30),
    start_price: float = 100.0,
    drift: float = 0.0006,
    vol: float = 0.008,
    seed: int = 1,
    volume: float = 1_000_000.0,
    isin: str = "INE000000000",
) -> pd.DataFrame:
    """n business days ending at `end`: geometric random walk with drift, smooth by default."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    rets = rng.normal(drift, vol, n)
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    high = np.maximum(open_, close) * 1.004
    low = np.minimum(open_, close) * 0.996
    vols = volume * (1 + 0.1 * rng.standard_normal(n)).clip(0.5, 1.5)
    return pd.DataFrame(
        {
            "isin": isin,
            "trade_date": [d.date() for d in days],
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "adj_close": close,
            "volume": vols,
            "source": "test",
        }
    )


def make_index(
    prices: pd.DataFrame, drift: float = 0.0002, vol: float = 0.005, seed: int = 9
) -> pd.Series:
    rng = np.random.default_rng(seed)
    n = len(prices)
    level = 1000 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    return pd.Series(level, index=pd.to_datetime(prices["trade_date"]).dt.date)
