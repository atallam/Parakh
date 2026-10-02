"""Report services: one view model per stock, shared by the report, share export, CLI and MCP.

Everything here is arithmetic and wording over a snapshot (a dict) and, optionally, last month's
snapshot. No network, no LLM, no recomputed score (UX-02, UX-09, AG-04).

    view = stock_view(snapshot, prev)          # tldr, chip, what changed, action box, checks …
    safe = mask_snapshot(snapshot)             # no quantity, ₹ value, ₹ P&L, sizing or notes
"""

from __future__ import annotations

import copy
import re
from typing import Any

from parakh.render import format as fmt
from parakh.render.tokens import label, status

DISCLAIMER = (
    "Personal analytical framework. Not investment advice, and not a research report. "
    "Scores come from fixed rules applied to public data; every threshold is an assumption. "
    "If you ever publish stock-specific calls, SEBI's Research Analyst regulations may apply."
)
NEAR_LTCG_DAYS = 30
MAX_CHANGES = 4

_VERDICT_KEY = {
    "STRONG BUY": "STRONG_BUY",
    "MOMENTUM TRADE ONLY": "MOMENTUM_ONLY",
    "MOMENTUM ONLY": "MOMENTUM_ONLY",
}


def verdict_label(verdict: str | None, owned_wording: str | None = None) -> str:
    """Icon + word, from the token file. Owned stocks show the position verb."""
    if owned_wording:
        return label(status("position", owned_wording))
    if not verdict:
        return "—"
    key = _VERDICT_KEY.get(verdict.upper(), verdict.upper().replace(" ", "_"))
    try:
        return label(status("verdict", key))
    except KeyError:
        return verdict


def chip(verdict: dict[str, Any], prev: dict[str, Any] | None = None) -> str:
    """`⚪ ● HOLD → 🟢 ▲ BUY (staggered)`: the verdict chip with last month's verdict (UI.verdict_chip)."""
    now = verdict_label(verdict.get("verdict"), verdict.get("action"))
    q = verdict.get("qualifier")
    if q:
        now += f" ({q})"
    if verdict.get("label"):
        now += f" · {verdict['label']}"
    if prev:
        before = verdict_label(prev["verdict"].get("verdict"), prev["verdict"].get("action"))
        if before != verdict_label(verdict.get("verdict"), verdict.get("action")):
            return f"{before} → {now}"
        return f"{now} (unchanged)"
    return f"{now} (first report)"


def fired_signals(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Signals that fired this month, with names (the lens lists IDs; the detail has the rest)."""
    rows = ((snap["momentum"].get("details") or {}).get("active_signals")) or []
    return [r for r in rows if r.get("status") == "fired"]


def _score(lens: dict[str, Any]) -> str:
    return "N/A" if lens.get("score") is None else f"{lens['score']:.0f}"


def _delta(cur: dict[str, Any], prev: dict[str, Any] | None) -> float | None:
    if not prev or cur.get("score") is None or prev.get("score") is None:
        return None
    return round(cur["score"] - prev["score"], 1)


def _delta_txt(d: float | None) -> str:
    if d is None:
        return "new"
    if d == 0:
        return "● 0"
    return f"▲ {d:+.0f}".replace("-", fmt.MINUS) if d > 0 else f"▼ {d:+.0f}".replace("-", fmt.MINUS)


def what_changed(
    snap: dict[str, Any], prev: dict[str, Any] | None, near_ltcg_days: int = NEAR_LTCG_DAYS
) -> list[str]:
    """At most four bullets, in the fixed order of UX-03: thesis → verdict drivers → scores → position."""
    if not prev:
        return ["First report for this stock; there is no earlier month to compare with."]
    out: list[str] = []
    th, v = snap["thesis"], snap["verdict"]
    if th.get("changed_from"):
        out.append(f"Thesis {th['changed_from']} → {th['status']} ({th.get('status_source', '')}).")
    elif th.get("review_due"):
        out.append(f"Thesis review was due by {th.get('review_by')}.")
    if v.get("changed"):
        d = "; ".join(x["text"] for x in v.get("drivers", [])[:3]) or "no single driver"
        out.append(
            f"Verdict {verdict_label(v.get('prev_verdict'), v.get('prev_action'))} → {verdict_label(v['verdict'], v.get('action'))}: {d}."
        )
    elif v.get("held_by_hysteresis"):
        out.append(
            "A band change was held back by the ±5-point hysteresis: "
            + ", ".join(v["held_by_hysteresis"])
            + "."
        )
    dv, dm = _delta(snap["value"], prev["value"]), _delta(snap["momentum"], prev["momentum"])
    if dv is not None or dm is not None:
        out.append(
            f"Value {_score(snap['value'])} ({_delta_txt(dv)}), momentum {_score(snap['momentum'])} ({_delta_txt(dm)})."
        )
    pr = prev.get("regime", {}).get("regime")
    if pr and pr != snap["regime"]["regime"]:
        out.append(f"Segment regime {pr} → {snap['regime']['regime']}.")
    pos = snap.get("position")
    if (
        pos
        and not pos.get("cost_pending")
        and 0 < pos.get("days_to_long_term", 0) <= near_ltcg_days
    ):
        out.append(
            f"Long-term capital-gains status in {pos['days_to_long_term']} days; timing matters if you act."
        )
    fired = fired_signals(snap)
    if fired:
        out.append("Signals fired: " + ", ".join(s["id"] for s in fired[:4]) + ".")
    return out[:MAX_CHANGES] or [
        "No change in verdict, thesis or regime; scores moved within their bands."
    ]


def tldr(snap: dict[str, Any]) -> str:
    """One line: the verdict and the single biggest reason (plan 00 §8 §0)."""
    v = snap["verdict"]
    head = verdict_label(v["verdict"], v.get("action"))
    if v.get("label"):
        head += f" · {v['label']}"
    if v.get("vetoes"):
        why = "veto: " + "; ".join(v["vetoes"][:2])
    elif v.get("drivers"):
        why = v["drivers"][0]["text"]
    else:
        why = f"value {_score(snap['value'])} ({snap['value']['view']}), momentum {_score(snap['momentum'])} ({snap['momentum']['view']})"
    return f"{snap['symbol']}: {head}, {why}. Confidence {v['confidence']}."


def _fv(snap: dict[str, Any]) -> dict[str, Any]:
    return snap["chart"] if snap.get("chart") else {}


def action_box(snap: dict[str, Any]) -> dict[str, Any]:
    """Entry zone · stop · fair-value range · risk/reward · action for your position · tax note.

    Derived from lens outputs, never a price target. The entry zone is the span from the 50-DMA
    to the close when the close is above it (buy in tranches on pullbacks), else the close
    and 3% below it; the stop is the momentum lens's trailing stop; risk/reward is the distance
    to the fair-value mid over the distance to that stop.
    """
    close = snap["price"].get("close")
    dma50 = ((snap["momentum"].get("details") or {}).get("dma") or {}).get("dma50")
    exits = (snap["momentum"].get("details") or {}).get("exit_levels") or {}
    stop = exits.get("trailing_stop")
    ch = _fv(snap)
    lo, hi, mid = ch.get("fair_value_low"), ch.get("fair_value_high"), ch.get("fair_value_mid")
    v = snap["verdict"]
    entry = None
    if close and v["verdict"] in ("STRONG BUY", "BUY", "ACCUMULATE"):
        top = close
        bottom = dma50 if dma50 and dma50 < close else close * 0.97
        entry = (round(bottom, 2), round(top, 2))
    rr = None
    if close and stop and mid and stop < close:
        rr = round((mid - close) / (close - stop), 2)
    irr = (snap["value"].get("details") or {}).get("expected_irr") or {}
    pos = snap.get("position")
    return {
        "entry_zone": entry,
        "stop": None if stop is None else round(stop, 2),
        "trend_exit": exits.get("trend_exit_200dma"),
        "fair_value": None
        if lo is None
        else {"low": round(lo, 2), "high": round(hi, 2), "mid": round(mid, 2)},
        "margin_of_safety": (snap["value"].get("details") or {}).get("margin_of_safety"),
        "expected_return": irr.get("weighted"),
        "hurdle": irr.get("hurdle"),
        "risk_reward": rr,
        "action": verdict_label(v["verdict"], v.get("action")),
        "position_note": (pos or {}).get("tax_note"),
        "tax_if_sold_now_inr": (pos or {}).get("tax_if_sold_now_inr"),
        "days_to_long_term": (pos or {}).get("days_to_long_term"),
    }


def position_line(pos: dict[str, Any] | None, masked: bool = False) -> str:
    if not pos:
        return "NOT HELD"
    masked = masked or "quantity" not in pos
    parts = [
        "🟢 OWNED",
        f"wt {fmt.pct(pos['weight_pct'], signed=False)}"
        if pos.get("weight_pct") is not None
        else "wt N/A",
    ]
    parts.append(
        "P&L cost pending" if pos.get("cost_pending") else f"P&L {fmt.pct(pos['pnl_pct'])}"
    )
    if not masked:
        parts.insert(1, f"{pos['quantity']:g} sh")
        if pos.get("avg_cost_inr") is not None:
            parts.insert(2, f"avg {fmt.inr(pos['avg_cost_inr'], decimals=2)}")
    if pos.get("days_to_long_term"):
        parts.append(f"LTCG in {pos['days_to_long_term']} days")
    return " · ".join(parts)


def check_rows(snap: dict[str, Any]) -> list[dict[str, str]]:
    """Tri-state rows (UX-05): ✅ CLEAN · ⚠️ FLAGGED · ❔ UNKNOWN with reason and last attempt."""
    rows = []
    for c in snap.get("checks", []):
        st = c["state"]
        text = label(status("check", st))
        why = ""
        if st == "UNKNOWN":
            why = f"couldn't check: {c.get('detail') or 'no reason recorded'} · tried {c.get('last_attempt', 'n/a')}"
        elif c.get("detail"):
            why = c["detail"]
        rows.append({"name": c["name"], "state": st, "text": text, "detail": why})
    return rows


def stock_view(
    snap: dict[str, Any], prev: dict[str, Any] | None = None, near_ltcg_days: int = NEAR_LTCG_DAYS
) -> dict[str, Any]:
    v = snap["verdict"]
    return {
        "tldr": tldr(snap),
        "chip": chip(v, prev),
        "confidence": v["confidence"],
        "what_changed": what_changed(snap, prev, near_ltcg_days),
        "action_box": action_box(snap),
        "position_line": position_line(snap.get("position")),
        "value_score": _score(snap["value"]),
        "value_delta": _delta(snap["value"], (prev or {}).get("value")),
        "momentum_score": _score(snap["momentum"]),
        "momentum_delta": _delta(snap["momentum"], (prev or {}).get("momentum")),
        "checks": check_rows(snap),
        "limited_history": v.get("label"),
    }


# -- Redaction for the share export (AC-F09.8) ---------------------------------------------------
_PERSONAL = re.compile(
    r"\bowned\b|\bhold(?:ing|s)?\b.*\bshares?\b|thesis|position|cost basis|\bADD\b|\bTRIM\b|\bEXIT\b",
    re.I,
)
SHARE_KEYS_DROPPED = ("position", "overrides", "lineage")


def mask_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """A copy with the position, sizing rationale, overrides and personal notes removed.

    The verdict stays, but the owned wording (ADD/TRIM/EXIT) is replaced by the plain verdict
    name, because a position verb reveals that you hold the stock.
    """
    out = copy.deepcopy(snap)
    for k in SHARE_KEYS_DROPPED:
        out.pop(k, None)
    out["position"] = None
    out["thesis"] = {"status": "NOT_SET", "present": False}  # your thesis is personal
    out["notes"] = []
    out["overrides"] = []
    v = out["verdict"]
    v["owned"] = False
    v["action"] = None
    v["override"] = None
    v["prev_action"] = None
    v["headline"] = v["verdict"]
    v["thesis_status"] = "NOT_SET"
    v["drivers"] = [d for d in v.get("drivers", []) if d.get("kind") not in ("thesis", "ownership")]
    for k in ("trail", "reasons"):
        v[k] = [t for t in v.get(k, []) if not _PERSONAL.search(t)]
    return out
