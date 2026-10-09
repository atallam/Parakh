"""Audit and governance, minimal (plan 10; F15): integrity, recent events, overrides, agents."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui.page import setup  # noqa: E402

from parakh.services import app_api  # noqa: E402

setup("Audit and governance", icon="🛡")
a = app_api.audit()
if a.chain_ok:
    st.success(f"Integrity ✅ · {a.events} events · head {a.head}…")
else:
    UI.show(
        UI.error_panel(
            "The audit chain is broken",
            "Do not trust recent decisions until it is checked. Run `parakh audit verify`.",
        )
    )
st.markdown("#### Agents")
st.dataframe(a.agents, hide_index=True, width="stretch")
st.caption(
    "Agents run in shadow mode (output logged, not acted on) while dry_run is true. They can only propose; you approve."
)
st.markdown("#### Overrides expiring within 30 days")
if a.overrides_expiring:
    st.dataframe(a.overrides_expiring, hide_index=True, width="stretch")
else:
    st.caption("None.")
st.markdown("#### Recent events")
kind = st.text_input("Filter by event type", placeholder="AUD.WATCHLIST")
rows = [r for r in a.recent if kind.upper() in r["type"]] if kind else a.recent
if rows:
    st.dataframe(rows, hide_index=True, width="stretch")
else:
    st.caption("No events match.")
