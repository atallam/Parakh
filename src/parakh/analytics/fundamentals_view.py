"""A point-in-time view over fundamentals rows (plan 05 §3.4, AC-F02.3).

Build it from rows already filtered with `storage.point_in_time.visible_asof`, so a restatement
made after the as-of date can never leak in. Rows use the long format of the `fundamentals`
table: `metric_id` is `<section>.<line item>` exactly as the Screener export names it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

ANNUAL = "annual"
QUARTER = "quarter"


def _d(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


class Fundamentals:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._series: dict[tuple[str, str, str], dict[dt.date, float]] = {}
        self.reported_on: dict[dt.date, dt.date] = {}  # quarter end → broadcast date
        for r in rows:
            if r.get("value") is None:
                continue
            section, _, item = str(r["metric_id"]).partition(".")
            key = (str(r["period_type"]), section, item)
            self._series.setdefault(key, {})[_d(r["period_end"])] = float(r["value"])
            if r["period_type"] == QUARTER and r.get("reported_on"):
                end = _d(r["period_end"])
                self.reported_on[end] = min(
                    _d(r["reported_on"]), self.reported_on.get(end, dt.date.max)
                )

    def has_data(self) -> bool:
        return bool(self._series)

    def annual(self, section: str, item: str, since: dt.date | None = None) -> pd.Series:
        s = pd.Series(self._series.get((ANNUAL, section, item), {}), dtype=float).sort_index()
        return s[s.index >= since] if since is not None and len(s) else s

    def quarterly(self, section: str, item: str) -> pd.Series:
        return pd.Series(self._series.get((QUARTER, section, item), {}), dtype=float).sort_index()

    @property
    def last_annual(self) -> dt.date | None:
        s = self.annual("annual_pl", "Sales")
        return s.index[-1] if len(s) else None

    @property
    def last_quarter(self) -> dt.date | None:
        s = self.quarterly("quarterly_pl", "Sales")
        return s.index[-1] if len(s) else None

    def ttm(self, item: str) -> float | None:
        """Sum of the last four consecutive quarters of a quarterly P&L line, or None."""
        s = self.quarterly("quarterly_pl", item)
        if len(s) < 4:
            return None
        last4 = s.iloc[-4:]
        span = (last4.index[-1] - last4.index[0]).days
        if not 240 <= span <= 300:  # four consecutive quarters end ~9 months apart
            return None
        return float(last4.sum())

    def result_dates(self) -> list[dt.date]:
        return sorted(set(self.reported_on.values()))
