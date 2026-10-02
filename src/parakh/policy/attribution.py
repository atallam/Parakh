"""Score attribution: why a verdict moved (AC-F08.4; UX-03).

`drivers(prev, cur, ...)` returns at most `n` drivers, most important first:

1. a veto that appeared or cleared;
2. a regime, thesis or ownership change;
3. each lens sub-score's change in points (weight × change in sub-score), with the metric inside
   it that moved most, when last month's metric values are known;
4. a band change that hysteresis held back is reported as such.

Everything is arithmetic over two snapshots: no model reads this, and nothing here is invented.
`prev` is last month's snapshot (a dict) or None for a stock's first month.
"""

from __future__ import annotations

from typing import Any

from parakh.render.format import MINUS

IMPACT_VETO = 100.0
IMPACT_CONTEXT = 90.0


def _pts(x: float) -> str:
    return f"{x:+.1f}".replace("-", MINUS)


def _effective_weights(details: dict[str, Any], present: set[str]) -> dict[str, float]:
    w = {k: float(v) for k, v in (details.get("weights") or {}).items() if k in present}
    total = sum(w.values())
    return {k: v / total for k, v in w.items()} if total else {}


def _metric_label(metric_id: str) -> str:
    return metric_id.rsplit(".", 1)[-1].replace("_", " ")


def _fmt(v: Any) -> str:
    if isinstance(v, int | float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def _lens_drivers(
    lens: str,
    prev: dict[str, Any],
    cur: dict[str, Any],
    metric_sub: dict[str, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    ps, cs = prev.get("subscores") or {}, cur.get("subscores") or {}
    present = set(ps) & set(cs)
    weights = _effective_weights(cur.get("details") or {}, present)
    pm = (prev.get("details") or {}).get("metric_values") or {
        k: v.get("value") for k, v in ((prev.get("details") or {}).get("metrics") or {}).items()
    }
    cm = (cur.get("details") or {}).get("metric_values") or {
        k: v.get("value") for k, v in ((cur.get("details") or {}).get("metrics") or {}).items()
    }
    for sub in sorted(present):
        delta = (cs[sub] - ps[sub]) * 100 * weights.get(sub, 0.0)
        if abs(delta) < 0.05:
            continue
        movers = []
        for mid, sname in metric_sub.items():
            if sname != sub:
                continue
            a, b = pm.get(mid), cm.get(mid)
            if isinstance(a, int | float) and isinstance(b, int | float) and a != b:
                movers.append((abs(b - a) / (abs(a) or 1.0), mid, a, b))
        text = f"{lens} {sub.replace('_', ' ')} {_pts(delta)} pts"
        if movers:
            _, mid, a, b = max(movers)
            text += f" ({_metric_label(mid)} {_fmt(a)} → {_fmt(b)})"
        out.append(
            {
                "kind": "subscore",
                "lens": lens,
                "subscore": sub,
                "points": round(delta, 2),
                "text": text,
                "impact": abs(delta),
            }
        )
    return out


def drivers(
    prev: dict[str, Any] | None,
    cur: dict[str, Any],
    n: int,
    metric_sub: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Top-n drivers of the change from `prev` to `cur`. Empty for a first month."""
    if prev is None:
        return []
    metric_sub = metric_sub or {}
    out: list[dict[str, Any]] = []
    pv, cv = prev.get("verdict") or {}, cur.get("verdict") or {}
    new_v = sorted(set(cv.get("vetoes") or []) - set(pv.get("vetoes") or []))
    gone = sorted(set(pv.get("vetoes") or []) - set(cv.get("vetoes") or []))
    for v in new_v:
        out.append({"kind": "veto", "text": f"new veto {v}", "impact": IMPACT_VETO})
    for v in gone:
        out.append({"kind": "veto", "text": f"veto {v} cleared", "impact": IMPACT_VETO})
    pr, cr = (prev.get("regime") or {}).get("regime"), (cur.get("regime") or {}).get("regime")
    if pr and cr and pr != cr:
        out.append({"kind": "regime", "text": f"regime {pr} → {cr}", "impact": IMPACT_CONTEXT})
    pt, ct = (prev.get("thesis") or {}).get("status"), (cur.get("thesis") or {}).get("status")
    if pt and ct and pt != ct:
        out.append({"kind": "thesis", "text": f"thesis {pt} → {ct}", "impact": IMPACT_CONTEXT})
    if pv.get("owned") is not None and cv.get("owned") is not None and pv["owned"] != cv["owned"]:
        out.append(
            {
                "kind": "ownership",
                "text": "now owned" if cv["owned"] else "no longer owned",
                "impact": IMPACT_CONTEXT,
            }
        )
    for lens in ("value", "momentum"):
        if prev.get(lens) and cur.get(lens):
            out.extend(_lens_drivers(lens, prev[lens], cur[lens], metric_sub))
    for held in cv.get("held_by_hysteresis") or []:
        raw = cv.get(f"{held}_band_raw")
        band = cv.get(f"{held}_band")
        out.append(
            {
                "kind": "hysteresis",
                "text": f"{held} score moved toward {raw} but stayed {band} (inside the hysteresis band)",
                "impact": 1.0,
            }
        )
    out.sort(key=lambda d: -d["impact"])
    return out[:n]
