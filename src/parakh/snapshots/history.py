"""history.csv and HISTORY.md, rendered from snapshots (plan 00 §3; AC-F09.2, AC-F09.3).

history.csv is rebuilt from every snapshot on disk, so re-running a month replaces its row and
a backfilled month slots into place: idempotent by construction, never an append that can
duplicate. HISTORY.md shows the last 24 months, every verdict change, and trend flags.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from parakh.render import format as fmt
from parakh.services.reports import verdict_label
from parakh.snapshots.store import periods_for, read_snapshot_dict, snapshot_path, stock_dir

HISTORY_MONTHS = 24
TREND_MONTHS = 3

COLUMNS = [
    "period", "asof", "symbol", "isin", "cap", "profile", "history_class", "run_id",
    "framework_version", "policy_version", "weights_hash", "config_hash",
    "close", "verdict", "headline", "qualifier", "confidence", "owned", "rule_id",
    "value_score", "value_view", "value_conf", "value_band", "momentum_score", "momentum_view",
    "momentum_conf", "momentum_band", "rs_percentile", "stage", "trend_template_passed",
    "pct_from_52w_high", "regime", "thesis_status", "vetoes", "signals",
    "fair_value_low", "fair_value_mid", "fair_value_high", "margin_of_safety", "expected_irr",
    "data_confidence", "weight_pct",
]  # fmt: skip


def row_from(snap: dict[str, Any]) -> dict[str, Any]:
    v, val, mom = snap["verdict"], snap["value"], snap["momentum"]
    md, vd = mom.get("details") or {}, val.get("details") or {}
    ch = snap.get("chart") or {}
    pos = snap.get("position") or {}
    return {
        "period": snap["period"], "asof": snap["asof"], "symbol": snap["symbol"], "isin": snap["isin"],
        "cap": snap["cap"], "profile": snap["profile"], "history_class": snap["history_class"],
        "run_id": snap["run_id"], "framework_version": snap["framework"]["version"],
        "policy_version": snap["framework"]["policy_version"], "weights_hash": snap["framework"]["weights_hash"],
        "config_hash": snap["framework"]["config_hash"],
        "close": snap["price"].get("close"), "verdict": v["verdict"], "headline": v["headline"],
        "qualifier": v.get("qualifier") or "", "confidence": v["confidence"], "owned": v["owned"],
        "rule_id": v["rule_id"],
        "value_score": val.get("score"), "value_view": val.get("view"), "value_conf": val.get("confidence"),
        "value_band": v.get("value_band"), "momentum_score": mom.get("score"), "momentum_view": mom.get("view"),
        "momentum_conf": mom.get("confidence"), "momentum_band": v.get("momentum_band"),
        "rs_percentile": md.get("rs_percentile"), "stage": md.get("stage"),
        "trend_template_passed": (md.get("trend_template") or {}).get("passed"),
        "pct_from_52w_high": md.get("pct_from_52w_high"), "regime": snap["regime"]["regime"],
        "thesis_status": snap["thesis"].get("status"), "vetoes": "; ".join(v.get("vetoes", [])),
        "signals": ",".join(mom.get("signals") or []),
        "fair_value_low": ch.get("fair_value_low"), "fair_value_mid": ch.get("fair_value_mid"),
        "fair_value_high": ch.get("fair_value_high"), "margin_of_safety": vd.get("margin_of_safety"),
        "expected_irr": (vd.get("expected_irr") or {}).get("weighted"),
        "data_confidence": snap["data_quality"].get("confidence"), "weight_pct": pos.get("weight_pct"),
    }  # fmt: skip


def _all_snapshots(cap: str, symbol: str, root: Path | None) -> list[dict[str, Any]]:
    out = []
    for p in periods_for(cap, symbol, root):
        s = read_snapshot_dict(snapshot_path(cap, symbol, p, root))
        if s:
            out.append(s)
    return out


def history_csv_text(snaps: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    for s in sorted(snaps, key=lambda x: x["period"]):
        r = row_from(s)
        w.writerow({k: ("" if r[k] is None else r[k]) for k in COLUMNS})
    return buf.getvalue()


def trend_flags(snaps: list[dict[str, Any]]) -> list[str]:
    """Plain-language flags from the last few months (AC-F09.3)."""
    flags: list[str] = []
    if len(snaps) < TREND_MONTHS:
        return ["Fewer than three months of history: no trend flags yet."]
    last = snaps[-TREND_MONTHS:]
    for key, name in (("value", "Value"), ("momentum", "Momentum")):
        sc = [s[key].get("score") for s in last]
        if all(x is not None for x in sc):
            if sc[0] < sc[1] < sc[2]:
                flags.append(
                    f"{name} score has risen {TREND_MONTHS} months running ({sc[0]:.0f} → {sc[2]:.0f})."
                )
            elif sc[0] > sc[1] > sc[2]:
                flags.append(
                    f"{name} score has fallen {TREND_MONTHS} months running ({sc[0]:.0f} → {sc[2]:.0f})."
                )
    verdicts = [s["verdict"]["verdict"] for s in last]
    if len(set(verdicts)) == 1:
        flags.append(f"Verdict unchanged at {verdicts[0]} for {TREND_MONTHS}+ months.")
    flips = sum(
        1
        for a, b in zip(snaps[-6:], snaps[-5:], strict=False)
        if a["verdict"]["verdict"] != b["verdict"]["verdict"]
    )
    if flips >= 3:
        flags.append(
            f"{flips} verdict changes in the last six months: the stock is near a band edge."
        )
    regs = [s["regime"]["regime"] for s in last]
    if len(set(regs)) > 1:
        flags.append(
            "Segment regime changed within the last three months: " + " → ".join(regs) + "."
        )
    return flags or ["No trend flags this month."]


def history_md_text(snaps: list[dict[str, Any]]) -> str:
    snaps = sorted(snaps, key=lambda s: s["period"])
    if not snaps:
        return "# History\n\nNo snapshots yet.\n"
    s0 = snaps[-1]
    lines = [
        f"# {s0['symbol']}: history",
        "",
        f"_Generated from snapshots; never edit by hand. Last {HISTORY_MONTHS} months, newest first. "
        f"Framework {s0['framework']['version']}, policy {s0['framework']['policy_version']}._",
        "",
        "## Trend flags",
        "",
        *[f"- {f}" for f in trend_flags(snaps)],
        "",
        "## Month by month",
        "",
        "| Period | Verdict | Conf | Value | Momentum | Regime | Thesis | Close | Weights |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    recent = snaps[-HISTORY_MONTHS:][::-1]
    prev_weights = None
    for s in recent:
        v = s["verdict"]
        w = s["framework"]["weights_hash"]
        mark = "" if prev_weights in (None, w) else " ⚑"
        prev_weights = w
        lines.append(
            f"| {s['period']} | {verdict_label(v['verdict'], v.get('action'))} "
            f"| {v['confidence']} | {_n(s['value'].get('score'))} | {_n(s['momentum'].get('score'))} "
            f"| {s['regime']['regime']} | {s['thesis'].get('status') or '—'} | {fmt.inr(s['price'].get('close'), decimals=2)} | {w}{mark} |"
        )
    lines += [
        "",
        "⚑ the weights or policy hash differs from the next row: a score change that month may come from the rules, not the stock.",
        "",
        "## Verdict changes",
        "",
    ]
    changes = []
    for a, b in zip(snaps, snaps[1:], strict=False):
        if a["verdict"]["verdict"] != b["verdict"]["verdict"]:
            d = "; ".join(x["text"] for x in b["verdict"].get("drivers", [])[:3])
            changes.append(
                f"- **{b['period']}**: {a['verdict']['verdict']} → {b['verdict']['verdict']}"
                + (f" ({d})" if d else "")
            )
    lines += changes[::-1] if changes else ["- None on record."]
    lines += ["", "## Thesis status", ""]
    tl = snaps[-1]["thesis"].get("timeline") or []
    lines += [f"- {t['period']}: {t['status']}" for t in tl[::-1]] or ["- No thesis on record."]
    return "\n".join(lines) + "\n"


def _n(x: Any) -> str:
    return "N/A" if x is None else f"{x:.0f}"


def write_history(cap: str, symbol: str, root: Path | None = None) -> tuple[Path, Path]:
    snaps = _all_snapshots(cap, symbol, root)
    d = stock_dir(cap, symbol, root)
    d.mkdir(parents=True, exist_ok=True)
    csv_path, md_path = d / "history.csv", d / "HISTORY.md"
    csv_path.write_text(history_csv_text(snaps), encoding="utf-8", newline="")
    md_path.write_text(history_md_text(snaps), encoding="utf-8")
    return csv_path, md_path


def score_series(cap: str, symbol: str, root: Path | None = None) -> list[dict[str, Any]]:
    return [
        {
            "period": s["period"],
            "value_score": s["value"].get("score"),
            "momentum_score": s["momentum"].get("score"),
        }
        for s in _all_snapshots(cap, symbol, root)
    ][-HISTORY_MONTHS:]
