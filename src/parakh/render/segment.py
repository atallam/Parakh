"""Segment summary files: `_SEGMENT_SUMMARY/YYYY-MM.{md,csv,xlsx,json}` (F10; plan 12 §7).

Stocks are linked as `[[SYMBOL]]` so the Obsidian graph and backlinks work over the report folder.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from parakh.render import format as fmt
from parakh.services.reports import DISCLAIMER

HEADERS = [
    "symbol",
    "name",
    "sector",
    "owned",
    "verdict",
    "confidence",
    "value",
    "value_delta",
    "momentum",
    "momentum_delta",
    "thesis",
    "weight_pct",
    "pnl_pct",
    "flags",
    "driver",
]


def _d(x: float | None) -> str:
    return (
        "—"
        if x is None
        else (
            "● 0" if x == 0 else (f"▲ {x:+.0f}" if x > 0 else f"▼ {x:+.0f}".replace("-", fmt.MINUS))
        )
    )


def _n(x: float | None) -> str:
    return "N/A" if x is None else f"{x:.0f}"


def _table(rows: list[dict[str, Any]]) -> list[str]:
    out = [
        "| Stock | Verdict | Conf | Value | Momentum | Thesis | Wt | P&L | Flags |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| [[{r['symbol']}]] | {r['chip'] if r['changed'] else r['verdict_label']}{' · ' + r['limited_history'] if r['limited_history'] else ''} | {r['confidence']} "
            f"| {_n(r['value'])} ({_d(r['value_delta'])}) | {_n(r['momentum'])} ({_d(r['momentum_delta'])}) | {r['thesis'] or '—'} "
            f"| {fmt.pct(r['weight_pct'], signed=False) if r['weight_pct'] is not None else '—'} "
            f"| {fmt.pct(r['pnl_pct']) if r['pnl_pct'] is not None else '—'} | {'; '.join(r['flags']) or '—'} |"
        )
    return out


def segment_md(v: dict[str, Any]) -> str:
    reg = v["regime"]
    L = [
        "---",
        f"segment: {v['cap']}_cap",
        f"period: {v['period']}",
        f"asof: {v['asof']}",
        f"stocks: {v['stocks']}",
        f"regime: {reg['regime']}",
        f"framework_version: {(v['framework'] or {}).get('version', 'N/A')}",
        "---",
        f"# {v['cap'].capitalize()} cap — {v['period']}",
        "",
        "## Segment regime",
        "",
        f"**{reg['regime']}**"
        + (
            f" · benchmark {fmt.ratio_pct(reg.get('benchmark_pct_vs_200dma'))} vs its 200 DMA"
            if reg.get("benchmark_pct_vs_200dma") is not None
            else ""
        ),
    ]
    L += [f"- {x}" for x in (reg.get("reasons") or []) + (reg.get("flags") or [])]
    if v["regime_history"]:
        L += [
            "",
            "Regime history: "
            + " → ".join(f"{h['period']} {h['regime']}" for h in v["regime_history"]),
        ]
    L += [
        "",
        "## Verdicts",
        "",
        ", ".join(f"{k}: {n}" for k, n in v["counts"].items()) or "No stocks.",
        "",
    ]
    L += ["## Holdings (owned first)", ""]
    if v["needs_action"]:
        L += [
            "**Needs your attention:** "
            + ", ".join(f"[[{r['symbol']}]] ({'; '.join(r['flags'])})" for r in v["needs_action"]),
            "",
        ]
    L += _table(v["holdings"]) if v["holdings"] else ["No holdings in this segment."]
    if v["concentration"]:
        L += ["", "**Concentration**", ""] + [f"- ⚠️ {c}" for c in v["concentration"]]
    if v.get("weight_basis"):
        L += ["", f"_Weights are shares of {v['weight_basis']}._"]
    L += ["", "## Best new ideas (not owned)", ""]
    L += (
        _table(v["ideas"])
        if v["ideas"]
        else ["None this month: no stock outside your holdings reaches BUY or better."]
    )
    L += ["", "## Weakest holdings", ""]
    L += _table(v["weakest"]) if v["weakest"] else ["None."]
    L += ["", "## Verdict changes", ""]
    L += [
        f"- [[{r['symbol']}]]: {r['chip']}" + (f" ({r['driver']})" if r["driver"] else "")
        for r in v["changes"]
    ] or ["No verdict changed this month."]
    L += ["", "## Active signals and red flags", ""]
    L += [f"- [[{r['symbol']}]] signals: {', '.join(r['signals'])}" for r in v["new_signals"]]
    L += [
        f"- [[{r['symbol']}]] flagged: {', '.join(r['red_flags'] + r['flags'])}"
        for r in v["red_flags"]
    ]
    if not v["new_signals"] and not v["red_flags"]:
        L += [
            "None. (Checks that could not run are listed per stock in the report, never counted as clean.)"
        ]
    L += ["", "## Overrides", ""]
    if not v["overrides_active"]:
        L += ["No active overrides."]
    for o in v["overrides_active"]:
        soon = any(e["id"] == o["id"] for e in v["overrides_expiring"])
        L += [
            f"- {o['isin']} · {o['field']} = {o['value']} until {o['expires_on']}{' ⏳ expiring within 30 days' if soon else ''}: {o['reason']}"
        ]
    L += ["", "## All stocks, ranked", ""] + _table(v["ranked"])
    L += ["", "## Not in this version", ""] + [f"- {p}" for p in v["pending"]]
    L += ["", f"_{DISCLAIMER}_", ""]
    return "\n".join(L)


def write_segment(v: dict[str, Any], folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    stem = v["period"]
    md, cs, xl, js = (folder / f"{stem}.{e}" for e in ("md", "csv", "xlsx", "json"))
    md.write_text(segment_md(v), encoding="utf-8")
    with cs.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADERS)
        for r in v["ranked"]:
            w.writerow(
                [
                    ("; ".join(r[h]) if h == "flags" else ("" if r[h] is None else r[h]))
                    for h in HEADERS
                ]
            )
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{v['cap']} {stem}"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in v["ranked"]:
        ws.append([("; ".join(r[h]) if h == "flags" else r[h]) for h in HEADERS])
    ws.freeze_panes = "B2"
    wb.save(xl)
    js.write_text(json.dumps(v, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return [md, cs, xl, js]
