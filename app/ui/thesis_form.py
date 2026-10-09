"""The thesis form (plan 12 §5.3): four fields, original locked after the first save, skip allowed."""

from __future__ import annotations

import datetime as dt

import streamlit as st

from parakh.services import app_api
from parakh.thesis.editor import BreakerDraft, ThesisDraft

CHECKS = {
    "A number rule": "metric",
    "The concall agent flags it": "llm_flag",
    "I check it myself": "manual",
}


def render(symbol: str, key: str = "tf") -> bool:
    """Draw the form body for `symbol`. Returns True after a successful save."""
    cur = app_api.thesis_draft(symbol)
    locked = cur["locked"]
    st.caption(f"{symbol} · " + (f"working thesis v{cur['version']}" if locked else "first thesis"))
    if locked:
        st.info(
            f"Original ({cur['written_on']}): {cur['statement']}  \nThe original never changes; edits below are revisions."
        )
    statement = st.text_area(
        "Why I bought it",
        value="" if not locked else cur["statement"],
        key=f"{key}-why",
        help="In your words, on the day you bought it. Locked after the first save.",
    )
    metrics = st.text_area(
        "What to watch (one per line, up to 5)",
        value="\n".join(cur["key_metrics"]),
        key=f"{key}-km",
    )
    st.markdown("**What would make me sell** (up to 5)")
    breakers: list[BreakerDraft] = []
    existing = cur["breakers"] or []
    for i in range(5):
        row = existing[i] if i < len(existing) else {"text": "", "check": "llm_flag", "rule": ""}
        c1, c2, c3 = st.columns([4, 3, 3])
        text = c1.text_input(
            f"Condition {i + 1}",
            value=row["text"],
            key=f"{key}-bt{i}",
            label_visibility="collapsed" if i else "visible",
        )
        label = next(
            (k for k, v in CHECKS.items() if v == row["check"]), "The concall agent flags it"
        )
        how = c2.selectbox(
            "How",
            list(CHECKS),
            index=list(CHECKS).index(label),
            key=f"{key}-bc{i}",
            label_visibility="collapsed",
        )
        rule = c3.text_input(
            "Rule",
            value=row.get("rule", ""),
            key=f"{key}-br{i}",
            placeholder="revenue_growth_yoy_pct < -10",
            disabled=CHECKS[how] != "metric",
            label_visibility="collapsed",
        )
        if text.strip():
            breakers.append(
                BreakerDraft(
                    text=text.strip(),
                    check=CHECKS[how],  # type: ignore[arg-type]
                    rule=(rule or "").strip() or None,
                )
            )
    sizing = st.text_input("Why this size", value=cur["sizing"], key=f"{key}-size")
    review = st.date_input(
        "Review by", value=dt.date.today() + dt.timedelta(days=180), key=f"{key}-rev"
    )
    if st.button("Save thesis", type="primary", key=f"{key}-save"):
        lines = [m.strip() for m in metrics.splitlines() if m.strip()]
        if len(lines) > 5:
            st.error("At most 5 things to watch.")
            return False
        try:
            draft = ThesisDraft(
                statement=(statement or "").strip(),
                key_metrics=lines,
                breakers=breakers,
                sizing_rationale=(sizing or "").strip() or None,
                review_by=review,
            )
        except ValueError as exc:
            st.error(f"Check the form: {exc}")
            return False
        res = app_api.save_thesis_form(symbol, draft)
        if res.ok:
            st.success(
                f"Saved as version {res.version}."
                + (" Your edit is stored as a dated revision." if res.revised_statement else "")
            )
            return True
        for err in res.errors:
            st.error(err)
    return False


@st.dialog("Thesis", width="large")
def dialog(symbol: str) -> None:
    if render(symbol, key=f"tfd-{symbol}"):
        st.button("Close", key=f"tfd-close-{symbol}", on_click=st.rerun)
