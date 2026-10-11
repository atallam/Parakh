# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""The price-only momentum score panel: one row per stock per month-end (F17).

    panel = build_panel(bundle, securities, prices, bench, membership, month_ends)

Each row is the momentum lens run as of that month-end on prices up to that day only, using the same
code the monthly run uses (`momentum_context_parts` + `MomentumLens`), so the backtest tests the lens
you actually use. Earnings momentum needs fundamentals and the regime needs breadth, so both are left
out here: earnings momentum drops out of the score (its weight re-normalises, AC-F04.8) and the
regime is held at Neutral. The report states both.

The panel is cached by `momentum_hash` (momentum.yaml plus the lens version): a month already scored
under the same settings is never recomputed, so the monthly job adds one month and a settings change
rebuilds everything. Nothing in the panel looks past its own `asof`; a test feeds a price jump the day
after and checks the earlier rows are unchanged.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from parakh.analytics import indicators as ind
from parakh.analytics.momentum_build import momentum_context_parts, momentum_inputs
from parakh.analytics.momentum_calc import make_bars
from parakh.calibration.membership import Membership
from parakh.config import config_dir
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.lenses.base import LensConfig, StockContext
from parakh.lenses.momentum import MomentumLens

log = structlog.get_logger(__name__)

PANEL_COLUMNS = [
    "period", "asof", "isin", "symbol", "segment", "member", "close", "score", "view",
    "confidence", "informational", "sessions", "rs_percentile", "signals", "momentum_hash",
]  # fmt: skip
CAPS = ("large", "mid", "small")


def momentum_hash(bundle: ConfigBundle, root: Path | None = None) -> str:
    """Short hash of everything that moves a momentum score: the settings file and the lens version."""
    raw = (root or config_dir()).joinpath("momentum.yaml").read_bytes().replace(b"\r\n", b"\n")
    d = hashlib.sha256(raw)
    d.update(MomentumLens.lens_version.encode())
    return d.hexdigest()[:8]


def month_ends(dates: Iterable[dt.date]) -> list[dt.date]:
    """The last date seen in each calendar month, ascending."""
    last: dict[tuple[int, int], dt.date] = {}
    for d in dates:
        k = (d.year, d.month)
        if k not in last or d > last[k]:
            last[k] = d
    return sorted(last.values())


def period_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _frame_dates(frame: pd.DataFrame) -> list[dt.date]:
    return [pd.Timestamp(x).date() for x in frame["trade_date"]]


def _segment(
    sec: Security,
    asof: dt.date,
    membership: Membership | None,
    indices: Mapping[str, str],
) -> tuple[str, bool] | None:
    """(segment, is_point_in_time_member), or None when the stock is not eligible that day."""
    if membership is None:
        return sec.cap, False
    pref = [indices[c] for c in CAPS if c in indices]
    hit = membership.index_of(sec.isin, asof, pref)
    if hit is None:
        return None
    return next(c for c in CAPS if indices.get(c) == hit), True


def score_stock(
    bundle: ConfigBundle,
    sec: Security,
    segment: str,
    asof: dt.date,
    prices: pd.DataFrame,
    bench: pd.Series | None,
    segment_mom: list[float],
):  # type: ignore[no-untyped-def]
    cfg = bundle.momentum
    inp = momentum_inputs(
        sec.isin, sec.symbol, segment, asof, prices, cfg, sec.listed_on, bench=bench,
        segment_mom=segment_mom,
    )  # fmt: skip
    values, reasons, extras = momentum_context_parts(inp, cfg)
    extras["regime"] = "Neutral"  # price-only: no breadth, so no Risk-Off cap
    ctx = StockContext(
        isin=sec.isin, symbol=sec.symbol, asof=asof, profile=sec.profile, cap=segment,
        metrics=values, na_reasons=reasons, extras=extras,
    )  # fmt: skip
    res = MomentumLens().evaluate(
        ctx, LensConfig(lens_version=cfg.lens_version, params={"settings": cfg})
    )
    return res, inp, extras


def _momentum_12_1(prices: pd.DataFrame, asof: dt.date) -> float | None:
    bars = make_bars(prices, asof)
    return ind.ret_12_1(bars.close) if len(bars) else None


def build_panel(
    bundle: ConfigBundle,
    securities: list[Security],
    prices: dict[str, pd.DataFrame],
    bench: dict[str, pd.Series],
    membership: Membership | None,
    rebalance_dates: list[dt.date],
    *,
    existing: pd.DataFrame | None = None,
    root: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Score every eligible stock on every rebalance date; reuse rows scored under the same settings."""
    h = momentum_hash(bundle, root)
    indices = bundle.calibration.backtest.membership_indices
    have: set[str] = set()
    kept = pd.DataFrame(columns=PANEL_COLUMNS)
    if existing is not None and len(existing):
        same = existing[existing["momentum_hash"] == h]
        kept = same
        have = set(same["period"])
    rows: list[dict[str, object]] = []
    # why: a stock listed after a rebalance date has no bars yet; it is not eligible then, which is
    # different from a scoring failure (and logging one warning per such stock-month is just noise)
    first_bar: dict[str, dt.date] = {
        isin: pd.to_datetime(f["trade_date"]).min().date()
        for isin, f in prices.items()
        if f is not None and not f.empty
    }
    for asof in rebalance_dates:
        period = period_of(asof)
        if period in have:
            continue
        eligible: list[tuple[Security, str, bool]] = []
        for sec in securities:
            frame = prices.get(sec.isin)
            if frame is None or frame.empty:
                continue
            if first_bar[sec.isin] > asof:
                continue
            seg = _segment(sec, asof, membership, indices)
            if seg is not None:
                eligible.append((sec, seg[0], seg[1]))
        peers: dict[str, list[float]] = {c: [] for c in CAPS}
        for sec, segment, _ in eligible:
            m = _momentum_12_1(prices[sec.isin], asof)
            if m is not None and np.isfinite(m):
                peers[segment].append(m)
        for sec, segment, is_member in eligible:
            frame = prices[sec.isin]
            try:
                res, inp, extras = score_stock(
                    bundle, sec, segment, asof, frame, bench.get(segment), peers[segment]
                )
            except Exception as exc:  # one stock never sinks the panel
                log.warning(
                    "panel_stock_failed", isin=sec.isin, asof=asof.isoformat(), error=str(exc)
                )
                continue
            n = len(inp.bars)
            confirm = bundle.notify.routing.confirm_closes
            live = [
                x["id"]
                for x in extras.get("signals", [])
                if x["status"] == "fired"
                and (x["confirmed"] or (confirm.get(x["id"]) is not None and confirm[x["id"]] <= 1))
            ]  # the same test the daily watcher applies before it alerts
            rows.append(
                {
                    "period": period,
                    "asof": asof,
                    "isin": sec.isin,
                    "symbol": sec.symbol,
                    "segment": segment,
                    "member": is_member,
                    "close": float(inp.bars.close[-1]) if n else np.nan,
                    "score": res.score,
                    "view": res.view,
                    "confidence": res.confidence,
                    "informational": res.informational,
                    "sessions": n,
                    "rs_percentile": (res.details or {}).get("rs_percentile"),
                    "signals": ",".join(sorted(live)),
                    "momentum_hash": h,
                }
            )
        if on_progress:
            on_progress(f"{period}: {len(eligible)} eligible")
    fresh = pd.DataFrame(rows, columns=PANEL_COLUMNS)
    both = [f for f in (kept, fresh) if len(f)]
    out = pd.concat(both, ignore_index=True) if both else pd.DataFrame(columns=PANEL_COLUMNS)
    return out.sort_values(["asof", "isin"]).reset_index(drop=True)


def save_panel(panel: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(path, index=False)


def load_panel(path: Path) -> pd.DataFrame | None:
    return pd.read_parquet(path) if path.exists() else None
