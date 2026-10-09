"""Component rules: colour + icon + word, tokens only, same style on every surface (AC-F22.1–F22.3, F22.5)."""

from __future__ import annotations

import re

import pytest
from app.ui import components as UI

from parakh.notify.templates import (
    fit_lines,  # noqa: F401  (the Telegram side uses the same tokens)
)
from parakh.render import format as fmt
from parakh.render.tokens import label, status, tokens
from parakh.services.reports import verdict_label

FAMILIES = {f: list(v) for f, v in tokens().statuses.items()}


@pytest.mark.ac("AC-F22.2")
@pytest.mark.parametrize("family,key", [(f, k) for f, ks in FAMILIES.items() for k in ks])
def test_every_status_carries_colour_icon_and_word(family, key) -> None:
    html = UI._chip(UI.status_style(family, key), key)
    s = status(family, key)
    assert s.icon in html and s.word in html and f"var(--c-{s.token})" in html


@pytest.mark.ac("AC-F22.2")
def test_statuses_are_distinguishable_without_colour() -> None:
    for family, keys in FAMILIES.items():
        texts = {label(status(family, k)) for k in keys}
        assert len(texts) == len(keys), f"{family}: two statuses share icon and word"


@pytest.mark.ac("AC-F22.1")
def test_components_emit_no_hex_colours() -> None:
    samples = [
        UI.verdict_chip("BUY", prev="HOLD"),
        UI.score_ring(70, label="Value", delta=2),
        UI.range_bar(low=1, high=2, cmp=1.5, entry=1.2, fair_low=1.1, fair_high=1.8),
        UI.sparkline([1, 2, 3], avg_cost=2),
        UI.score_heatmap([{"symbol": "A", "cells": {"m": 50}}], ["m"]),
        UI.thesis_heatmap([{"id": "KM1", "cells": {"q": "BREAKS"}}], ["q"]),
    ]
    assert not [s for s in samples if re.search(r"#[0-9a-fA-F]{6}\b", s)]


@pytest.mark.ac("AC-F22.3")
def test_streamlit_and_telegram_use_the_same_words() -> None:
    for verdict in ("BUY", "HOLD", "SELL", "WATCH"):
        word = status("verdict", verdict).word
        assert word in UI.verdict_chip(verdict) and word in verdict_label(verdict)


@pytest.mark.ac("AC-F22.5")
def test_money_formats_match_the_shared_formatter() -> None:
    assert fmt.inr(1_920_000, compact=True) in UI.owned_badge(
        weight_pct=1, pnl_pct=1, masked=False, value_inr=1_920_000
    )
    assert "—" in UI.score_ring(None, label="Value")  # unknown is a dash, never 0


def test_a_masked_badge_hides_amounts() -> None:
    html = UI.owned_badge(
        weight_pct=4.2, pnl_pct=10, masked=True, quantity=120, value_inr=1_920_000
    )
    assert "120" not in html and "19.2" not in html


def test_unknown_check_is_never_shown_clean() -> None:
    assert "UNKNOWN" in UI.check_row(
        "Pledge", "UNKNOWN", "couldn't check"
    ) and "CLEAN" not in UI.check_row("Pledge", "UNKNOWN")


def test_html_is_escaped() -> None:
    assert "<script>" not in UI.banner("<script>alert(1)</script>")
