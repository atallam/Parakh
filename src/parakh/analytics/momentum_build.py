"""Builds a lens-ready `StockContext` (momentum part) from price data. No I/O: callers pass frames."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from parakh.analytics.metrics.momentum import compute_all, template_items
from parakh.analytics.momentum_calc import (
    Calc,
    Measure,
    MomentumInputs,
    align,
    exclude_listing,
    make_bars,
)
from parakh.analytics.signals.momentum import evaluate_signals
from parakh.configs.lens_models import MomentumConfig


def momentum_inputs(
    isin: str,
    symbol: str,
    cap: str,
    asof: dt.date,
    prices: pd.DataFrame,
    cfg: MomentumConfig,
    listed_on: dt.date | None = None,
    bench: pd.Series | None = None,
    sector: pd.Series | None = None,
    segment_mom: list[float] | None = None,
    results_dates: list[dt.date] | None = None,
    earnings_accel: Measure | None = None,
) -> MomentumInputs:
    bars, excluded = exclude_listing(make_bars(prices, asof), listed_on, cfg)
    inp = MomentumInputs(
        isin=isin,
        symbol=symbol,
        cap=cap,
        asof=asof,
        bars=bars,
        excluded_sessions=excluded,
        bench=align(bench, bars.dates),
        sector=align(sector, bars.dates),
        segment_mom=segment_mom or [],
        results_dates=results_dates or [],
    )
    if earnings_accel is not None:
        inp.earnings_accel = earnings_accel
    return inp


def momentum_extras(c: Calc) -> dict[str, Any]:
    """Non-numeric momentum inputs for the lens: template items, signals, flags, benchmark names."""
    items = template_items(c)
    states = evaluate_signals(c)
    caps = c.cfg.cap_settings[c.inp.cap]  # type: ignore[index]
    return {
        "template_items": [{"label": label, "passed": ok} for label, ok in items],
        "signals": [
            {
                "id": s.id,
                "name": s.name,
                "severity": s.severity,
                "status": s.status,
                "confirmed": s.confirmed,
                "date": s.date.isoformat() if s.date else None,
                "price": s.price,
                "note": s.note,
            }
            for s in states
        ],
        "flags": sorted(set(c.flags)),
        "benchmark": caps.benchmark,
        "excluded_sessions": c.inp.excluded_sessions,
        "last_session": c.inp.bars.dates[-1].isoformat() if len(c.inp.bars) else None,
    }


def momentum_context_parts(
    inp: MomentumInputs, cfg: MomentumConfig
) -> tuple[dict[str, float | None], dict[str, str], dict[str, Any]]:
    c = Calc(inp, cfg)
    values, reasons = compute_all(c)
    return values, reasons, momentum_extras(c)
