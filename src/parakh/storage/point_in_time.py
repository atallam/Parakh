"""Point-in-time reads (plan 04 §4 #3; AC-F02.3): what was public on a given date.

    rows = visible_asof(stored_rows, asof=D, assumed_lag_days=cfg.assumed_report_lag_days)

Works on rows from `fundamentals` (versioned) and `shareholding` (one row per filing). A row is
visible on D when its `reported_on` is on or before D. A row with no `reported_on` (an old
annual figure the exchange feed does not date) becomes visible `assumed_lag_days` after its
period end, which is later than any real filing could be. For each key the newest visible
version wins, so a restatement made after D never leaks into a score for D.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

FUNDAMENTAL_KEY = ("isin", "metric_id", "period_type", "period_end", "source_id")
SHAREHOLDING_KEY = ("isin", "period_end")


def _date(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def visible_on(row: dict[str, Any], assumed_lag_days: int) -> dt.date:
    if row.get("reported_on"):
        return _date(row["reported_on"])
    return _date(row["period_end"]) + dt.timedelta(days=assumed_lag_days)


def visible_asof(
    rows: list[dict[str, Any]],
    asof: dt.date,
    assumed_lag_days: int,
    key: tuple[str, ...] = FUNDAMENTAL_KEY,
) -> list[dict[str, Any]]:
    best: dict[tuple[Any, ...], tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for row in rows:
        seen = visible_on(row, assumed_lag_days)
        if seen > asof:
            continue
        k = tuple(str(row.get(c)) for c in key)
        rank = (int(row.get("version") or 1), seen)
        if k not in best or rank > best[k][0]:
            best[k] = (rank, row)
    return [row for _, row in best.values()]
