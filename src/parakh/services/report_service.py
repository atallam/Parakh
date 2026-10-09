"""Read access to snapshots for the CLI and MCP tools (plan 15 §4.2). No writes, no recompute.

Everything returned is a view of a snapshot already on disk, with positions masked to weight
and P&L percentages (UX-11). The same functions back `parakh show/explain` and the MCP tools,
so the two can't disagree (AG-04, AC-F24.2).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from parakh import __version__
from parakh.configs import load_all
from parakh.configs.models import Security
from parakh.registry import REGISTRY, discover
from parakh.services.explain import explain_verdict, render_tree
from parakh.services.reports import fired_signals, stock_view
from parakh.services.view_models import (
    CatalogueLookup,
    ChangeItem,
    ExplainLookup,
    HistoryLookup,
    SegmentLookup,
    Stamp,
    StockLookup,
    WhatChanged,
)
from parakh.snapshots.store import (
    all_stock_dirs,
    cap_dir,
    load_previous,
    periods_for,
    read_snapshot_dict,
    snapshot_path,
    stock_dir,
)

MAX_ROWS = 25


def _stamp(snap: dict[str, Any] | None = None) -> Stamp:
    return Stamp(
        asof=None if snap is None else snap["asof"],
        run_id=None if snap is None else snap["run_id"],
        framework_version=__version__ if snap is None else snap["framework"]["version"],
    )


def mask_position(pos: dict[str, Any] | None) -> dict[str, Any] | None:
    """Weight and percentages only: no quantity, cost, ₹ value, ₹ P&L or ₹ tax."""
    if not pos:
        return None
    keep = (
        "weight_pct",
        "weight_basis",
        "pnl_pct",
        "xirr_pct",
        "benchmark_xirr_pct",
        "cost_pending",
        "days_to_long_term",
        "lots",
        "lots_long_term",
        "tax_note",
    )
    return {k: pos.get(k) for k in keep}


def resolve(symbol_or_isin: str, root: Path | None = None) -> Security | None:
    key = symbol_or_isin.strip().upper()
    return next(
        (s for s in load_all().universe.active if key in (s.symbol.upper(), s.isin.upper())), None
    )


def _load(symbol_or_isin: str, period: str | None, root: Path | None):  # type: ignore[no-untyped-def]
    sec = resolve(symbol_or_isin, root)
    if sec is None:
        return None, None, None, f"{symbol_or_isin} is not in the pilot universe."
    periods = periods_for(sec.cap, sec.symbol, root)
    if not periods:
        return (
            sec,
            None,
            None,
            f"No snapshots for {sec.symbol} yet. Run `parakh run --mode monthly`.",
        )
    p = period or periods[-1]
    snap = read_snapshot_dict(snapshot_path(sec.cap, sec.symbol, p, root))
    if snap is None:
        return (
            sec,
            None,
            None,
            f"No snapshot for {sec.symbol} {p}. Available: {', '.join(periods)}.",
        )
    return sec, snap, load_previous(sec.cap, sec.symbol, p, root), ""


def _score_delta(cur: dict[str, Any], prev: dict[str, Any] | None) -> float | None:
    if not prev or cur.get("score") is None or prev.get("score") is None:
        return None
    return round(float(cur["score"]) - float(prev["score"]), 1)


def get_stock(
    symbol_or_isin: str, period: str | None = None, root: Path | None = None
) -> StockLookup:
    sec, snap, prev, msg = _load(symbol_or_isin, period, root)
    if snap is None:
        return StockLookup(stamp=_stamp(), found=False, message=msg)
    view = stock_view(snap, prev)
    view["position_line"] = (
        view["position_line"] if not snap.get("position") else _masked_line(snap)
    )
    view["scores"] = {
        "value": {
            "score": snap["value"]["score"],
            "view": snap["value"]["view"],
            "confidence": snap["value"]["confidence"],
            "informational": snap["value"]["informational"],
            "delta": _score_delta(snap["value"], (prev or {}).get("value")),
        },
        "momentum": {
            "score": snap["momentum"]["score"],
            "view": snap["momentum"]["view"],
            "confidence": snap["momentum"]["confidence"],
            "informational": snap["momentum"]["informational"],
            "delta": _score_delta(snap["momentum"], (prev or {}).get("momentum")),
        },
    }
    view["verdict"] = {
        k: snap["verdict"].get(k)
        for k in (
            "verdict",
            "action",
            "qualifier",
            "label",
            "rule_id",
            "vetoes",
            "drivers",
            "changed",
            "prev_verdict",
        )
    }
    view["regime"] = snap["regime"]["regime"]
    view["thesis"] = {
        "status": snap["thesis"].get("status"),
        "source": snap["thesis"].get("status_source"),
        "review_due": snap["thesis"].get("review_due"),
    }
    view["position"] = mask_position(snap.get("position"))
    view["action_box"].pop("tax_if_sold_now_inr", None)
    view["data_confidence"] = snap["data_quality"].get("confidence")
    assert sec is not None  # snap loaded, so the stock resolved
    view["report_path"] = f"{sec.cap}_cap/{sec.symbol}/reports/{snap['period']}.md"
    return StockLookup(
        stamp=_stamp(snap), found=True, symbol=sec.symbol, period=snap["period"], view=view
    )


def _masked_line(snap: dict[str, Any]) -> str:
    from parakh.services.reports import position_line

    return position_line(snap.get("position"), masked=True)


def what_changed(
    period: str | None = None, cap: str | None = None, root: Path | None = None
) -> WhatChanged:
    bundle = load_all()
    caps = [cap] if cap else sorted({s.cap for s in bundle.universe.active})
    snaps: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for c in caps:
        for d in all_stock_dirs(c, root):
            periods = periods_for(c, d.name, root)
            p = period or (periods[-1] if periods else None)
            s = read_snapshot_dict(snapshot_path(c, d.name, p, root)) if p else None
            if s:
                snaps.append((s, load_previous(c, d.name, s["period"], root)))
    if not snaps:
        return WhatChanged(
            stamp=_stamp(),
            found=False,
            message="No snapshots found. Run `parakh run --mode monthly`.",
        )
    items: list[ChangeItem] = []
    for s, prev in snaps:
        v, owned = s["verdict"], bool(s["verdict"]["owned"])
        if v.get("changed"):
            d = "; ".join(x["text"] for x in v.get("drivers", [])[:3])
            items.append(
                ChangeItem(
                    symbol=s["symbol"],
                    owned=owned,
                    kind="verdict",
                    text=f"{v.get('prev_verdict')} → {v['verdict']}" + (f" ({d})" if d else ""),
                )
            )
        if s["thesis"].get("changed_from"):
            items.append(
                ChangeItem(
                    symbol=s["symbol"],
                    owned=owned,
                    kind="thesis",
                    text=f"thesis {s['thesis']['changed_from']} → {s['thesis']['status']}",
                )
            )
        for sig in fired_signals(s):
            items.append(
                ChangeItem(
                    symbol=s["symbol"],
                    owned=owned,
                    kind="signal",
                    text=f"{sig['id']} {sig['name']}",
                )
            )
        for c in s.get("checks", []):
            if c["state"] == "FLAGGED":
                items.append(
                    ChangeItem(symbol=s["symbol"], owned=owned, kind="red_flag", text=c["name"])
                )
        if prev and prev["regime"]["regime"] != s["regime"]["regime"]:
            items.append(
                ChangeItem(
                    symbol=s["symbol"],
                    owned=owned,
                    kind="regime",
                    text=f"{prev['regime']['regime']} → {s['regime']['regime']}",
                )
            )
    items.sort(key=lambda i: (not i.owned, i.symbol, i.kind))  # owned first (UX-04)
    return WhatChanged(
        stamp=_stamp(snaps[0][0]), found=True, period=snaps[0][0]["period"], items=items
    )


def segment_summary(cap: str, period: str | None = None, root: Path | None = None) -> SegmentLookup:
    folder = cap_dir(cap, root) / "_SEGMENT_SUMMARY"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if not files:
        return SegmentLookup(
            stamp=_stamp(), found=False, message=f"No segment summary for {cap} cap yet."
        )
    path = folder / f"{period}.json" if period else files[-1]
    if not path.exists():
        return SegmentLookup(
            stamp=_stamp(),
            found=False,
            message=f"No {cap} summary for {period}; have {', '.join(p.stem for p in files)}.",
        )
    v = json.loads(path.read_text(encoding="utf-8"))
    ranked = v["ranked"]
    for r in ranked:
        r.pop("isin", None)
    out = {
        k: v[k]
        for k in (
            "cap",
            "period",
            "asof",
            "stocks",
            "regime",
            "regime_history",
            "counts",
            "concentration",
            "pending",
        )
    }
    if "portfolio_risk" in v:
        out["portfolio_risk"] = v["portfolio_risk"]  # percentages and ratios only
    out["ranked"] = ranked[:MAX_ROWS]
    out["holdings"] = [r["symbol"] for r in v["holdings"]]
    out["needs_action"] = [{"symbol": r["symbol"], "flags": r["flags"]} for r in v["needs_action"]]
    out["changes"] = [{"symbol": r["symbol"], "chip": r["chip"]} for r in v["changes"]]
    return SegmentLookup(
        stamp=Stamp(
            asof=v["asof"],
            run_id=None,
            framework_version=(v.get("framework") or {}).get("version", __version__),
        ),
        found=True,
        cap=cap,
        period=v["period"],
        summary=out,
        truncated=len(ranked) > MAX_ROWS,
    )


def private_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """A copy safe to hand to Claude: the position keeps weight and percentages only."""
    import copy

    out = copy.deepcopy(snap)
    out["position"] = mask_position(out.get("position"))
    return out


def masked_snapshot_json(
    symbol_or_isin: str, period: str | None = None, root: Path | None = None
) -> str:
    _, snap, _, msg = _load(symbol_or_isin, period, root)
    return msg if snap is None else json.dumps(private_snapshot(snap), indent=2, ensure_ascii=False)


def report_markdown(
    symbol_or_isin: str, period: str | None = None, root: Path | None = None
) -> str:
    from parakh.render.report import render_report

    _, snap, prev, msg = _load(symbol_or_isin, period, root)
    if snap is None:
        return msg
    prev_masked = private_snapshot(prev) if prev else None
    return render_report(
        private_snapshot(snap), prev_masked, None, load_all().portfolio.near_ltcg_days
    )


def segment_markdown(cap: str, period: str | None = None, root: Path | None = None) -> str:
    folder = cap_dir(cap, root) / "_SEGMENT_SUMMARY"
    files = sorted(folder.glob("*.md")) if folder.exists() else []
    if not files:
        return f"No segment summary for {cap} cap yet."
    path = folder / f"{period}.md" if period else files[-1]
    return path.read_text(encoding="utf-8") if path.exists() else f"No {cap} summary for {period}."


def plan_doc(doc: str) -> str:
    import re

    from parakh.config import REPO_ROOT

    if not re.fullmatch(r"[A-Za-z0-9_\-]+(\.md)?", doc):
        return "Plan document names are letters, digits, underscore and hyphen only."
    name = doc if doc.endswith(".md") else doc + ".md"
    path = REPO_ROOT / "docs" / "plan" / name
    return path.read_text(encoding="utf-8") if path.exists() else f"No plan document {name}."


def get_history(
    symbol_or_isin: str,
    metrics: list[str] | None = None,
    months: int = 12,
    root: Path | None = None,
) -> HistoryLookup:
    sec = resolve(symbol_or_isin, root)
    if sec is None:
        return HistoryLookup(
            stamp=_stamp(), found=False, message=f"{symbol_or_isin} is not in the pilot universe."
        )
    path = stock_dir(sec.cap, sec.symbol, root) / "history.csv"
    if not path.exists():
        return HistoryLookup(
            stamp=_stamp(), found=False, symbol=sec.symbol, message="No history yet."
        )
    rows = list(csv.DictReader(path.open(encoding="utf-8")))[-max(1, months) :]
    cols = list(rows[0].keys()) if rows else []
    if metrics:
        unknown = [m for m in metrics if m not in cols]
        if unknown:
            return HistoryLookup(
                stamp=_stamp(),
                found=False,
                symbol=sec.symbol,
                message=f"Unknown columns {unknown}; available: {cols}",
            )
        cols = ["period", *[m for m in metrics if m != "period"]]
        rows = [{c: r[c] for c in cols} for r in rows]
    return HistoryLookup(stamp=_stamp(), found=True, symbol=sec.symbol, columns=cols, rows=rows)


def explain(
    symbol_or_isin: str, period: str | None = None, root: Path | None = None
) -> ExplainLookup:
    sec, snap, prev, msg = _load(symbol_or_isin, period, root)
    if snap is None:
        return ExplainLookup(stamp=_stamp(), found=False, message=msg)
    tree = explain_verdict(snap, prev)
    return ExplainLookup(stamp=_stamp(snap), found=True, tree=tree, text=render_tree(tree))


def list_catalogue(kind: str) -> CatalogueLookup:
    reg = discover()
    items: list[dict[str, Any]]
    match kind:
        case "metric":
            items = [
                {
                    "id": m.id,
                    "unit": m.unit,
                    "inputs": m.inputs,
                    "used_by": m.used_by,
                    "summary": (m.doc.strip().splitlines() or [""])[0],
                }
                for m in sorted(reg.metrics.values(), key=lambda x: x.id)
            ]
        case "signal":
            items = [
                {
                    "id": s.id,
                    "name": s.name,
                    "lens": s.lens,
                    "severity": s.severity,
                    "summary": (s.doc.strip().splitlines() or [""])[0],
                }
                for s in sorted(reg.signals.values(), key=lambda x: x.id)
            ]
        case "rule":
            items = [
                {"id": r.id, "kind": r.kind, "summary": (r.doc.strip().splitlines() or [""])[0]}
                for r in sorted(reg.rules.values(), key=lambda x: x.id)
            ]
        case "lens":
            items = [{"id": k, "version": v.lens_version} for k, v in sorted(reg.lenses.items())]
        case _:
            items = []
    return CatalogueLookup(stamp=_stamp(), kind=kind, items=items)


__all__ = [
    "REGISTRY",
    "explain",
    "get_history",
    "get_stock",
    "list_catalogue",
    "segment_summary",
    "what_changed",
]
