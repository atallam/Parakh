"""Watchlist review: approve, reject or snooze suggestions; manage My Watchlist (plan 06 §5; AC-F15.1, F15.2)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui import thesis_form  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.render import format as fmt  # noqa: E402
from parakh.services import app_api  # noqa: E402
from parakh.services.watchlist import WatchlistError  # noqa: E402

setup("Watchlist review", icon="🗂")
svc = app_api.watch_service()
view = app_api.watchlist()

cols = st.columns(3)
for col, cap in zip(cols, ("large", "mid", "small"), strict=True):
    used, room = view.used.get(cap, 0), view.capacity.get(cap, 0)
    col.metric(f"{cap.title()} cap · System Watchlist", f"{used} / {room}")
    col.progress(min(used / room, 1.0) if room else 0.0)

pending = sorted(svc.pending(), key=lambda s: (s.expires_on, s.symbol))
st.markdown(f"#### Waiting for you ({len(pending)})")
if not pending:
    st.success("No suggestions waiting. The monthly review adds new ones when sources change.")
for s in pending:
    with st.container(border=True):
        UI.show(UI.suggestion_card({**s.model_dump(), "expires_on": s.expires_on}))
        note = st.text_input("Note (optional)", key=f"note-{s.sugg_id}")
        a, r, z = st.columns(3)
        try:
            if a.button("✅ Approve", key=f"a-{s.sugg_id}"):
                res = svc.approve(s.sugg_id, channel="streamlit", note=note or None)
                st.toast(res.message)
                if res.needs_thesis:
                    thesis_form.dialog(s.symbol)
                else:
                    st.rerun()
            if r.button("❌ Reject", key=f"r-{s.sugg_id}"):
                st.toast(svc.reject(s.sugg_id, channel="streamlit", note=note or None).message)
                st.rerun()
            if z.button("💤 Snooze 30 days", key=f"z-{s.sugg_id}"):
                st.toast(svc.snooze(s.sugg_id, channel="streamlit").message)
                st.rerun()
        except WatchlistError as exc:
            UI.show(UI.error_panel("That did not go through", str(exc)))

my_tab, sys_tab, add_tab = st.tabs(["My Watchlist", "System Watchlist", "Add a stock"])
with my_tab:
    mine = view.state.open_entries(kind="my")
    if not mine:
        st.info("Nothing on My Watchlist yet. Approve a suggestion or add a stock.")
    for e in mine:
        with st.container(border=True):
            c1, c2 = st.columns([6, 2])
            c1.markdown(f"**{e.symbol}** · {e.cap.title()} · added {fmt.date(e.added_on)}")
            c1.caption(
                e.reason + (f" · ⚑ {', '.join(e.flags)}" if getattr(e, "flags", None) else "")
            )
            if c2.button("Remove", key=f"rm-{e.entry_id}"):
                st.session_state[f"rm-open-{e.entry_id}"] = True
            if st.session_state.get(f"rm-open-{e.entry_id}"):
                why = st.text_input("Why remove it?", key=f"rm-why-{e.entry_id}")
                if st.button("Confirm removal", key=f"rm-ok-{e.entry_id}"):
                    try:
                        svc.remove_my(e.symbol, reason=why, channel="streamlit")
                        st.rerun()
                    except WatchlistError as exc:
                        st.error(str(exc))
with sys_tab:
    for cap in ("large", "mid", "small"):
        rows = view.state.open_entries(cap=cap, kind="system")
        st.markdown(f"**{cap.title()}** · {len(rows)} of {view.capacity[cap]}")
        if rows:
            st.dataframe(
                [
                    {
                        "Stock": e.symbol,
                        "Since": fmt.date(e.added_on),
                        "Sources": ", ".join(e.sources),
                        "Why": e.reason,
                    }
                    for e in rows
                ],
                hide_index=True,
                width="stretch",
            )
with add_tab:
    st.caption("A reason is required. Lookup works by symbol or company name.")
    query = st.selectbox("Stock", [""] + app_api.universe_options(), key="add-sym")
    reason = st.text_area("Why add it?", key="add-why")
    if st.button("Add to My Watchlist", type="primary"):
        if not query or len(reason.strip()) < 10:
            st.error("Pick a stock and give a reason of at least a sentence.")
        else:
            try:
                res = svc.add_my(query, reason=reason.strip(), channel="streamlit")
                st.success(res.message)
                if getattr(res, "needs_thesis", False):
                    thesis_form.dialog(query)
            except WatchlistError as exc:
                st.error(str(exc))
