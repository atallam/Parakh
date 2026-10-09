"""Segment summary view model (F10, basic): one cap segment, one month, ranked and flagged.

Holdings lead (UX-04), then opportunities, then the full ranked table. Holdings carry XIRR against
the cap benchmark and the worst drawdown in the chart window; the portfolio block adds HHI and the
top-5 share. All use the weights of the holdings that have a loaded price and say so (plan 05 §4).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from parakh.configs.lens_models import OverridesConfig, PortfolioConfig, VerdictPolicy
from parakh.policy.overrides import nearing_expiry
from parakh.services.reports import chip, verdict_label
from parakh.services.risk import holding_returns, portfolio_risk, stock_drawdown

BUY_SET = {"STRONG_BUY", "BUY", "ACCUMULATE"}
ACTION_WORDS = {"TRIM", "EXIT"}


def _key(v: str) -> str:
    return v.upper().replace(" ", "_")


def _combined(s: dict[str, Any]) -> float:
    vals = [x for x in (s["value"].get("score"), s["momentum"].get("score")) if x is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _delta(cur: dict[str, Any], prev: dict[str, Any] | None, lens: str) -> float | None:
    if not prev or cur[lens].get("score") is None or prev[lens].get("score") is None:
        return None
    return round(cur[lens]["score"] - prev[lens]["score"], 1)


def row(s: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    v, pos = s["verdict"], s.get("position") or {}
    flags: list[str] = []
    if v.get("action") in ACTION_WORDS:
        flags.append(f"action: {v['action']}")
    if s["thesis"].get("status") in ("WATCH", "BROKEN"):
        flags.append(f"thesis {s['thesis']['status']}")
    if v.get("vetoes"):
        flags.append("veto")
    if s["thesis"].get("review_due"):
        flags.append("thesis review due")
    return {
        "symbol": s["symbol"],
        "name": s["name"],
        "isin": s["isin"],
        "sector": s.get("sector"),
        "owned": bool(v.get("owned")),
        "verdict": v["verdict"],
        "verdict_label": verdict_label(v["verdict"], v.get("action")),
        "chip": chip(v, prev),
        "changed": bool(v.get("changed")),
        "prev_verdict": v.get("prev_verdict"),
        "confidence": v["confidence"],
        "value": s["value"].get("score"),
        "value_delta": _delta(s, prev, "value"),
        "momentum": s["momentum"].get("score"),
        "momentum_delta": _delta(s, prev, "momentum"),
        "thesis": s["thesis"].get("status"),
        "weight_pct": pos.get("weight_pct"),
        "pnl_pct": pos.get("pnl_pct"),
        "days_to_long_term": pos.get("days_to_long_term"),
        "flags": flags,
        "limited_history": v.get("label"),
        "signals": list(s["momentum"].get("signals") or []),
        "red_flags": [c["name"] for c in s.get("checks", []) if c["state"] == "FLAGGED"],
        "unknown_checks": sum(1 for c in s.get("checks", []) if c["state"] == "UNKNOWN"),
        "driver": (v.get("drivers") or [{}])[0].get("text"),
        "combined": round(_combined(s), 1),
        "drawdown_pct": None if (d := stock_drawdown(s)) is None else round(d, 1),
        **holding_returns(s),
    }


def concentration(rows: list[dict[str, Any]], pf: PortfolioConfig) -> list[str]:
    out = []
    by_sector: dict[str, float] = defaultdict(float)
    for r in rows:
        w = r["weight_pct"]
        if w is None:
            continue
        if w > pf.single_stock_max_weight_pct:
            out.append(
                f"{r['symbol']} is {w:.1f}% of holdings, above the {pf.single_stock_max_weight_pct:g}% single-stock limit."
            )
        by_sector[r["sector"] or "Unclassified"] += w
    for sec, w in by_sector.items():
        if w > pf.sector_max_weight_pct:
            out.append(
                f"{sec} is {w:.1f}% of holdings, above the {pf.sector_max_weight_pct:g}% sector limit."
            )
    return out


def segment_view(
    cap: str,
    period: str,
    snaps: list[dict[str, Any]],
    prevs: dict[str, dict[str, Any] | None],
    regime: dict[str, Any],
    regime_history: list[dict[str, str]],
    policy: VerdictPolicy,
    portfolio: PortfolioConfig,
    overrides: OverridesConfig,
    asof: dt.date,
) -> dict[str, Any]:
    order = {v: i for i, v in enumerate(policy.verdict_order)}
    rows = [row(s, prevs.get(s["isin"])) for s in snaps]
    rows.sort(key=lambda r: (order.get(_key(r["verdict"]), 99), -r["combined"], r["symbol"]))
    held = [r for r in rows if r["owned"]]
    needs_action = [r for r in held if r["flags"]]
    ideas = [r for r in rows if not r["owned"] and _key(r["verdict"]) in BUY_SET][:5]
    weakest = sorted(held, key=lambda r: r["combined"])[:3]
    changes = [r for r in rows if r["changed"]]
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["verdict_label"]] += 1
    return {
        "cap": cap,
        "period": period,
        "asof": asof.isoformat(),
        "stocks": len(rows),
        "regime": regime,
        "regime_history": regime_history[-12:],
        "counts": dict(counts),
        "holdings": held,
        "needs_action": needs_action,
        "ideas": ideas,
        "weakest": weakest,
        "changes": changes,
        "ranked": rows,
        "red_flags": [r for r in rows if r["red_flags"] or r["flags"]],
        "new_signals": [r for r in rows if r["signals"]],
        "concentration": concentration(held, portfolio),
        "portfolio_risk": portfolio_risk(held),
        "weight_basis": next(
            (s["position"]["weight_basis"] for s in snaps if s.get("position")), None
        ),
        "overrides_active": [
            o.model_dump(mode="json")
            for o in overrides.overrides
            if o.set_on <= asof <= o.expires_on
        ],
        "overrides_expiring": [o.model_dump(mode="json") for o in nearing_expiry(overrides, asof)],
        "framework": snaps[0]["framework"] if snaps else None,
        "pending": [
            "correlation clusters need a constituent price history the pilot does not load yet",
            "the framework scorecard (hit rate of past calls) arrives in Phase 5",
        ],
    }
