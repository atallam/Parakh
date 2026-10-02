"""Turn snapshots into the files you read: reports, charts, history, segment summaries (F09, F10).

Everything is rendered from the snapshots on disk, so it can be re-run for any month without
touching data, and re-running replaces that month's files rather than adding copies (AC-F09.2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from parakh.configs import ConfigBundle
from parakh.render.charts import price_chart, score_chart
from parakh.render.report import render_report
from parakh.render.segment import write_segment
from parakh.services.segment import segment_view
from parakh.snapshots.history import score_series, write_history
from parakh.snapshots.store import (
    all_stock_dirs,
    cap_dir,
    load_previous,
    periods_for,
    read_snapshot_dict,
    snapshot_path,
    stock_dir,
)


def render_stock(
    bundle: ConfigBundle, snap: dict[str, Any], out_root: Path | None = None
) -> list[Path]:
    cap, sym, period = snap["cap"], snap["symbol"], snap["period"]
    prev = load_previous(cap, sym, period, out_root)
    folder = stock_dir(cap, sym, out_root)
    written: list[Path] = []
    avg_cost = (snap.get("position") or {}).get("avg_cost_inr")
    charts: dict[str, str] = {}
    p = price_chart(snap, folder / "charts" / f"{period}-price.png", avg_cost)
    if p:
        written.append(p)
        charts["price"] = f"../charts/{p.name}"
    write_history(cap, sym, out_root)
    sc = score_chart(
        sym,
        score_series(cap, sym, out_root),
        bundle.verdict_policy,
        folder / "charts" / f"{period}-scores.png",
    )
    if sc:
        written.append(sc)
        charts["score"] = f"../charts/{sc.name}"
    report = folder / "reports" / f"{period}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        render_report(snap, prev, charts, bundle.portfolio.near_ltcg_days), encoding="utf-8"
    )
    written += [report, folder / "history.csv", folder / "HISTORY.md"]
    return written


def render_segment(
    bundle: ConfigBundle,
    cap: str,
    period: str,
    regime: dict[str, Any] | None = None,
    out_root: Path | None = None,
) -> list[Path]:
    snaps, prevs, hist = [], {}, {}
    for d in all_stock_dirs(cap, out_root):
        sym = d.name
        s = read_snapshot_dict(snapshot_path(cap, sym, period, out_root))
        for p in periods_for(cap, sym, out_root):
            h = read_snapshot_dict(snapshot_path(cap, sym, p, out_root))
            if h:
                hist.setdefault(p, h["regime"]["regime"])
        if s:
            snaps.append(s)
            prevs[s["isin"]] = load_previous(cap, sym, period, out_root)
    if not snaps:
        return []
    asof = dt.date.fromisoformat(snaps[0]["asof"])
    view = segment_view(
        cap,
        period,
        snaps,
        prevs,
        regime or snaps[0]["regime"],
        [{"period": p, "regime": r} for p, r in sorted(hist.items()) if p <= period],
        bundle.verdict_policy,
        bundle.portfolio,
        bundle.overrides,
        asof,
    )
    return write_segment(view, cap_dir(cap, out_root) / "_SEGMENT_SUMMARY")


def render_month(
    bundle: ConfigBundle, snaps: list[dict[str, Any]], out_root: Path | None = None
) -> list[Path]:
    out: list[Path] = []
    for s in snaps:
        out += render_stock(bundle, s, out_root)
    for cap, period in sorted({(s["cap"], s["period"]) for s in snaps}):
        out += render_segment(bundle, cap, period, None, out_root)
    return out
