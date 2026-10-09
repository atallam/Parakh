"""Component gallery (dev only): every UI.* component from fixtures. It is also the test (AC-F22.4)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from ui import components as UI  # noqa: E402
from ui.page import setup  # noqa: E402

setup("Component gallery", icon="🧩")
st.caption(
    "Every status below is colour + icon + word. Developer page; not part of the daily flow."
)

st.markdown("##### Statuses")
for family, values in (
    (
        "verdict",
        [
            "STRONG_BUY",
            "BUY",
            "ACCUMULATE",
            "HOLD",
            "WATCH",
            "MOMENTUM_ONLY",
            "REDUCE",
            "SELL",
            "AVOID",
        ],
    ),
    ("position", ["ADD", "HOLD", "TRIM", "EXIT"]),
    ("thesis", ["INTACT", "WATCH", "BROKEN", "NOT_SET"]),
    ("concall", ["CONFIRMS", "NEUTRAL", "CHALLENGES", "BREAKS"]),
    ("check", ["CLEAN", "FLAGGED", "UNKNOWN"]),
    ("severity", ["HIGH", "MEDIUM", "LOW"]),
):
    UI.show(
        f"<b>{family}</b> &nbsp; "
        + " ".join(UI._chip(UI.status_style(family, v), v) for v in values)
    )

st.markdown("##### UI.verdict_chip · UI.owned_badge · UI.thesis_pill · UI.concall_pill")
UI.show(
    UI.verdict_chip("BUY", prev="HOLD", size="lg")
    + " &nbsp; "
    + UI.verdict_chip("HOLD", action="TRIM")
)
UI.show(UI.owned_badge(weight_pct=4.2, pnl_pct=14.6, masked=True))
UI.show(
    UI.owned_badge(weight_pct=4.2, pnl_pct=-3.1, masked=False, quantity=120, value_inr=1_920_000)
)
UI.show(UI.thesis_pill("WATCH") + " &nbsp; " + UI.concall_pill("Q1 FY27", "STRESSED"))

st.markdown("##### UI.score_ring · UI.range_bar · UI.sparkline")
UI.show(
    UI.score_ring(72, label="Value", delta=4)
    + UI.score_ring(31, label="Momentum", delta=-3)
    + UI.score_ring(None, label="Unknown")
)
UI.show(UI.range_bar(low=820, high=1310, cmp=1105, entry=990, fair_low=1000, fair_high=1250))
UI.show(
    UI.sparkline(
        [100, 104, 99, 110, 118, 112, 121, 130],
        dma50=[100, 101, 102, 104, 108, 110, 113, 118],
        avg_cost=105,
    )
)

st.markdown("##### UI.evidence_list · UI.check_row · UI.component_grid")
UI.show(
    UI.evidence_list(
        [
            "Momentum score 72 reached the BUY band",
            "Fair value 12% above price",
            "No red flags among 9 checks",
        ]
    )
)
UI.show(
    UI.check_row("Promoter pledge", "CLEAN")
    + UI.check_row("Auditor change", "FLAGGED", "new auditor appointed")
    + UI.check_row(
        "Related-party loans", "UNKNOWN", "couldn't check: filing not parsed · tried 2d ago"
    )
)
UI.show(
    UI.component_grid(
        [
            {
                "id": "KM1",
                "text": "Order book above 3x revenue",
                "status": "INTACT",
                "evidence": "Q1: 3.4x",
            },
            {
                "id": "KM2",
                "text": "EBITDA margin above 18%",
                "status": "WATCH",
                "evidence": "Q1: 17.6%",
            },
        ]
    )
)

st.markdown("##### UI.thesis_heatmap · UI.score_heatmap")
UI.show(
    UI.thesis_heatmap(
        [
            {
                "id": "KM1",
                "cells": {"Q2": "SUPPORTED", "Q3": "NEUTRAL", "Q4": "STRESSED", "Q1": "BREAKS"},
            }
        ],
        ["Q2", "Q3", "Q4", "Q1"],
    )
)
UI.show(
    UI.score_heatmap(
        [
            {
                "symbol": "INDIGO",
                "cells": {"2026-08": 71, "2026-09": 64, "2026-10": 38},
                "changed": {"2026-10": True},
            }
        ],
        ["2026-08", "2026-09", "2026-10"],
    )
)

st.markdown("##### UI.timeline · UI.count_chips · UI.stage_ladder")
UI.show(
    UI.timeline(
        [
            {"when": "2026-10", "text": "HOLD → BUY"},
            {"when": "2026-09", "text": "thesis INTACT → WATCH"},
        ]
    )
)
UI.show(UI.count_chips({"verdict changes": 4, "thesis alerts": 1, "approvals": 3}))
UI.show(
    UI.stage_ladder(
        [
            {"name": "list calls", "state": "done"},
            {"name": "fetch transcript", "state": "failed", "reason": "HTTP 503, retry"},
            {"name": "read", "state": "pending"},
        ]
    )
)

st.markdown(
    "##### UI.suggestion_card · UI.banner · UI.error_panel · UI.feedback · UI.privacy_toggle"
)
UI.show(
    UI.suggestion_card(
        {
            "symbol": "POLYCAB",
            "cap": "mid",
            "action": "add_my",
            "reason": "Top 10% combined score for 3 months",
            "origin": "rule",
            "sources": ["SRC.top_combined"],
            "expires_on": None,
        }
    )
)
UI.show(UI.banner("4 holdings without a thesis.", "Add them"))
UI.show(
    UI.error_panel(
        "Prices could not load",
        "Check your connection, then refresh. Last good data is from 3 Oct.",
    )
)
UI.feedback("gallery")
st.caption("Privacy toggle: top right of every page.")
