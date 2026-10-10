"""Calibration: your decision journal, alert ratings and the latest calibration report (F17; AC-F17.3 to F17.5)."""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.calibration.journal import JournalError  # noqa: E402
from parakh.render import format as fmt  # noqa: E402
from parakh.services import app_api  # noqa: E402
from parakh.services.alert_feedback import FeedbackError  # noqa: E402

setup("Calibration", icon="🎯")
view = app_api.calibration_view()
svc = app_api.journal_service()

tab_j, tab_a, tab_r = st.tabs(["Decision journal", "Rate alerts", "Calibration report"])

with tab_j:
    if view.due:
        st.markdown(f"#### Due for review ({len(view.due)})")
    for e in view.due:
        with st.container(border=True):
            st.markdown(f"**{e.symbol}** · {e.action} on {fmt.date(e.decided_on)}")
            st.caption(f"Why: {e.reason}  \nExpected: {e.expected}")
            verdict = st.radio(
                "How did it turn out?", ["right", "mixed", "wrong", "too_early"],
                horizontal=True, key=f"v-{e.entry_id}",
            )  # fmt: skip
            note = st.text_input("What happened (no amounts)", key=f"n-{e.entry_id}")
            if st.button("Save review", key=f"s-{e.entry_id}"):
                try:
                    svc.review(e.entry_id, verdict=verdict, note=note, channel="streamlit")
                    st.rerun()
                except JournalError as exc:
                    UI.show(UI.error_panel("That did not go through", str(exc)))
    if not view.due:
        st.success("No reviews due.")
    with (
        st.expander("Add an entry", expanded=not view.entries),
        st.form("journal-add", clear_on_submit=True),
    ):
        stock = st.text_input("Stock (symbol)")
        action = st.selectbox("What did you decide?", view.actions)
        reason = st.text_input("Why (one line, no amounts)")
        expected = st.text_input("What do you expect to happen?")
        review_on = st.date_input("Review on", dt.date.today() + dt.timedelta(days=91))
        if st.form_submit_button("Save"):
            try:
                e = svc.add(
                    stock, action=action, reason=reason, expected=expected,
                    review_on=review_on, channel="streamlit",
                )  # fmt: skip
                st.toast(f"Saved. Review on {fmt.date(e.review_on)}.")
                st.rerun()
            except JournalError as exc:
                UI.show(UI.error_panel("That did not go through", str(exc)))
    s = view.journal_stats
    if s.get("entries"):
        right = s.get("right_pct")
        st.caption(
            f"{s['entries']} entries · {s['reviewed']} reviewed · {s['open']} open"
            + (f" · judged right {right:.0f}%" if right is not None else "")
        )
    for e in view.entries:
        if e.status == "reviewed":
            st.markdown(f"- {e.symbol} · {e.action} · **{e.verdict}** · {e.outcome_note}")

with tab_a:
    p = view.precision
    if p.get("alerts"):
        pct = p.get("precision_pct")
        st.metric(
            "Alerts judged useful",
            "not enough ratings" if pct is None else f"{pct:.0f}%",
            help=f"Target {p['target_pct']:.0f}% or more. {p['rated']} of {p['alerts']} alerts rated.",
        )
    if not view.alerts_to_rate:
        st.info("Nothing waiting for a rating. New alerts appear here after they are sent.")
    for a in view.alerts_to_rate:
        with st.container(border=True):
            st.markdown(
                f"**{a.get('symbol') or a.get('isin')}** · {a.get('code')} · {a.get('asof')}"
            )
            tag = st.selectbox("If noise, why?", ["", *view.tags], key=f"t-{a['alert_id']}")
            up, down = st.columns(2)
            try:
                if up.button("👍 Useful", key=f"u-{a['alert_id']}"):
                    app_api.rate_alert(a["alert_id"], True)
                    st.rerun()
                if down.button("👎 Noise", key=f"d-{a['alert_id']}"):
                    app_api.rate_alert(a["alert_id"], False, tag or None)
                    st.rerun()
            except FeedbackError as exc:
                UI.show(UI.error_panel("That did not go through", str(exc)))

with tab_r:
    if view.report_quarter:
        st.caption(
            f"Report for {view.report_quarter}. Read-only: weights change only through a PR."
        )
        st.markdown(view.report_markdown)
    else:
        st.info(
            "No report yet. Run `parakh calibrate report --write` once prices and index membership "
            "history are loaded."
        )
