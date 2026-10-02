"""Share export (UX-11; AC-F09.8): a Markdown view and a PNG card with nothing personal in them.

Built only from `mask_snapshot()`, so there is no quantity, ₹ value, ₹ P&L, position verb, sizing
rationale, thesis or note to leak. It adds the personal-use disclaimer and the SEBI note.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from parakh.render import format as fmt  # noqa: E402
from parakh.render.tokens import status, tokens  # noqa: E402
from parakh.services.reports import (  # noqa: E402
    DISCLAIMER,
    action_box,
    mask_snapshot,
    verdict_label,
)

SEBI_NOTE = (
    "Sharing stock-specific buy/sell views publicly may need SEBI Research Analyst registration. "
    "This card is for personal discussion only."
)


def share_markdown(snap: dict[str, Any]) -> str:
    s = mask_snapshot(snap)
    v, a = s["verdict"], action_box(s)
    fv = a["fair_value"]
    lines = [
        f"# {s['symbol']} — {s['name']} ({s['period']})",
        "",
        f"**{verdict_label(v['verdict'])}**"
        + (f" ({v['qualifier']})" if v.get("qualifier") else "")
        + f" · confidence {v['confidence']}",
        "",
        f"- Value score {s['value']['score']:.0f} ({s['value']['view']})"
        if s["value"].get("score") is not None
        else "- Value score N/A",
        f"- Momentum score {s['momentum']['score']:.0f} ({s['momentum']['view']})"
        if s["momentum"].get("score") is not None
        else "- Momentum score N/A",
        f"- Segment regime: {s['regime']['regime']}",
        f"- Close {fmt.inr(s['price']['close'], decimals=2)} on {s['price']['last_session']}",
    ]
    if fv:
        lines.append(f"- Fair-value range {fmt.inr(fv['low'])} – {fmt.inr(fv['high'])}")
    if v.get("vetoes"):
        lines.append("- Vetoes: " + "; ".join(v["vetoes"]))
    if v.get("label"):
        lines.append(f"- {v['label']}")
    unknown = sum(1 for c in s.get("checks", []) if c["state"] == "UNKNOWN")
    flagged = sum(1 for c in s.get("checks", []) if c["state"] == "FLAGGED")
    lines.append(f"- Checks: {flagged} flagged, {unknown} could not be run")
    lines += ["", f"_{DISCLAIMER}_", "", f"_{SEBI_NOTE}_", ""]
    return "\n".join(lines)


def share_card(snap: dict[str, Any], path: Path) -> Path:
    s = mask_snapshot(snap)
    t = tokens()
    c = t.colors
    st = status("verdict", s["verdict"]["verdict"].upper().replace(" ", "_"))
    fig = plt.figure(figsize=(6, 3.4), dpi=160)
    fig.patch.set_facecolor(c["bg_card"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0.84), 1, 0.16, color=c["navy"], transform=ax.transAxes))
    ax.text(
        0.04,
        0.92,
        f"{s['symbol']} · {s['period']}",
        color=c["bg_card"],
        fontsize=13,
        weight="bold",
        va="center",
    )
    # A drawn dot, not an emoji: the card font has no colour-emoji glyphs. The word carries the meaning.
    ax.add_patch(
        plt.Circle((0.06, 0.66), 0.022, color=c[st.token], transform=ax.transAxes, clip_on=False)
    )
    ax.text(0.10, 0.66, st.word, color=c[st.token], fontsize=22, weight="bold", va="center")
    ax.text(
        0.04,
        0.50,
        f"Confidence {s['verdict']['confidence']}  ·  Regime {s['regime']['regime']}",
        color=c["text_muted"],
        fontsize=9,
        va="center",
    )
    for i, (name, lens) in enumerate((("Value", s["value"]), ("Momentum", s["momentum"]))):
        x = 0.04 + i * 0.30
        ax.text(x, 0.36, name, color=c["text_muted"], fontsize=8)
        ax.text(
            x,
            0.24,
            "N/A" if lens.get("score") is None else f"{lens['score']:.0f}",
            color=c["text"],
            fontsize=20,
            weight="bold",
        )
    ax.text(
        0.04, 0.08, "Personal analysis. Not investment advice.", color=c["text_muted"], fontsize=7
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
