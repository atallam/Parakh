"""Render a snapshot to the monthly Markdown report (F09; plan 00 §8, plan 12 §7).

    text = render_report(snapshot, prev=None, charts={"price": "../charts/2026-09-price.png"})

The report opens with the TL;DR, the verdict chip (prev → now), at most four "what changed"
bullets and the action box. Sections 4–15 fold inside `<details>`. A section with no data says
"N/A" and why (AC-F09.1); a check that could not run says ❔ UNKNOWN, never clean (AC-F09.7).
Derived text comes from `services.reports`, so the CLI, the MCP tools and this report agree.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

import jinja2

from parakh.registry import REGISTRY, discover
from parakh.render import format as fmt
from parakh.render.tokens import label, status
from parakh.services import reports as svc

TEMPLATE_DIR = Path(__file__).parent / "templates"
SECTION_TITLES = [
    "0. TL;DR", "1. Verdict, what changed & why", "2. Action box", "3. Bull / Base / Bear cases",
    "4. Value scorecard", "5. Momentum scorecard", "6. Earnings & concall tracker",
    "7. Peer comparison", "8. Ownership & smart money", "9. Qualitative view", "10. Thesis check",
    "11. Time-series view & charts", "12. Upcoming events & catalysts",
    "13. Red flags, risks & watch items", "14. Data quality & sources", "15. Methodology & disclaimer",
]  # fmt: skip

ACRONYMS = {
    "cagr": "CAGR", "eps": "EPS", "dma": "DMA", "dma200": "200-DMA", "rs": "RS", "obv": "OBV", "mom": "momentum",
    "pct": "%", "vol": "volatility", "adj": "adjusted", "mcap": "market cap", "roe": "ROE", "roce": "ROCE",
    "pb": "P/B", "roa": "ROA", "nim": "NIM", "gnpa": "GNPA", "nnpa": "NNPA", "avg": "average", "abv": "ABV",
    "ev": "EV", "cfo": "CFO", "ebitda": "EBITDA", "ebitdar": "EBITDAR", "pe": "P/E", "fii": "FII", "dii": "DII",
    "52w": "52-week", "12m": "12-month", "6m": "6-month", "3y": "3-year", "5y": "5-year", "50d": "50-day",
    "1m": "1-month", "3m": "3-month", "12": "12", "1": "1",
}  # fmt: skip
PLAIN_NUMBERS = {
    "vol_adj_12m",
    "vol_adj_6m",
    "mansfield_rs",
    "earnings_accel",
}  # ratios of return to risk, not percentages
PRETTY = {
    "mom_12_1": "12-month momentum, skipping the latest month",
    "pe_normalised": "P/E on normalised earnings", "roe_5y_avg": "ROE, 5-year average",
    "cfo_to_ebitda_3y": "Cash conversion (CFO/EBITDA, 3y)", "op_margin_trend_pp": "Operating-margin trend",
    "net_cash_to_mcap": "Net cash / market cap", "pledge_pct": "Promoter pledge",
    "promoter_holding": "Promoter holding", "promoter_trend_pp": "Promoter holding, 1y change",
    "fii_trend_pp": "FII holding, 1y change", "dii_trend_pp": "DII holding, 1y change",
    "dilution_3y": "Share dilution, 3y",
}  # fmt: skip


def metric_label(mid: str) -> str:
    key = mid.rsplit(".", 1)[-1]
    if key in PRETTY:
        return PRETTY[key]
    words = [ACRONYMS.get(w, w) for w in key.split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def fmt_value(mid: str, v: Any) -> str:
    """Format by the registry unit so a ratio and a percentage can never be mixed."""
    discover()
    if v is None:
        return "N/A"
    if isinstance(v, bool):
        return "yes" if v else "no"
    spec = REGISTRY.metrics.get(mid)
    unit = spec.unit if spec else None
    if mid.endswith("_pp") and isinstance(v, int | float):
        return fmt.pp(v)
    if mid.rsplit(".", 1)[-1] in PLAIN_NUMBERS and isinstance(v, int | float):
        return f"{v:,.2f}".replace("-", fmt.MINUS)
    if not isinstance(v, int | float):
        return str(v)
    match unit:
        case "ratio":
            return fmt.ratio_pct(v)
        case "pct":
            return fmt.pct(v)
        case "x":
            return fmt.mult(v)
        case "cr":
            return f"₹{v:,.0f} cr"
        case "inr":
            return fmt.inr(v, decimals=2)
        case "days":
            return f"{v:,.0f} days"
        case "bps":
            return f"{v:,.0f} bps"
        case _:
            return f"{v:,.2f}".rstrip("0").rstrip(".")


def _computed_from(mid: str) -> str:
    return "fundamentals (quarterly results)" if mid.endswith("earnings_accel") else "price history"


def _scorecard(lens: dict[str, Any], title: str) -> str:
    d = lens.get("details") or {}
    metrics = d.get("metrics") or {}
    values = d.get("metric_values") or {k: m.get("value") for k, m in metrics.items()}
    sub = d.get("metric_sub") or {}
    weights = d.get("weights") or {}
    rows = [f"| {title} sub-score | Weight | Score | Metrics |", "|---|---|---|---|"]
    for name, sc in (lens.get("subscores") or {}).items():
        used = ", ".join(metric_label(m) for m, s in sub.items() if s == name) or "—"
        rows.append(
            f"| {name.replace('_', ' ')} | {weights.get(name, 0):g}% | {sc * 100:.0f} | {used} |"
        )
    miss = d.get("subscore_missing") or {}
    for name in miss:
        if name not in (lens.get("subscores") or {}):
            rows.append(
                f"| {name.replace('_', ' ')} | {weights.get(name, 0):g}% | N/A | all inputs missing |"
            )
    rows += ["", "| Metric | Value | Source · as of |", "|---|---|---|"]
    for mid in sorted(values):
        src = metrics.get(mid, {})
        rows.append(
            f"| {metric_label(mid)} (`{mid}`) | {fmt_value(mid, values[mid])} | "
            + (f"{src.get('source', '—')} · {src.get('asof', '—')}" if src else _computed_from(mid))
            + " |"
        )
    return "\n".join(rows)


def _ownership(s: dict[str, Any]) -> str:
    m = (s["value"].get("details") or {}).get("metrics") or {}
    want = [
        "MET.value.promoter_holding",
        "MET.value.promoter_trend_pp",
        "MET.value.pledge_pct",
        "MET.value.fii_trend_pp",
        "MET.value.dii_trend_pp",
    ]
    rows = ["| Measure | Value | As of |", "|---|---|---|"]
    for mid in want:
        if mid in m:
            rows.append(
                f"| {metric_label(mid)} | {fmt_value(mid, m[mid]['value'])} | {m[mid].get('asof', '—')} |"
            )
    if len(rows) == 2:
        return "N/A: no shareholding pattern visible at the as-of date."
    rows += [
        "",
        "Mutual-fund scheme counts, insider trades and bulk/block deals arrive with Phase 3 (❔ not loaded, not zero).",
    ]
    return "\n".join(rows)


def _thesis_block(th: dict[str, Any]) -> str:
    if th.get("banner") and not th.get("original"):
        return (
            th["banner"]
            if th.get("present")
            else "⚪ NOT SET: no THESIS.md for this stock. Add one to turn on the exit checks (`parakh thesis validate`)."
        )
    out = []
    if th.get("original"):
        out.append(
            f"**Original thesis ({th['original']['written_on']}):** {th['original']['statement']}"
        )
    out.append(
        f"\nStatus: **{th['status']}** — {th.get('status_source', '')}. Checked {th.get('checked', 0)}, unchecked {th.get('unchecked', 0)}."
    )
    if th.get("review_due"):
        out.append(f"\n⚠️ Review was due by {th.get('review_by')}.")
    if th.get("breakers"):
        out += ["", "| Sell if… | Check | State | Detail |", "|---|---|---|---|"]
        for b in th["breakers"]:
            st = label(status("check", b["state"]))
            detail = b.get("reason") or (
                ", ".join(f"{k}={v}" for k, v in (b.get("evidence") or {}).items())
            )
            out.append(f"| {b['id']}: {b['text']} | {b['check']} | {st} | {detail} |")
    if th.get("key_metrics"):
        out += ["", "| Watch | State | Detail |", "|---|---|---|"]
        for k in th["key_metrics"]:
            out.append(
                f"| {k['id']}: {k['text']} | {label(status('check', k['state']))} | {k.get('reason', '')} |"
            )
    return "\n".join(out)


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        autoescape=False,
    )


def render_report(
    snap: dict[str, Any],
    prev: dict[str, Any] | None = None,
    charts: dict[str, str] | None = None,
    near_ltcg_days: int = svc.NEAR_LTCG_DAYS,
) -> str:
    s = snap
    v = svc.stock_view(s, prev, near_ltcg_days)
    vd = s["value"].get("details") or {}
    md = s["momentum"].get("details") or {}
    irr = vd.get("expected_irr") or {}
    methods = (vd.get("intrinsic_value") or {}).get("methods") or {}
    fa = s["fundamentals_asof"]
    fund_asof = fa.get("quarter") or fa.get("annual") or "N/A"
    pos = s.get("position")
    if pos and "tax_if_sold_now_inr" not in pos:
        tax_line = "hidden in this masked view"
    elif pos and pos.get("tax_if_sold_now_inr") is not None:
        tax_line = f"{fmt.inr(pos['tax_if_sold_now_inr'])} ({pos['tax_note']})"
    elif pos:
        tax_line = pos.get("tax_note") or "cost pending: tax cannot be estimated"
    else:
        tax_line = "N/A (not held)"
    fired = ", ".join(f"{x['id']} {x['name']}" for x in svc.fired_signals(s)) or "none this month"
    cannot = [
        x["id"] for x in (md.get("active_signals") or []) if x.get("status") == "cannot_evaluate"
    ]
    if cannot:
        fired += f". ❔ Could not evaluate (inputs not loaded): {', '.join(cannot)}"
    checks = v["checks"]
    nflag, nunk = (
        sum(c["state"] == "FLAGGED" for c in checks),
        sum(c["state"] == "UNKNOWN" for c in checks),
    )
    ctx = {
        "s": s,
        "v": v,
        "a": v["action_box"],
        "vd": vd,
        "md": md,
        "irr": irr,
        "month_label": dt.date.fromisoformat(s["asof"]).strftime("%b %Y"),
        "verdict_plain": s["verdict"]["verdict"]
        + (f" ({s['verdict']['qualifier']})" if s["verdict"].get("qualifier") else ""),
        "fund_asof": fund_asof,
        "tax_line": tax_line,
        "methods": ", ".join(
            f"{k.replace('_', ' ')} {fmt.inr(x, decimals=0)}" for k, x in methods.items()
        )
        or "N/A",
        "value_table": _scorecard(s["value"], "Value"),
        "momentum_table": _scorecard(s["momentum"], "Momentum"),
        "tt": md.get("trend_template") or {"passed": 0, "computable": 0, "of": 8},
        "gate": md.get("strong_gate") or {"passed": False, "failed": []},
        "fired": fired,
        "ownership_table": _ownership(s),
        "thesis_block": _thesis_block(s["thesis"]),
        "thesis_pill": label(status("thesis", s["thesis"].get("status") or "NOT_SET")),
        "price_png": (charts or {}).get("price"),
        "score_png": (charts or {}).get("score"),
        "price_only_note": "In months with no new results, valuation moves come from price alone."
        if fa.get("quarter")
        else "",
        "flag_summary": f"{nflag} flagged · {nunk} could not be checked",
        "lineage_sources": ", ".join((s["lineage"].get("fundamentals") or {}).get("sources") or [])
        or "N/A",
        "lens_versions": ", ".join(f"{k} {x}" for k, x in s["framework"]["lens_versions"].items()),
        "disclaimer": svc.DISCLAIMER,
        "inr": lambda x, d=0: fmt.inr(x, decimals=d),
        "ratio": lambda x: "N/A" if x is None else fmt.ratio_pct(x),
    }
    text = _env().get_template("stock_report.md.j2").render(**ctx)
    return re.sub(r"\n{3,}", "\n\n", text)
