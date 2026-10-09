"""CSS from config/ui_tokens.yaml, injected once per page (plan 12 §3; AC-F22.1).

Colours exist here only as CSS variables built from the token file at run time, so a palette change is
one YAML edit and no hex colour appears in app code. Dark mode follows the browser (`prefers-color-scheme`).
"""

from __future__ import annotations

import streamlit as st

from parakh.render.tokens import tokens

_CSS = """
:root { %(light)s --font-ui: '%(ui)s', system-ui, sans-serif; --font-num: '%(num)s', ui-monospace, monospace; }
@media (prefers-color-scheme: dark) { :root { %(dark)s } }
.pk { font-family: var(--font-ui); color: var(--c-text); }
.pk .num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
.pk-chip { display:inline-flex; gap:.35rem; align-items:center; padding:.15rem .6rem; border-radius:999px;
  border:1.5px solid var(--chip); color: var(--chip); font-weight:600; font-size:.85rem; background: transparent; }
.pk-chip.fill { background: var(--chip); color: var(--c-bg_card); }
.pk-chip.lg { font-size:1.05rem; padding:.3rem .8rem; }
.pk-prev { color: var(--c-text_muted); font-weight:500; margin-right:.3rem; }
.pk-card { background: var(--c-bg_card); border:1px solid var(--c-border); border-radius:12px; padding:.9rem 1rem; margin:.4rem 0; }
.pk-muted { color: var(--c-text_muted); }
.pk-row { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap; }
.pk-banner { border-left:4px solid var(--c-caution); background: var(--c-bg_muted); padding:.6rem .9rem; border-radius:8px; margin:.4rem 0; }
.pk-err { border-left:4px solid var(--c-negative); background: var(--c-bg_muted); padding:.6rem .9rem; border-radius:8px; }
.pk-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:.6rem; }
.pk-km { border-left:5px solid var(--chip); background: var(--c-bg_card); border:1px solid var(--c-border);
  border-left:5px solid var(--chip); border-radius:8px; padding:.5rem .7rem; }
.pk-heat { border-collapse: collapse; width:100%%; font-size:.85rem; }
.pk-heat td, .pk-heat th { border:1px solid var(--c-border); padding:.25rem .45rem; text-align:center; }
.pk-heat td.cell { color: var(--chip); font-weight:600; }
.pk-count { display:inline-block; margin:.15rem .3rem .15rem 0; padding:.2rem .65rem; border-radius:8px; background: var(--c-bg_muted); border:1px solid var(--c-border); }
.pk-count b { font-family: var(--font-num); }
.pk-ev li { margin:.15rem 0; }
.pk-stage { display:flex; gap:.4rem; align-items:center; margin:.15rem 0; }
"""


def css() -> str:
    t = tokens()
    light = " ".join(f"--c-{k}: {v};" for k, v in t.colors.items())
    dark = " ".join(f"--c-{k}: {v};" for k, v in t.colors_dark.items())
    return _CSS % {
        "light": light,
        "dark": dark,
        "ui": t.fonts.get("ui", "DM Sans"),
        "num": t.fonts.get("numbers", "DM Mono"),
    }


def inject() -> None:
    st.markdown(f"<style>{css()}</style>", unsafe_allow_html=True)
