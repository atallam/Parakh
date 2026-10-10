"""The calibration service: from loaded data to the quarterly report (F17).

    inputs = CalibrationInputs(securities, prices, benches, membership, alert_rows, watchlist, ...)
    parts = compute_parts(bundle, inputs, allow_proxy=False)
    report = build_report(quarter=..., cfg=bundle.calibration, framework_version=..., parts=parts)

The CLI loads the data (prices from the price store, benchmarks, the local membership history, the
alerts log, the watchlist, the journal); this module only joins the pieces, so it runs the same on
synthetic data in tests and real data in production. It reads; it never writes scores, weights or
verdicts (AG-03).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from parakh.calibration import backtest as bt
from parakh.calibration import feedback, outcomes, quintiles
from parakh.calibration.journal import JournalEntry, stats
from parakh.calibration.membership import Membership
from parakh.calibration.panel import build_panel, momentum_hash, month_ends
from parakh.calibration.report import Parts
from parakh.calibration.scorecard import build_scorecard
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.watchlist.models import WatchlistState


@dataclass
class CalibrationInputs:
    securities: list[Security]
    prices: dict[str, pd.DataFrame]
    benches: dict[str, pd.Series]  # cap → benchmark close series (index = dates)
    wide_bench: pd.Series | None = None  # the backtest benchmark (NIFTY 500)
    membership: Membership | None = None
    alert_rows: list[dict[str, Any]] = field(default_factory=list)
    watchlist: WatchlistState | None = None
    journal: list[JournalEntry] = field(default_factory=list)
    first_buys: dict[str, dt.date] = field(default_factory=dict)
    start: dt.date | None = None  # first rebalance date to score; default: ten years back
    asof: dt.date | None = None


def rebalance_dates(
    prices: dict[str, pd.DataFrame], start: dt.date | None, asof: dt.date | None
) -> list[dt.date]:
    days = sorted(
        {
            dt.date.fromisoformat(str(d)[:10])
            for f in prices.values()
            if f is not None and len(f)
            for d in f["trade_date"]
        }
    )
    out = month_ends(days)
    return [d for d in out if (start is None or d >= start) and (asof is None or d <= asof)]


def membership_ok(
    bundle: ConfigBundle, m: Membership | None, start: dt.date
) -> tuple[bool, dict[str, Any]]:
    idx = bundle.calibration.backtest.membership_indices
    ids = [idx[c] for c in ("large", "mid", "small")]
    if m is None:
        return False, {"indices": ids, "first_known": {}, "needed_from": start.isoformat()}
    first: dict[str, str | None] = {}
    for i in ids:
        d = m.coverage_start(i)
        first[i] = d.isoformat() if d else None
    return m.covers_window(ids, start), {
        "indices": ids,
        "first_known": first,
        "needed_from": start.isoformat(),
    }


def compute_panel(
    bundle: ConfigBundle,
    inputs: CalibrationInputs,
    *,
    existing: pd.DataFrame | None = None,
    root: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    dates = rebalance_dates(inputs.prices, inputs.start, inputs.asof)
    return build_panel(
        bundle, inputs.securities, inputs.prices, inputs.benches, inputs.membership, dates,
        existing=existing, root=root, on_progress=on_progress,
    )  # fmt: skip


def compute_parts(
    bundle: ConfigBundle,
    inputs: CalibrationInputs,
    panel: pd.DataFrame,
    *,
    allow_proxy: bool = False,
    root: Path | None = None,
) -> Parts:
    cal = bundle.calibration
    book = bt.PriceBook.from_frames(inputs.prices)
    parts = Parts()
    gap = cal.outcomes.delisted_gap_days
    caps = {s.isin: s.cap for s in inputs.securities}
    bench_name = cal.backtest.benchmark
    wide = inputs.wide_bench
    start = dt.date.fromisoformat(str(panel["asof"].min())[:10]) if len(panel) else dt.date.today()
    ok, coverage = membership_ok(bundle, inputs.membership, start)
    parts.backtest = bt.run_backtest(
        panel, book, wide, cal, bundle.portfolio.tax, membership_ok=ok, coverage=coverage,
        momentum_hash=momentum_hash(bundle, root), allow_proxy=allow_proxy,
    ).as_dict()  # fmt: skip
    if wide is None:
        parts.notes.append(
            f"Benchmark {bench_name} is not loaded; the backtest shows no excess return."
        )
    # signal outcomes: live alerts plus the month-end panel, kept apart by `source`
    directions = dict(bundle.notify.routing.signal_direction)
    obs = outcomes.observations_from_alerts(inputs.alert_rows, directions)
    obs += outcomes.observations_from_panel(panel, directions)
    base = outcomes.unconditional(panel, book, cal.outcomes)
    parts.outcomes = outcomes.to_dict(
        outcomes.track(obs, book, inputs.benches, caps, cal.outcomes, base)
    )
    # score quintiles per lens, from the panel
    parts.quintiles = {}
    if len(panel):
        rows = quintiles.attach_forward(panel, book, cal.quintiles.horizons_months, gap)
        parts.quintiles["momentum"] = [
            quintiles.calibrate(rows, "score", m, cal.quintiles, lens="momentum").as_dict()
            for m in cal.quintiles.horizons_months
        ]
    parts.alerts = feedback.alert_precision(inputs.alert_rows, cal.alerts).as_dict()
    if inputs.watchlist is not None:
        parts.scorecard = build_scorecard(
            inputs.watchlist, book, inputs.benches, cal.scorecard, inputs.first_buys, gap
        ).as_dict()  # fmt: skip
    parts.journal = dict(stats(inputs.journal))
    parts.notes.append(
        "Only the momentum lens has a price-only history. The value lens needs point-in-time "
        "fundamentals, so its calibration waits for real monthly snapshots (plan 09 Phase 5)."
    )
    return parts


def snapshot_rows(root: Path) -> pd.DataFrame:
    """One row per stored stock-month, in the `history.csv` shape, for drift monitoring."""
    from parakh.snapshots.history import row_from
    from parakh.snapshots.store import read_snapshot_dict

    rows = []
    for path in sorted(root.glob("**/snapshots/*.json")):
        snap = read_snapshot_dict(path)
        if snap:
            rows.append(row_from(snap))
    return pd.DataFrame(rows)
