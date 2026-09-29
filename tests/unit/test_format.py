"""Shared formatters and status tokens (plan 12 §3; AC-F22.3, AC-F22.5). T-UI-01…"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from parakh.render import format as f
from parakh.render.tokens import label, status


@pytest.mark.ac("AC-F22.5")
@pytest.mark.parametrize(
    ("value", "compact", "expected"),
    [
        (0, False, "₹0"),
        (999, False, "₹999"),
        (1_000, False, "₹1,000"),
        (99_999, False, "₹99,999"),
        (1_00_000, False, "₹1,00,000"),
        (19_20_000, False, "₹19,20,000"),
        (12_34_56_789, False, "₹12,34,56,789"),
        (-19_20_000, False, "−₹19,20,000"),
        (99_999, True, "₹99,999"),  # below 1 L compact stays in full
        (1_00_000, True, "₹1.0 L"),
        (19_20_000, True, "₹19.2 L"),
        (99_94_999, True, "₹99.9 L"),
        (99_99_999, True, "₹1.0 Cr"),  # rounds to 100 L → shown as crore
        (1_00_00_000, True, "₹1.0 Cr"),
        (12_40_00_000, True, "₹12.4 Cr"),
        (123_450_000_000, True, "₹12,345.0 Cr"),
        (-12_40_00_000, True, "−₹12.4 Cr"),
    ],
)
def test_inr(value: float, compact: bool, expected: str) -> None:
    """T-UI-01: lakh and crore boundaries."""
    assert f.inr(value, compact=compact) == expected


@pytest.mark.ac("AC-F22.5")
def test_percentages_multiples_and_missing() -> None:
    """T-UI-02"""
    assert f.pct(4.6) == "+4.6%"
    assert f.pct(-3.04) == "−3.0%"
    assert f.pct(0.0) == "0.0%"
    assert f.pct(4.6, signed=False) == "4.6%"
    assert f.ratio_pct(0.046) == "+4.6%"
    assert f.pp(2.1) == "+2.1 pp"
    assert f.mult(24.3) == "24.3×"
    for fn in (f.inr, f.pct, f.ratio_pct, f.pp, f.mult):
        assert fn(None) == f.MISSING
        assert fn(math.nan) == f.MISSING  # unknown is never shown as 0 (UX-05)


@pytest.mark.ac("AC-F22.5")
def test_dates_and_times() -> None:
    """T-UI-03"""
    assert f.date(dt.date(2026, 9, 24)) == "24 Sep 2026"
    assert f.date(dt.date(2026, 9, 5)) == "5 Sep 2026"
    assert f.time_ist(dt.datetime(2026, 9, 24, 13, 0, tzinfo=dt.UTC)) == "18:30 IST"
    now = dt.datetime(2026, 9, 29, 12, 0, tzinfo=dt.UTC)
    assert f.relative(now - dt.timedelta(seconds=10), now) == "just now"
    assert f.relative(now - dt.timedelta(minutes=12), now) == "12m ago"
    assert f.relative(now - dt.timedelta(hours=5), now) == "5h ago"
    assert f.relative(now - dt.timedelta(days=3), now) == "3d ago"
    assert f.relative(now - dt.timedelta(days=40), now) == "20 Aug 2026"


@pytest.mark.ac("AC-F22.3")
def test_status_styles_come_from_tokens() -> None:
    """T-UI-04: one lookup for every surface; colour is never the only carrier."""
    buy = status("verdict", "BUY")
    assert buy.token == "positive"
    assert buy.color.startswith("#")
    assert label(buy) == "🟢 ▲ BUY"
    assert status("verdict", "strong buy").word == "STRONG BUY"
    assert status("thesis", "BROKEN").token == status("verdict", "SELL").token == "negative"
    with pytest.raises(KeyError):
        status("verdict", "MOON")
