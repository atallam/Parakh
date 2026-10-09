"""Segment dashboard: one cap, one month, holdings first (plan 12 §5; F10)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.render import format as fmt  # noqa: E402
from parakh.services import app_api  # noqa: E402

setup("Segment dashboard", icon="🧭")
cap = st.radio("Segment", ["large", "mid", "small"], horizontal=True, format_func=str.title)
v = app_api.segment_full(cap)
if v is None:
    UI.show(UI.error_panel(f"No {cap}-cap summary yet", "Run `parakh run --mode monthly`."))
    st.stop()
reg = v["regime"]
st.markdown(f"**{cap.title()} cap · {v['period']}** · regime **{reg['regime']}**")
st.caption("; ".join((reg.get("reasons") or []) + (reg.get("flags") or [])))
UI.show(UI.count_chips(v["counts"]))


def rows(items: list[dict]) -> list[dict]:
    return [
        {
            "Stock": r["symbol"],
            "Verdict": r["chip"],
            "Conf": r["confidence"],
            "Value": fmt.score(r["value"]),
            "Momentum": fmt.score(r["momentum"]),
            "Thesis": r["thesis"],
            "Flags": "; ".join(r["flags"] + r["red_flags"]),
        }
        for r in items
    ]


st.markdown("#### Holdings")
if v["needs_action"]:
    UI.show(UI.banner("Needs your attention: " + ", ".join(r["symbol"] for r in v["needs_action"])))
if v["holdings"]:
    st.dataframe(rows(v["holdings"]), hide_index=True, width="stretch")
else:
    st.caption("No holdings in this segment.")
for c in v["concentration"]:
    st.warning(c)
risk = v.get("portfolio_risk") or {}
if risk.get("hhi") is not None:
    a, b, c = st.columns(3)
    a.metric("Top-5 share", fmt.pct(risk["top5_pct"], signed=False))
    b.metric("HHI", f"{risk['hhi']:.2f}", help="1.00 = one stock; lower is more spread")
    c.metric("Worst drawdown", fmt.pct(risk.get("worst_drawdown_pct")))
    st.dataframe(
        [
            {
                "Stock": r["symbol"],
                "XIRR": fmt.pct(r.get("xirr_pct")),
                "Benchmark": fmt.pct(r.get("benchmark_xirr_pct")),
                "vs benchmark": fmt.pp(r.get("vs_benchmark_pp")),
                "Drawdown": fmt.pct(r.get("drawdown_pct")),
            }
            for r in v["holdings"]
        ],
        hide_index=True,
        width="stretch",
    )
st.markdown("#### Best new ideas")
if v["ideas"]:
    st.dataframe(rows(v["ideas"]), hide_index=True, width="stretch")
else:
    st.caption("None this month.")
st.markdown("#### Score history")
lens = st.radio("Lens", ["value", "momentum"], horizontal=True, format_func=str.title)
matrix, cols = app_api.score_matrix(cap, lens)
UI.show(UI.score_heatmap(matrix[:25], cols))
st.markdown("#### All stocks, ranked")
st.dataframe(rows(v["ranked"]), hide_index=True, width="stretch")
