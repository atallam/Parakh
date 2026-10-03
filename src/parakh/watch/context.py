"""Market context for the regime: FII/DII flows and breadth (plan 02 §5; F16).

    flows = FlowStore(store); flows.record(feeds.fii_dii())
    ctx = MarketContext.load(store, asof, bundle.regime)   # → segment_regime(..., fii_net_20d_cr=…)

NSE publishes only the latest session's flows, so the history builds up one daily run at a time.
Until 20 sessions are stored the 20-day figure is `None` and the regime says so; it is never
estimated. Breadth is the share of a segment's constituents above their 200-day average. It needs the
constituents' prices; below `min_coverage` of them it is `None`, and the regime falls back to the
benchmark trend and records why (the existing "breadth unavailable" flag).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from parakh.configs.lens_models import RegimeConfig
from parakh.watch.events import parse_nse_date
from parakh.watch.state import StateStore

FLOWS = "flows"
BREADTH = "breadth"
WINDOW = 20  # why: plan 02 §5, flows are judged over 20 sessions
KEEP_DAYS = 400
MIN_COVERAGE = 0.8  # why: breadth over fewer than 80% of the members would be a guess


def _num(text: Any) -> float | None:
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


class FlowStore:
    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.data: dict[str, dict[str, float]] = store.load(FLOWS)

    def record(self, rows: list[dict[str, Any]]) -> list[dt.date]:
        """Add the days in an NSE `fiidiiTradeReact` response; returns the days stored."""
        by_day: dict[dt.date, dict[str, float]] = {}
        for r in rows:
            day = parse_nse_date(r.get("date"))
            net = _num(r.get("netValue"))
            cat = str(r.get("category") or "").upper()
            if day is None or net is None:
                continue
            key = (
                "fii_net_cr"
                if cat.startswith("FII")
                else "dii_net_cr"
                if cat.startswith("DII")
                else None
            )
            if key:
                by_day.setdefault(day, {})[key] = net
        added = []
        for day, vals in sorted(by_day.items()):
            if {"fii_net_cr", "dii_net_cr"} <= vals.keys():
                self.data[day.isoformat()] = vals
                added.append(day)
        cutoff = (dt.date.today() - dt.timedelta(days=KEEP_DAYS)).isoformat()
        self.data = {k: v for k, v in self.data.items() if k >= cutoff or added}
        self.store.save(FLOWS, self.data)
        return added

    def window(self, asof: dt.date) -> list[tuple[str, dict[str, float]]]:
        days = sorted(d for d in self.data if d <= asof.isoformat())
        return [(d, self.data[d]) for d in days[-WINDOW:]]

    def net_20d(self, asof: dt.date) -> tuple[float | None, bool]:
        """(FII net over the last 20 sessions in ₹ crore, whether DIIs absorbed it); None if short."""
        w = self.window(asof)
        if len(w) < WINDOW:
            return None, False
        fii = sum(v["fii_net_cr"] for _, v in w)
        dii = sum(v["dii_net_cr"] for _, v in w)
        return fii, dii >= -fii and fii < 0


def breadth_pct(
    frames: dict[str, pd.DataFrame],
    asof: dt.date,
    ma: int = 200,
    min_coverage: float = MIN_COVERAGE,
) -> float | None:
    """Share of members with close above their `ma`-day average on `asof`; None if too few can be judged."""
    judged = above = 0
    for f in frames.values():
        if f is None or f.empty:
            continue
        g = f[f["trade_date"] <= asof].sort_values("trade_date")
        close = g["close"].astype(float).to_numpy()
        close = close[np.isfinite(close)]
        if len(close) < ma or pd.Timestamp(g["trade_date"].iloc[-1]).date() != asof:
            continue
        judged += 1
        above += int(close[-1] > close[-ma:].mean())
    if not frames or judged / len(frames) < min_coverage:
        return None
    return above / judged


@dataclass
class MarketContext:
    asof: dt.date
    fii_net_20d_cr: float | None = None
    dii_absorbing: bool = False
    flow_sessions: int = 0
    breadth: dict[str, float | None] = field(default_factory=dict)  # by cap
    notes: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, store: StateStore, asof: dt.date) -> MarketContext:
        flows = FlowStore(store)
        fii, absorbed = flows.net_20d(asof)
        ctx = cls(asof, fii, absorbed, len(flows.window(asof)))
        saved = store.load(BREADTH).get(asof.isoformat(), {})
        ctx.breadth = {k: v for k, v in saved.items()}
        if fii is None:
            ctx.notes.append(
                f"flows: {ctx.flow_sessions} of {WINDOW} sessions stored; 20-day figure not yet available"
            )
        return ctx


def record_breadth(store: StateStore, asof: dt.date, by_cap: dict[str, float | None]) -> None:
    data = store.load(BREADTH)
    data[asof.isoformat()] = by_cap
    keep = sorted(data)[-KEEP_DAYS:]
    store.save(BREADTH, {k: data[k] for k in keep})


def regime_kwargs(ctx: MarketContext | None, cap: str, cfg: RegimeConfig) -> dict[str, Any]:  # noqa: ARG001
    """Keyword arguments for `segment_regime`; empty when there is no context."""
    if ctx is None:
        return {}
    return {
        "breadth": ctx.breadth.get(cap),
        "fii_net_20d_cr": ctx.fii_net_20d_cr,
        "dii_absorbing": ctx.dii_absorbing,
    }
