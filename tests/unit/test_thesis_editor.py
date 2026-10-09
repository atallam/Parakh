"""The thesis form's writer: original locked, revisions kept, rules checked (AC-F15.9, F09.9, F23)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.thesis.editor import BreakerDraft, ThesisDraft, save_thesis
from parakh.thesis.model import read_thesis

ISIN = "INE646L01027"
DAY = dt.date(2026, 10, 5)
KNOWN = {"revenue_growth_yoy_pct", "roce_pct"}


def draft(**kw):  # type: ignore[no-untyped-def]
    base = {
        "statement": "A low-cost carrier compounding on market share.",
        "key_metrics": ["Capacity growth above 10%"],
        "breakers": [
            BreakerDraft(text="Revenue falls", check="metric", rule="revenue_growth_yoy_pct < -10")
        ],
        "sizing_rationale": "Quality, but cyclical.",
    }
    return ThesisDraft(**{**base, **kw})


@pytest.mark.ac("AC-F15.9")
def test_first_save_writes_a_valid_thesis_and_one_audit_event(tmp_path) -> None:
    path = tmp_path / "INDIGO" / "THESIS.md"
    res = save_thesis(
        path, symbol="INDIGO", isin=ISIN, draft=draft(), today=DAY, known_variables=KNOWN
    )
    assert res.ok and res.version == 1
    parsed = read_thesis(path)
    assert parsed.front and parsed.front.original.written_on == DAY and not parsed.errors
    events = [e for e in get_sink().events() if e.event_type == AUD.THESIS_CHANGED]
    assert len(events) == 1 and "compounding" not in str(
        events[0].details
    )  # versions and counts only


@pytest.mark.ac("AC-F15.9")
def test_the_original_never_changes_and_an_edit_becomes_a_revision(tmp_path) -> None:
    path = tmp_path / "THESIS.md"
    save_thesis(path, symbol="INDIGO", isin=ISIN, draft=draft(), today=DAY, known_variables=KNOWN)
    first = read_thesis(path).front.original.statement  # type: ignore[union-attr]
    later = dt.date(2027, 1, 10)
    res = save_thesis(
        path,
        symbol="INDIGO",
        isin=ISIN,
        draft=draft(statement="Now also a cargo story, in my words."),
        today=later,
        known_variables=KNOWN,
    )
    assert res.ok and res.version == 2 and res.revised_statement
    parsed = read_thesis(path)
    assert parsed.front.original.statement == first and parsed.front.thesis_version == 2  # type: ignore[union-attr]
    assert "Revision 2 (2027-01-10)" in parsed.body and "cargo story" in parsed.body


@pytest.mark.ac("AC-F09.9")
@pytest.mark.parametrize(
    "bad",
    [
        {
            "breakers": [
                BreakerDraft(text="Revenue falls", check="metric", rule="made_up_metric < 1")
            ]
        },
        {
            "breakers": [
                BreakerDraft(text="Revenue falls", check="metric", rule="revenue_growth_yoy_pct <")
            ]
        },
        {"breakers": [BreakerDraft(text="Revenue falls", check="metric", rule=None)]},
    ],
)
def test_a_bad_rule_writes_nothing(tmp_path, bad) -> None:
    path = tmp_path / "THESIS.md"
    res = save_thesis(
        path, symbol="INDIGO", isin=ISIN, draft=draft(**bad), today=DAY, known_variables=KNOWN
    )
    assert not res.ok and res.errors and not path.exists()


def test_more_than_five_items_is_refused_by_the_model() -> None:
    with pytest.raises(ValueError):
        draft(key_metrics=[f"m{i}" for i in range(6)])


def test_a_flag_breaker_has_no_rule(tmp_path) -> None:
    path = tmp_path / "THESIS.md"
    res = save_thesis(
        path, symbol="INDIGO", isin=ISIN, today=DAY, known_variables=KNOWN,
        draft=draft(breakers=[BreakerDraft(text="Management tone turns evasive", check="llm_flag", rule="ignored < 1")]),
    )  # fmt: skip
    assert res.ok and read_thesis(path).front.breakers[0].rule is None  # type: ignore[union-attr]
