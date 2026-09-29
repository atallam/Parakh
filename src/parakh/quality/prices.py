"""Price-frame checks: schema (pandera), history length, staleness, unexplained gaps.

Check IDs:
- DQ.prices.schema: types, positive prices, low ≤ high, no duplicate dates per ISIN.
- DQ.prices.history: the frame starts within a week of the required start (10 years, or the
  listing date for young listings; D24).
- DQ.prices.stale: the last bar is at most N trading days old.
- DQ.prices.gaps: no one-day move over the threshold without a corporate action.
- DQ.prices.cross_source: recent closes agree with the exchange within tolerance.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pandera.pandas as pa

from parakh.adapters.corporate_actions import CorporateAction, find_gaps, unexplained
from parakh.adapters.prices import CloseCheck
from parakh.configs.models import PriceDq
from parakh.quality import DqResult

PRICE_SCHEMA = pa.DataFrameSchema(
    {
        "isin": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")),
        "trade_date": pa.Column(object),
        "open": pa.Column(float, pa.Check.gt(0), nullable=True),
        "high": pa.Column(float, pa.Check.gt(0), nullable=True),
        "low": pa.Column(float, pa.Check.gt(0), nullable=True),
        "close": pa.Column(float, pa.Check.gt(0)),
        "adj_close": pa.Column(float, pa.Check.gt(0), nullable=True),
        "volume": pa.Column("int64", pa.Check.ge(0)),
        "source": pa.Column(str),
    },
    checks=[
        pa.Check(
            lambda f: f["low"].isna() | f["high"].isna() | (f["low"] <= f["high"]),
            name="low_le_high",
        ),
        pa.Check(lambda f: ~f.duplicated(subset=["isin", "trade_date"]), name="unique_date"),
    ],
    strict=False,
)
# why: Yahoo's first bar can land a few days after the requested start (holidays, weekends)
HISTORY_SLACK_DAYS = 7


def _trading_days_between(a: dt.date, b: dt.date) -> int:
    """Weekdays after a, up to and including b (holidays are counted: a conservative bound)."""
    days, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def required_start(today: dt.date, years: int, listed_on: dt.date | None) -> dt.date:
    """10 years back, or the listing date if the stock is younger (D24)."""
    try:
        start = today.replace(year=today.year - years)
    except ValueError:  # 29 Feb
        start = today.replace(year=today.year - years, day=28)
    return max(start, listed_on) if listed_on else start


def check_prices(
    frame: pd.DataFrame,
    isin: str,
    today: dt.date,
    listed_on: dt.date | None,
    actions: list[CorporateAction],
    cfg: PriceDq,
) -> list[DqResult]:
    results: list[DqResult] = []
    try:
        PRICE_SCHEMA.validate(frame, lazy=True)
        results.append(DqResult("DQ.prices.schema", isin, "pass", {"rows": len(frame)}))
    except pa.errors.SchemaErrors as exc:
        cases = exc.failure_cases
        results.append(
            DqResult(
                "DQ.prices.schema",
                isin,
                "fail",
                {
                    "failures": int(len(cases)),
                    "checks": sorted({str(c) for c in cases["check"]})[:5],
                },
            )
        )
    if frame.empty:
        return [*results, DqResult("DQ.prices.history", isin, "fail", {"rows": 0})]

    first, last = min(frame["trade_date"]), max(frame["trade_date"])
    need = required_start(today, cfg.history_years, listed_on)
    short = (first - need).days > HISTORY_SLACK_DAYS
    results.append(
        DqResult(
            "DQ.prices.history",
            isin,
            "fail" if short else "pass",
            {
                "first": first.isoformat(),
                "required_from": need.isoformat(),
                "since_listing": bool(listed_on and need == listed_on),
            },
        )
    )
    lag = _trading_days_between(last, today)
    results.append(
        DqResult(
            "DQ.prices.stale",
            isin,
            "fail" if lag > cfg.max_stale_trading_days else "pass",
            {"last": last.isoformat(), "trading_days_old": lag},
        )
    )
    closes = {
        d: float(c) for d, c in zip(frame["trade_date"], frame["close"], strict=True) if pd.notna(c)
    }
    bad = unexplained(find_gaps(closes, actions, cfg.max_unexplained_move_ratio))
    results.append(
        DqResult(
            "DQ.prices.gaps",
            isin,
            "fail" if bad else "pass",
            {
                "unexplained": [
                    {"day": g.day.isoformat(), "move": round(g.move_ratio, 3)} for g in bad[:5]
                ]
            },
        )
    )
    return results


def check_cross_source(isin: str, checks: list[CloseCheck], cfg: PriceDq) -> DqResult:
    """Pass when every compared session agrees; warn when none could be compared."""
    if not checks:
        return DqResult("DQ.prices.cross_source", isin, "warn", {"compared": 0})
    bad = [c for c in checks if not c.ok]
    return DqResult(
        "DQ.prices.cross_source",
        isin,
        "fail" if bad else "pass",
        {
            "compared": len(checks),
            "max_diff_pct": round(max(c.diff_pct for c in checks), 3),
            "tolerance_pct": cfg.close_mismatch_pct,
            "mismatched_days": [c.trade_date.isoformat() for c in bad[:5]],
        },
    )
