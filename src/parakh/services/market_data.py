"""Prices, fundamentals and data quality as the lenses saw them (plan 15 §4.2; AG-04).

Everything here is read from the monthly snapshot, so what an agent sees is exactly what produced the
verdict, with the same source and as-of stamps. Nothing fetches at call time.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from parakh.services.portfolio_service import latest_snapshots
from parakh.services.report_service import _load, _stamp
from parakh.services.view_models import (
    DqCheck,
    FundamentalsOut,
    MetricValue,
    PriceRow,
    PricesOut,
    QualityOut,
)

MAX_PRICE_ROWS = 400


def fundamentals(
    symbol_or_isin: str,
    metrics: list[str] | None = None,
    as_of: str | None = None,
    root: Path | None = None,
) -> FundamentalsOut:
    sec, snap, _prev, msg = _load(symbol_or_isin, None, root)
    if snap is None:
        return FundamentalsOut(stamp=_stamp(), found=False, message=msg)
    assert sec is not None
    rows = (snap["value"].get("details") or {}).get("metrics") or {}
    out: list[MetricValue] = []
    for mid in sorted(rows):
        if metrics and mid not in metrics:
            continue
        r = rows[mid]
        if as_of and r.get("asof") and str(r["asof"]) > as_of:
            continue  # point in time: only what had been reported by `as_of`
        out.append(
            MetricValue(id=mid, value=r.get("value"), source=r.get("source"), asof=r.get("asof"))
        )
    unknown = [m for m in (metrics or []) if m not in rows]
    return FundamentalsOut(
        stamp=_stamp(snap),
        found=True,
        symbol=sec.symbol,
        as_of=as_of or str(snap["fundamentals_asof"].get("quarter")),
        metrics=out,
        unavailable={m: "not a value-lens metric for this stock" for m in unknown}
        | dict((snap["value"].get("na") or {}).items()),
    )


def prices(
    symbol_or_isin: str, start: str | None, end: str | None, root: Path | None = None
) -> PricesOut:
    sec, snap, _prev, msg = _load(symbol_or_isin, None, root)
    if snap is None:
        return PricesOut(stamp=_stamp(), found=False, message=msg)
    assert sec is not None
    chart = snap.get("chart") or {}
    dates = chart.get("dates") or []
    lo = dt.date.fromisoformat(start) if start else dt.date.min
    hi = dt.date.fromisoformat(end) if end else dt.date.max
    rows = [
        PriceRow(
            date=d,
            close=c,
            dma50=chart["dma50"][i] if chart.get("dma50") else None,
            dma200=chart["dma200"][i] if chart.get("dma200") else None,
        )  # fmt: skip
        for i, (d, c) in enumerate(zip(dates, chart.get("close") or [], strict=False))
        if lo <= dt.date.fromisoformat(str(d)[:10]) <= hi
    ]
    truncated = len(rows) > MAX_PRICE_ROWS
    return PricesOut(
        stamp=_stamp(snap),
        found=True,
        symbol=sec.symbol,
        source=str((snap.get("price") or {}).get("source")),
        rows=rows[-MAX_PRICE_ROWS:],
        truncated=truncated,
        message="Adjusted closes from the snapshot's chart window (about 12 months)."
        if rows
        else "No closes in that range within the chart window.",
    )


def quality(run_id: str | None = None, root: Path | None = None) -> QualityOut:
    snaps = latest_snapshots(root)
    if not snaps:
        return QualityOut(stamp=_stamp(), found=False, message="No snapshots yet.")
    checks: list[DqCheck] = []
    confidence: dict[str, str] = {}
    for s in snaps:
        dq: dict[str, Any] = s.get("data_quality") or {}
        confidence[s["symbol"]] = str(dq.get("confidence"))
        for c in dq.get("checks") or []:
            if run_id and c.get("run_id") != run_id:
                continue
            detail = c.get("detail")
            checks.append(
                DqCheck(
                    isin=s["isin"],
                    symbol=s["symbol"],
                    check_id=c["check_id"],
                    status=c["status"],
                    detail=(
                        ", ".join(map(str, detail.get("issues", [])))
                        if isinstance(detail, dict)
                        else str(detail or "")
                    )[:240],
                )  # fmt: skip
            )
    checks.sort(key=lambda c: ({"fail": 0, "warn": 1, "pass": 2}.get(c.status, 3), c.symbol))
    return QualityOut(
        stamp=_stamp(snaps[0]), found=True, checks=checks[:200], confidence=confidence
    )
