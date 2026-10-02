"""Verdict lineage: verdict → policy rule → lens versions → sub-scores → metrics → source, as-of
and raw hash (plan 10 §6; AC-F21.5). Arithmetic over one snapshot; nothing is recomputed.

    tree = explain_verdict(snapshot)
    print(render_tree(tree))
"""

from __future__ import annotations

from typing import Any

from parakh.render.report import fmt_value, metric_label
from parakh.services.reports import chip, verdict_label


def _lens_node(name: str, lens: dict[str, Any], band: str | None) -> dict[str, Any]:
    d = lens.get("details") or {}
    metrics = d.get("metrics") or {}
    values = d.get("metric_values") or {k: m.get("value") for k, m in metrics.items()}
    sub = d.get("metric_sub") or {}
    weights = d.get("weights") or {}
    children = []
    for sname, sc in (lens.get("subscores") or {}).items():
        mnodes = []
        for mid, ssub in sorted(sub.items()):
            if ssub != sname or mid not in values:
                continue
            src = metrics.get(mid, {})
            mnodes.append(
                {
                    "id": mid,
                    "label": metric_label(mid),
                    "value": values[mid],
                    "shown": fmt_value(mid, values[mid]),
                    "source": src.get("source", "price history / derived"),
                    "asof": src.get("asof"),
                }
            )
        children.append(
            {
                "subscore": sname,
                "score": round(sc * 100, 1),
                "weight_pct": weights.get(sname),
                "metrics": mnodes,
            }
        )
    return {
        "lens": name,
        "version": lens["lens_version"],
        "score": lens.get("score"),
        "view": lens.get("view"),
        "band": band,
        "confidence": lens.get("confidence"),
        "informational": lens.get("informational"),
        "subscores": children,
        "not_available": lens.get("na") or {},
        "flags": lens.get("flags") or [],
        "vetoes": lens.get("vetoes") or [],
    }


def explain_verdict(snap: dict[str, Any], prev: dict[str, Any] | None = None) -> dict[str, Any]:
    v = snap["verdict"]
    return {
        "symbol": snap["symbol"],
        "isin": snap["isin"],
        "period": snap["period"],
        "asof": snap["asof"],
        "run_id": snap["run_id"],
        "verdict": {
            "verdict": v["verdict"],
            "headline": v["headline"],
            "chip": chip(v, prev),
            "confidence": v["confidence"],
            "label": v.get("label"),
        },
        "policy": {
            "version": v["policy_version"],
            "rule_id": v["rule_id"],
            "trail": v["trail"],
            "vetoes": v["vetoes"],
            "held_by_hysteresis": v["held_by_hysteresis"],
            "override": v.get("override"),
            "reasons": v.get("reasons", []),
        },
        "drivers": v.get("drivers", []),
        "lenses": [
            _lens_node("value", snap["value"], v.get("value_band")),
            _lens_node("momentum", snap["momentum"], v.get("momentum_band")),
        ],
        "regime": snap["regime"]["regime"],
        "thesis": {
            "status": snap["thesis"].get("status"),
            "source": snap["thesis"].get("status_source"),
        },
        "inputs": snap["lineage"],
        "framework": snap["framework"],
    }


def render_tree(t: dict[str, Any]) -> str:
    L = [
        f"{t['symbol']} · {t['period']} (as of {t['asof']}, run {t['run_id']})",
        f"└─ verdict: {t['verdict']['chip']} · confidence {t['verdict']['confidence']}"
        + (f" · {t['verdict']['label']}" if t["verdict"]["label"] else ""),
    ]
    p = t["policy"]
    L.append(f"   └─ policy {p['version']} · rule {p['rule_id']}")
    L.append(f"      trail: {' → '.join(p['trail'])}")
    for x in p["vetoes"]:
        L.append(f"      veto: {x}")
    if p["held_by_hysteresis"]:
        L.append(f"      held by hysteresis: {', '.join(p['held_by_hysteresis'])}")
    if p["override"]:
        L.append(f"      override: {p['override']}")
    for i, d in enumerate(t["drivers"], 1):
        L.append(f"      driver {i}: {d['text']}")
    for lens in t["lenses"]:
        L.append(
            f"      ├─ {lens['lens']} lens {lens['version']}: {'N/A' if lens['score'] is None else round(lens['score'])} → {lens['band']} ({lens['view']}, {lens['confidence']} confidence{', informational' if lens['informational'] else ''})"
        )
        for sub in lens["subscores"]:
            L.append(
                f"      │  ├─ {sub['subscore'].replace('_', ' ')} {sub['score']:.0f} (weight {sub['weight_pct']:g}%)"
                if sub["weight_pct"] is not None
                else f"      │  ├─ {sub['subscore']} {sub['score']:.0f}"
            )
            for m in sub["metrics"]:
                L.append(
                    f"      │  │  └─ {m['id']} = {m['shown']} · {m['source']}"
                    + (f" · as of {m['asof']}" if m["asof"] else "")
                )
        for mid, why in lens["not_available"].items():
            L.append(f"      │  └─ N/A {mid}: {why}")
    fr, inp = t["framework"], t["inputs"]
    pr = inp.get("prices") or {}
    L.append(
        f"      └─ inputs: prices {pr.get('rows', 0)} sessions {pr.get('first', '')}…{pr.get('last', '')} {pr.get('sha256', '')[:23]}"
    )
    f = inp.get("fundamentals") or {}
    L.append(
        f"         fundamentals {f.get('rows', 0)} rows from {', '.join(f.get('sources', [])) or 'N/A'}; runs {', '.join(f.get('runs', [])) or 'N/A'}"
    )
    L.append(
        f"         framework {fr['version']} · lenses {fr['lens_versions']} · weights {fr['weights_hash']} · config {fr['config_hash']} · code {fr['code_version']}"
    )
    return "\n".join(L)


__all__ = ["explain_verdict", "render_tree", "verdict_label"]
