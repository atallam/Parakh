"""Review inbox: everything since your last review, owned first (plan 12 §5.1; AC-F15.8).

Run: uv run streamlit run app/Home.py. The page calls services only, never the model or the network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.services import app_api  # noqa: E402

setup("Review inbox", icon="📥")
app_api.open_review_window()
try:
    view = app_api.inbox()
except Exception as exc:  # a region-level error with the next step, never a blank page (UX-10)
    UI.show(
        UI.error_panel(
            "The inbox could not load",
            f"{type(exc).__name__}. Run `parakh run --mode monthly`, then refresh.",
        )
    )
    st.stop()

if view.theses_missing:
    UI.show(
        UI.banner(
            f"{view.theses_missing} holding(s) without a thesis.", "Add them on the Holdings page."
        )
    )
if view.pending_approvals:
    UI.show(
        UI.banner(
            f"{view.pending_approvals} suggestion(s) waiting for your decision.",
            "Open Watchlist Review.",
        )
    )

st.markdown("##### Since your last review" + (f" · {view.period}" if view.period else ""))
UI.show(UI.count_chips(view.counts))
st.progress(
    view.reviewed / view.total if view.total else 1.0,
    text=f"{view.reviewed} of {view.total} reviewed",
)

unseen = [i for i in view.items if not i.seen]
if not view.items:
    st.info(
        "Nothing here yet. After the next monthly run, verdict changes, thesis alerts and approvals appear in this list."
    )
if unseen and st.button("Mark all reviewed", type="primary"):
    app_api.mark_reviewed([i.key for i in unseen])
    st.rerun()

for n, item in enumerate(view.items):
    with st.container(border=True):
        c1, c2 = st.columns([8, 2])
        tag = "🟢 OWNED · " if item.owned else ""
        c1.markdown(f"**{item.title}**" + (" · ✔ reviewed" if item.seen else ""))
        c1.caption(f"{tag}{item.detail}")
        if item.symbol:
            c2.page_link(
                "pages/4_Stock_Detail.py", label="Open ▸", query_params={"symbol": item.symbol}
            )
        if not item.seen and c2.button("Mark reviewed", key=f"mr-{n}"):
            app_api.mark_reviewed([item.key])
            st.rerun()

st.divider()
st.caption(view.governance)
