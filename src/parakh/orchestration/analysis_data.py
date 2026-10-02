"""Where the analysis reads its inputs from (plan 05). One protocol, two implementations.

The monthly run asks an `AnalysisData` for a stock's prices, fundamentals, shareholding and the
open tax lots; it never knows whether they come from Supabase + Parquet or from a test fixture.
Index series (benchmarks, VIX) live in the same price store under pseudo-ISINs `IDX-<NAME>`.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from parakh.holdings.lots import Lot


def index_key(name: str) -> str:
    """Pseudo-ISIN for an index series: `NIFTY 100` → `IDX-NIFTY-100`."""
    return "IDX-" + re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-")


class AnalysisData(Protocol):
    def prices(self, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame: ...
    def fundamentals(self, isin: str) -> list[dict[str, Any]]: ...
    def shareholding(self, isin: str) -> list[dict[str, Any]]: ...
    def open_lots(self) -> list[Lot]: ...
    def dq(self, isin: str) -> list[dict[str, Any]]: ...
    def index_close(self, name: str, end: dt.date) -> pd.Series | None: ...


def _series(frame: pd.DataFrame) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    f = frame.sort_values("trade_date")
    return pd.Series(
        f["close"].astype(float).to_numpy(),
        index=[pd.Timestamp(d).date() for d in f["trade_date"]],
    )


@dataclass
class InMemoryData:
    """Test double and fixture loader."""

    price_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    fundamental_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    shareholding_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    lots: list[Lot] = field(default_factory=list)
    dq_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    indices: dict[str, pd.Series] = field(default_factory=dict)

    def prices(self, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        f = self.price_frames.get(isin)
        if f is None:
            return pd.DataFrame()
        d = pd.to_datetime(f["trade_date"]).dt.date
        return f[(d >= start) & (d <= end)].reset_index(drop=True)

    def fundamentals(self, isin: str) -> list[dict[str, Any]]:
        return self.fundamental_rows.get(isin, [])

    def shareholding(self, isin: str) -> list[dict[str, Any]]:
        return self.shareholding_rows.get(isin, [])

    def open_lots(self) -> list[Lot]:
        return self.lots

    def dq(self, isin: str) -> list[dict[str, Any]]:
        return self.dq_rows.get(isin, [])

    def index_close(self, name: str, end: dt.date) -> pd.Series | None:
        s = self.indices.get(name)
        return None if s is None else s[[d <= end for d in s.index]]


class SupabaseData:
    """Supabase tables for fundamentals / shareholding / lots / DQ; Parquet for prices."""

    def __init__(self, repo: Any, store: Any, history_years: int = 11) -> None:
        self.repo, self.store, self.years = repo, store, history_years
        self._dq: dict[str, list[dict[str, Any]]] | None = None

    def prices(self, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        return self.store.query([isin], start, end)

    def fundamentals(self, isin: str) -> list[dict[str, Any]]:
        return self.repo.fundamentals_for(isin)

    def shareholding(self, isin: str) -> list[dict[str, Any]]:
        return self.repo.stored_shareholding(isin)

    def open_lots(self) -> list[Lot]:
        return self.repo.open_lots()

    def dq(self, isin: str) -> list[dict[str, Any]]:
        if self._dq is None:
            latest: dict[tuple[str, str], dict[str, Any]] = {}
            for r in self.repo.dq_rows():  # later rows overwrite earlier ones
                latest[(r["isin"], r["check_id"])] = r
            grouped: dict[str, list[dict[str, Any]]] = {}
            for (i, _), r in latest.items():
                grouped.setdefault(i, []).append(r)
            self._dq = grouped
        return self._dq.get(isin, [])

    def index_close(self, name: str, end: dt.date) -> pd.Series | None:
        start = dt.date(end.year - self.years, 1, 1)
        return _series(self.store.query([index_key(name)], start, end))
