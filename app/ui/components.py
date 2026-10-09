"""The UI component library (plan 12 §4; AC-F22.2, F22.4). Every component is a plain function that returns
an HTML string built only from tokens, so it can be rendered by Streamlit, unit-tested and shown in the gallery.

    from app.ui import components as UI
    UI.show(UI.verdict_chip("BUY", prev="HOLD"))

A status always carries colour + icon + word (AC-F22.2). Numbers and money go through `render/format.py` only
(AC-F22.5). Missing data shows an em dash, never zero. Position amounts are shown only when `masked=False`.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any

import streamlit as st

from parakh.render import format as fmt
from parakh.render.tokens import Style, status

e = html.escape

# the qualitative agent's words → the concall vocabulary of plan 12 §3.2 (UI.concall_pill)
CONCALL_WORDS = {"SUPPORTED": "CONFIRMS", "STRESSED": "CHALLENGES"}
VERDICT_ALIASES = {"STRONG BUY": "STRONG_BUY", "MOMENTUM TRADE ONLY": "MOMENTUM_ONLY"}


def show(markup: str) -> None:
    st.markdown(f'<div class="pk">{markup}</div>', unsafe_allow_html=True)


def _style(family: str, value: str | None) -> Style | None:
    if not value:
        return None
    key = VERDICT_ALIASES.get(value.upper(), value.upper().replace(" ", "_"))
    try:
        return status(family, key)
    except KeyError:
        return None


def status_style(family: str, value: str | None) -> Style | None:
    """Public access to the token style for a status (tables use the word, not the HTML)."""
    return _style(family, value)


def _chip(style: Style | None, fallback: str, size: str = "sm") -> str:
    if style is None:
        return (
            f'<span class="pk-chip {size}" style="--chip: var(--c-neutral)">⚪ {e(fallback)}</span>'
        )
    fill = "" if style.outline else " fill"
    return (
        f'<span class="pk-chip {size}{fill}" style="--chip: var(--c-{style.token})">'
        f"{e(style.icon)} {e(style.word)}</span>"
    )


# -- status components --------------------------------------------------------------------------
def verdict_chip(
    verdict: str | None, *, action: str | None = None, prev: str | None = None, size: str = "sm"
) -> str:
    """Verdict or, for an owned stock, the position verb; optional "prev →"."""
    style = _style("position", action) if action else _style("verdict", verdict)
    now = _chip(style, verdict or "—", size)
    if prev and prev != verdict:
        before = _style("verdict", prev)
        word = before.word if before else prev
        return f'<span class="pk-prev">{e(word)} →</span>{now}'
    return now


def thesis_pill(state: str | None) -> str:
    return f'<span class="pk-muted">Thesis</span> {_chip(_style("thesis", state or "NOT_SET"), "NOT SET")}'


def concall_pill(label: str, verdict: str | None) -> str:
    word = CONCALL_WORDS.get((verdict or "").upper(), (verdict or "").upper())
    return f'<span class="pk-muted">{e(label)}</span> {_chip(_style("concall", word), "no read")}'


def severity_chip(sev: str) -> str:
    return _chip(_style("severity", sev), sev)


def check_row(name: str, state: str, detail: str = "") -> str:
    """Tri-state: CLEAN, FLAGGED or UNKNOWN with the reason (UX-05: unknown is never shown as clean)."""
    more = f'<span class="pk-muted"> — {e(detail)}</span>' if detail else ""
    return f'<div class="pk-row">{_chip(_style("check", state), state)} <span>{e(name)}</span>{more}</div>'


def owned_badge(
    *,
    weight_pct: float | None,
    pnl_pct: float | None,
    masked: bool = True,
    quantity: float | None = None,
    value_inr: float | None = None,
    cost_pending: bool = False,
) -> str:
    parts = ['<span class="pk-chip fill" style="--chip: var(--c-positive)">🟢 OWNED</span>']
    parts.append(f'<span class="num">wt {fmt.pct(weight_pct, signed=False)}</span>')
    parts.append(
        '<span class="num">P&amp;L cost pending</span>'
        if cost_pending
        else f'<span class="num">P&amp;L {fmt.pct(pnl_pct)}</span>'
    )
    if not masked:
        if quantity is not None:
            parts.append(f'<span class="num">{quantity:g} sh</span>')
        if value_inr is not None:
            parts.append(f'<span class="num">{e(fmt.inr(value_inr, compact=True))}</span>')
    return '<div class="pk-row">' + " ".join(parts) + "</div>"


def banner(text: str, action: str | None = None) -> str:
    act = f" <b>{e(action)}</b>" if action else ""
    return f'<div class="pk-banner">{e(text)}{act}</div>'


def error_panel(title: str, next_step: str) -> str:
    return f'<div class="pk-err"><b>{e(title)}</b><br>{e(next_step)}</div>'


# -- numbers and charts -------------------------------------------------------------------------
def score_ring(
    score: float | None, *, label: str, delta: float | None = None, size: int = 84
) -> str:
    """0–100 ring with the change vs last month. A missing score is an empty ring and an em dash."""
    r = size / 2 - 7
    circ = 2 * 3.14159 * r
    frac = 0 if score is None else max(0.0, min(1.0, score / 100))
    tone = (
        "neutral"
        if score is None
        else ("positive" if score >= 65 else ("caution" if score >= 40 else "negative"))
    )
    dtxt = (
        ""
        if delta is None
        else (f"▲ {delta:+.0f}" if delta > 0 else (f"▼ {delta:+.0f}" if delta < 0 else "● 0"))
    )
    return (
        f'<div style="display:inline-block;text-align:center;margin:0 .6rem">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="{e(label)} {fmt.MISSING if score is None else round(score)}">'
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="var(--c-border)" stroke-width="7"/>'
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="var(--c-{tone})" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{circ * frac:.1f} {circ:.1f}" transform="rotate(-90 {size / 2} {size / 2})"/>'
        f'<text x="50%" y="54%" text-anchor="middle" class="num" fill="var(--c-text)" font-size="20" font-weight="600">'
        f"{fmt.MISSING if score is None else round(score)}</text></svg>"
        f'<div class="pk-muted">{e(label)}</div><div class="num">{e(dtxt)}</div></div>'
    )


def range_bar(
    *,
    low: float | None,
    high: float | None,
    cmp: float | None,
    entry: float | None = None,
    fair_low: float | None = None,
    fair_high: float | None = None,
) -> str:
    """52-week range with the price dot, the entry-cost notch and the fair-value band."""
    if low is None or high is None or cmp is None or high <= low:
        return '<div class="pk-muted">52-week range — not available</div>'

    def pos(x: float) -> float:
        return max(0.0, min(100.0, (x - low) / (high - low) * 100))

    band = ""
    if fair_low is not None and fair_high is not None:
        band = f'<div style="position:absolute;left:{pos(fair_low):.1f}%;width:{max(pos(fair_high) - pos(fair_low), 1):.1f}%;top:0;bottom:0;background:var(--c-accent);opacity:.25"></div>'
    notch = (
        ""
        if entry is None
        else f'<div title="your average cost" style="position:absolute;left:{pos(entry):.1f}%;top:-3px;bottom:-3px;width:2px;background:var(--c-navy)"></div>'
    )
    return (
        '<div style="position:relative;height:10px;border-radius:5px;background:var(--c-bg_muted);border:1px solid var(--c-border);margin:.9rem 0 .3rem">'
        f"{band}{notch}"
        f'<div title="CMP" style="position:absolute;left:calc({pos(cmp):.1f}% - 6px);top:-3px;width:12px;height:12px;border-radius:50%;background:var(--c-text)"></div></div>'
        f'<div class="row num pk-muted" style="display:flex;justify-content:space-between"><span>{e(fmt.inr(low, decimals=0))}</span>'
        f"<span>CMP {e(fmt.inr(cmp, decimals=0))}</span><span>{e(fmt.inr(high, decimals=0))}</span></div>"
    )


def sparkline(
    close: Sequence[float | None],
    *,
    dma50: Sequence[float | None] | None = None,
    dma200: Sequence[float | None] | None = None,
    avg_cost: float | None = None,
    width: int = 280,
    height: int = 64,
    incomplete: bool = False,
) -> str:
    pts = [c for c in close if c is not None]
    if len(pts) < 2:
        return '<span class="pk-muted">no price history</span>'
    series = [list(close)]
    for extra in (dma50, dma200):
        if extra:
            series.append(list(extra))
    flat = [v for s in series for v in s if v is not None] + ([avg_cost] if avg_cost else [])
    lo, hi = min(flat), max(flat)
    span = (hi - lo) or 1.0

    def path(vals: Sequence[float | None]) -> str:
        n = len(vals)
        out = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            out.append(
                f"{'M' if not out else 'L'}{i / max(n - 1, 1) * width:.1f},{height - (v - lo) / span * height:.1f}"
            )
        return " ".join(out)

    lines = [f'<path d="{path(series[0])}" fill="none" stroke="var(--c-text)" stroke-width="1.6"/>']
    for s, tone in zip(series[1:], ("accent", "caution"), strict=False):
        lines.append(
            f'<path d="{path(s)}" fill="none" stroke="var(--c-{tone})" stroke-width="1" opacity=".8"/>'
        )
    if avg_cost:
        y = height - (avg_cost - lo) / span * height
        lines.append(
            f'<line x1="0" x2="{width}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--c-navy)" stroke-dasharray="4 3"/>'
        )
    mark = '<span class="pk-muted" title="price history incomplete"> ~</span>' if incomplete else ""
    return f'<svg width="{width}" height="{height}" role="img" aria-label="12-month price">{"".join(lines)}</svg>{mark}'


def evidence_list(bullets: Sequence[str], *, limit: int = 4) -> str:
    """At most four ordered bullets (UX-03)."""
    if not bullets:
        return '<div class="pk-muted">No evidence recorded for this verdict.</div>'
    return (
        '<ol class="pk-ev">' + "".join(f"<li>{e(b)}</li>" for b in list(bullets)[:limit]) + "</ol>"
    )


def component_grid(items: Sequence[dict[str, Any]]) -> str:
    """Thesis key metrics: coloured left border, status badge, one-line evidence."""
    if not items:
        return '<div class="pk-muted">No key metrics defined.</div>'
    cells = []
    for it in items:
        st_ = _style("thesis", it.get("status") or "NOT_SET")
        tone = st_.token if st_ else "neutral"
        cells.append(
            f'<div class="pk-km" style="--chip: var(--c-{tone})"><b>{e(it["id"])}</b> {_chip(st_, it.get("status", "NOT SET"))}'
            f'<div>{e(it["text"])}</div><div class="pk-muted">{e(it.get("evidence", ""))}</div></div>'
        )
    return '<div class="pk-grid">' + "".join(cells) + "</div>"


def thesis_heatmap(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    """Key metrics × the last four quarters; a gap is 'no read', never a green cell."""
    if not rows:
        return '<div class="pk-muted">No thesis history yet.</div>'
    head = "".join(f"<th>{e(c)}</th>" for c in columns)
    body = []
    for r in rows:
        cells = []
        for c in columns:
            v = (r.get("cells") or {}).get(c)
            s = _style("concall", CONCALL_WORDS.get((v or "").upper(), v or ""))
            cells.append(
                f'<td class="cell" style="--chip: var(--c-{s.token})">{e(s.icon)} {e(s.word)}</td>'
                if s
                else '<td class="pk-muted">—</td>'
            )
        body.append(f"<tr><th>{e(r['id'])}</th>{''.join(cells)}</tr>")
    return f'<table class="pk-heat"><tr><th></th>{head}</tr>{"".join(body)}</table>'


def score_heatmap(rows: Sequence[dict[str, Any]], columns: Sequence[str]) -> str:
    """Stocks × months. Colour comes from the score band; the number is always printed."""
    if not rows:
        return '<div class="pk-muted">No history yet.</div>'
    head = "".join(f"<th>{e(c)}</th>" for c in columns)
    body = []
    for r in rows:
        cells = []
        for c in columns:
            v = (r.get("cells") or {}).get(c)
            if v is None:
                cells.append('<td class="pk-muted">—</td>')
                continue
            tone = "positive" if v >= 65 else ("caution" if v >= 40 else "negative")
            mark = "◆" if (r.get("changed") or {}).get(c) else ""
            cells.append(
                f'<td class="cell num" style="--chip: var(--c-{tone})">{round(v)}{mark}</td>'
            )
        body.append(f"<tr><th>{e(r['symbol'])}</th>{''.join(cells)}</tr>")
    return f'<table class="pk-heat"><tr><th></th>{head}</tr>{"".join(body)}</table>'


def timeline(items: Sequence[dict[str, Any]], *, limit: int = 12) -> str:
    if not items:
        return '<div class="pk-muted">Nothing to show yet.</div>'
    rows = "".join(
        f'<div class="pk-row"><span class="num pk-muted">{e(str(i.get("when", "")))}</span><span>{e(str(i.get("text", "")))}</span></div>'
        for i in items[:limit]
    )
    return f"<div>{rows}</div>"


def count_chips(counts: dict[str, int]) -> str:
    if not counts:
        return '<span class="pk-muted">Nothing new.</span>'
    return "".join(
        f'<span class="pk-count">{e(k.replace("_", " "))} <b>{v}</b></span>'
        for k, v in counts.items()
    )


def stage_ladder(stages: Sequence[dict[str, str]]) -> str:
    """Long-job stages: done ✅, failed ⚠️ with the reason, pending ❔."""
    out = []
    for s in stages:
        state = {"done": "CLEAN", "failed": "FLAGGED"}.get(s.get("state", ""), "UNKNOWN")
        out.append(
            f'<div class="pk-stage">{_chip(_style("check", state), state)} <span>{e(s["name"])}</span><span class="pk-muted">{e(s.get("reason", ""))}</span></div>'
        )
    return "".join(out)


def suggestion_card(s: dict[str, Any]) -> str:
    """Plan 06 §5.1 card: who, why, how long it has to live."""
    who = "🤖 " if s.get("origin", "rule").startswith("agent") else ""
    srcs = ", ".join(s.get("sources", [])) or "—"
    return (
        f'<div class="pk-card"><div class="pk-row"><b>{who}{e(s["symbol"])}</b>'
        f'<span class="pk-muted">{e(str(s["cap"]).title())} · {e(s["action"].replace("_", " "))}</span></div>'
        f'<div>{e(s["reason"])}</div><div class="pk-muted num">sources {e(srcs)} · expires {e(fmt.date(s.get("expires_on")))}</div></div>'
    )


# -- native-widget components -------------------------------------------------------------------
def privacy_toggle(key: str = "privacy") -> bool:
    """The header toggle: when on, quantities, ₹ values and ₹ P&L are hidden on every page."""
    if key not in st.session_state:
        st.session_state[key] = True  # masked by default (UX-11)
    return st.toggle(
        "Privacy view", key=key, help="Hides quantities, ₹ values and ₹ P&L. Safe for screenshots."
    )


def feedback(key: str) -> str | None:
    c1, c2, _ = st.columns([1, 1, 6])
    if c1.button("👍 Useful", key=f"{key}-u"):
        return "useful"
    if c2.button("👎 Noise", key=f"{key}-n"):
        return "noise"
    return None


GALLERY = [
    "verdict_chip",
    "owned_badge",
    "thesis_pill",
    "concall_pill",
    "score_ring",
    "evidence_list",
    "check_row",
    "range_bar",
    "sparkline",
    "component_grid",
    "thesis_heatmap",
    "score_heatmap",
    "timeline",
    "count_chips",
    "stage_ladder",
    "suggestion_card",
    "banner",
    "error_panel",
    "feedback",
    "privacy_toggle",
]
