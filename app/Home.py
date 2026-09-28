"""Streamlit entry point: uv run streamlit run app/Home.py

Keep the UI thin: pages call services, never the LLM or the database directly.
"""

import streamlit as st

from parakh import __version__

st.set_page_config(page_title="Parakh", layout="wide")
st.title("Parakh")
st.caption(f"v{__version__}")
st.info("Scaffolded by aiscaffold. Add pages under app/pages/.")
