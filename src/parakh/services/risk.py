"""Segment risk numbers from snapshots: drawdown, concentration, returns vs the benchmark (F10 v2).

Everything here reads fields the monthly run already stored; nothing is fetched. Holdings figures
are percentages only (AG-07): no rupee amounts leave this module.
"""

from __future__ import annotations

from typing import Any

from parakh.holdings.xirr import hhi, max_drawdown, top_n_share


def stock_drawdown(snap: dict[str, Any]) -> float | None:
    """Max drawdown over the snapshot's chart window, as a negative percent."""
    close = (snap.get("chart") or {}).get("close") or []
    dd = max_drawdown([c for c in close if c is not None])
    return None if dd is None else dd * 100.0


def holding_returns(snap: dict[str, Any]) -> dict[str, float | None]:
    pos = snap.get("position") or {}
    x, b = pos.get("xirr_pct"), pos.get("benchmark_xirr_pct")
    return {
        "xirr_pct": x,
        "benchmark_xirr_pct": b,
        "vs_benchmark_pp": None if x is None or b is None else round(x - b, 1),
    }


def portfolio_risk(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """HHI, top-5 share and effective number of stocks over the weights of priced holdings."""
    weights = [r["weight_pct"] for r in rows if r.get("weight_pct")]
    h = hhi(weights)
    return {
        "holdings_counted": len(weights),
        "hhi": None if h is None else round(h, 3),
        "effective_n": None if not h else round(1.0 / h, 1),
        "top5_pct": None if not weights else round(top_n_share(weights, 5) or 0.0, 1),
        "worst_drawdown_pct": min(
            (r["drawdown_pct"] for r in rows if r.get("drawdown_pct") is not None), default=None
        ),
    }
