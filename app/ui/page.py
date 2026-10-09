"""Shared page chrome: config, theme, header with the privacy toggle, and the import path for `ui`."""

from __future__ import annotations

import streamlit as st

from parakh import __version__

from . import components as UI
from . import theme


def setup(title: str, *, icon: str = "📈") -> bool:
    """Call first on every page. Returns True when the privacy view is on (amounts hidden)."""
    st.set_page_config(page_title=f"Parakh · {title}", page_icon=icon, layout="wide")
    theme.inject()
    left, right = st.columns([5, 1])
    left.markdown(f"## {title}")
    with right:
        masked = UI.privacy_toggle()
    st.caption(f"Parakh v{__version__} · personal analytical framework, not investment advice")
    return masked
