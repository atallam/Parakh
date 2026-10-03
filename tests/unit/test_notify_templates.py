"""Message presentation: ≤ 10 lines, vocabulary, masking, agent notes (AC-F11.6, AC-F11.7)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.notify.model import Severity
from parakh.notify.templates import (
    MAX_LINES,
    MonthlySummaryVars,
    ReviewItem,
    fit_lines,
    render_alerts,
    render_digest,
    render_failure,
    render_heartbeat,
    render_monthly_review,
    render_monthly_summary,
    sanitize_note,
)
from tests.helpers.notify import alert

DAY = dt.date(2026, 10, 5)


@pytest.mark.ac("AC-F11.6")
def test_every_template_is_at_most_ten_lines_and_ends_items_with_open() -> None:
    many = [alert("M21", symbol=f"S{i}", isin=f"X{i}") for i in range(30)]
    ids = [f"id{i}" for i in range(30)]
    for msg in (
        render_alerts(many, ids, day=DAY),
        render_digest(many, ids, day=DAY),
        render_heartbeat(5, 5, 2, [f"warn {i}" for i in range(20)], DAY),
        render_failure("monthly", "regime", "x" * 500, "01JB6X"),
    ):
        assert len(msg.lines) <= MAX_LINES, msg.template_id
    one = render_alerts([alert("M21")], ["a1"], day=DAY)
    assert all("Open ▸" in line for line in one.lines[1:])


def test_vocabulary_is_emoji_plus_word_and_owned_shows_percentages_only() -> None:
    msg = render_alerts([alert("M21")], ["a1"], day=DAY)
    text = msg.text
    assert "🟢 OWNED" in text and "wt 12.0%" in text and "P&amp;L +18.4%" in text
    assert "🔴" in text and "M21" in text
    assert "₹" not in text


@pytest.mark.ac("AC-F11.7")
def test_no_amount_or_quantity_in_any_default_message() -> None:
    summary = MonthlySummaryVars(
        period="Oct 2026", stocks=7, seconds=492, regimes={"large": "Risk-On"},
        owned_attention=["INDIGO ⚪ HOLD→🟡 TRIM"], upgrades=["GROWW HOLD→BUY"], downgrades=[],
        red_flags=["MAZDOCK pledge"], inbox_items=4, data_warnings=1, unknown_checks=2,
        governance="🛡 Integrity ✅ · DQ 96%",
    )
    texts = [
        render_monthly_summary(summary).text,
        render_alerts([alert("M21", note="Pledge rose 8 pts to 27 pct")], ["a"], day=DAY).text,
        render_digest([alert("M12", owned=False, severity=Severity.MEDIUM)], ["a"], day=DAY).text,
    ]
    for t in texts:
        assert "₹" not in t and "shares" not in t.lower()


def test_html_in_data_is_escaped_so_m_and_m_cannot_break_a_message() -> None:
    msg = render_alerts([alert("M21", symbol="M&M", headline="a <b>bad</b> & worse")], ["a"], day=DAY)
    assert "M&amp;M" in msg.text and "<b>bad</b>" not in msg.text and "&amp; worse" in msg.text


@pytest.mark.parametrize(
    ("note", "ok"),
    [
        ("Auditor resigned citing workload; thesis item 2 is exposed.", True),
        ("Position worth ₹4.2 L is at risk", False),
        ("Sold 1,200 shares last week", False),
        ("Rs. 500 crore order win", False),
        ("See https://evil.example/x for details", False),
        ("<script>alert(1)</script>Rating cut to BBB", True),
        ("", False),
    ],
)
def test_agent_notes_are_checked_before_they_are_shown(note, ok) -> None:
    out = sanitize_note(note)
    assert (out is not None) is ok
    if out:
        assert "<" not in out


def test_agent_notes_are_clipped_and_marked_as_agent_written() -> None:
    long_note = "word " * 100
    clipped = sanitize_note(long_note)
    assert clipped is not None and len(clipped) <= 140
    msg = render_alerts([alert("E07", kind="event", note="Downgrade is one notch")], ["a"], day=DAY)
    assert "🤖 Downgrade is one notch" in msg.text


def test_buttons_are_one_row_per_item_up_to_five() -> None:
    msg = render_alerts([alert("M21", symbol=f"S{i}", isin=f"X{i}") for i in range(7)], [f"i{i}" for i in range(7)], day=DAY)
    assert len(msg.buttons) == 5
    assert [b.action for b in msg.buttons[0]] == ["u", "n", "m"]


def test_low_only_digest_is_silent_and_a_high_item_makes_it_loud() -> None:
    low = render_digest([alert("M24", severity=Severity.LOW, owned=False)], ["a"], day=DAY)
    assert low.silent
    mixed = render_digest([alert("M24", severity=Severity.LOW), alert("M21")], ["a", "b"], day=DAY)
    assert not mixed.silent


def test_heartbeat_is_silent() -> None:
    assert render_heartbeat(5, 5, 0, [], DAY).silent


def test_monthly_review_drops_unsafe_notes_and_returns_none_when_nothing_is_left() -> None:
    items = [ReviewItem("INDIGO", "act", "Lease liabilities up; check thesis 2."), ReviewItem("M&M", "watch", "Worth ₹5 Cr")]
    msg = render_monthly_review(items, period="Oct 2026")
    assert msg is not None and "INDIGO" in msg.text and "M&amp;M" not in msg.text
    assert render_monthly_review([ReviewItem("X", "info", "₹5 Cr")], period="Oct 2026") is None


def test_fit_lines_keeps_header_and_footer() -> None:
    lines = [f"l{i}" for i in range(15)]
    out = fit_lines(lines, keep_tail=2)
    assert len(out) == MAX_LINES and out[0] == "l0" and out[-2:] == ["l13", "l14"] and "more" in out[-3]
