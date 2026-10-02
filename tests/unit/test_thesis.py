"""THESIS.md: schema, safe rule language, status (F23; AC-F09.9)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from parakh.configs import load_all
from parakh.orchestration.analysis import run_monthly
from parakh.snapshots.store import snapshot_path, stock_dir
from parakh.thesis import rules
from parakh.thesis.model import parse_text
from tests.helpers.pilot import END, pilot_data

ISIN = "INE040A01034"


def thesis_text(breakers: str = "", review_by: str = "2027-03-31", extra: str = "") -> str:
    return f"""---
symbol: HDFCBANK
isin: {ISIN}
thesis_version: 1
original:
  written_on: 2026-01-15
  statement: "Compounding franchise; merger digestion should lift returns."
key_metrics:
  - {{id: KM1, text: Loan growth ahead of the system}}
breakers:
{breakers}
review_by: {review_by}
sizing_rationale: "Core holding; 10% cap."
{extra}---
Body notes.
"""


def test_a_valid_thesis_parses() -> None:
    p = parse_text(
        thesis_text(
            "  - {id: BR1, text: Growth stalls, check: metric, rule: 'revenue_growth_yoy_pct < -10'}"
        )
    )
    assert p.front is not None and not p.errors
    assert p.front.breakers[0].rule == "revenue_growth_yoy_pct < -10"


@pytest.mark.parametrize(
    "text",
    [
        "no front matter at all",
        thesis_text("  - {id: BR9, text: bad id, check: metric, rule: 'price < 1'}"),
        thesis_text("  - {id: BR1, text: metric without rule, check: metric}"),
        thesis_text("  - {id: BR1, text: flag with rule, check: llm_flag, rule: 'price < 1'}"),
    ],
)
def test_an_invalid_thesis_is_reported_not_raised(text: str) -> None:
    p = parse_text(text)
    assert p.front is None and p.errors


@pytest.mark.parametrize(
    ("rule", "values", "expected"),
    [
        ("a < 5", {"a": 3.0}, True),
        ("a < 5", {"a": 7.0}, False),
        ("a < 5 and b > 1", {"a": 3.0, "b": 0.0}, False),
        ("a < 5 or b > 1", {"a": 9.0, "b": 2.0}, True),
        ("(a < 5 or b > 1) and c >= 0", {"a": 9.0, "b": 0.0, "c": 1.0}, False),
    ],
)
def test_rules_evaluate_without_eval(rule: str, values: dict, expected: bool) -> None:
    assert rules.evaluate(rule, values.get).value is expected


def test_unknown_is_never_false() -> None:
    assert rules.evaluate("a < 5", {}.get).value is None
    assert rules.evaluate("a < 5 or b > 1", {"b": 2.0}.get).value is True  # True or UNKNOWN
    assert rules.evaluate("a < 5 and b > 1", {"b": 0.0}.get).value is False  # False and UNKNOWN
    assert rules.evaluate("a < 5 and b > 1", {"b": 2.0}.get).value is None


@pytest.mark.parametrize("rule", ["__import__('os')", "a < 5; b", "a ** 2 < 5", "price <"])
def test_rules_refuse_anything_but_comparisons(rule: str) -> None:
    with pytest.raises(rules.RuleError):
        rules.evaluate(rule, {"price": 1.0}.get)


def _month(tmp_path, text: str | None, asof=END, owned: bool = True):
    from parakh.holdings.lots import Lot

    bundle = load_all()
    sec = next(s for s in bundle.universe.pilot if s.isin == ISIN)
    if text is not None:
        d = stock_dir(sec.cap, sec.symbol, tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "THESIS.md").write_text(text, encoding="utf-8")
    data = pilot_data(bundle)
    if owned:
        data.lots = [
            Lot("L1", "acct", ISIN, 100.0, dt.date(2025, 1, 10), dt.date(2025, 1, 11), 150.0, "cli")
        ]
    res = run_monthly(bundle, data, asof, out_root=tmp_path)
    snap = next(s for s in res.snapshots if s.isin == ISIN)
    return snap, res


@pytest.mark.ac("AC-F23.1")
def test_a_met_metric_breaker_sets_broken_with_evidence(tmp_path) -> None:
    snap, _ = _month(
        tmp_path,
        thesis_text("  - {id: BR1, text: Price above 1, check: metric, rule: 'price > 1'}"),
    )
    th = snap.thesis
    assert th["status"] == "BROKEN"
    b = th["breakers"][0]
    assert b["state"] == "FLAGGED" and b["evidence"]["price"] > 1
    assert snap.verdict["action"] == "EXIT"  # thesis_broken_action


@pytest.mark.ac("AC-F23.2")
def test_an_llm_flag_never_breaks_a_thesis_on_its_own(tmp_path) -> None:
    snap, _ = _month(
        tmp_path, thesis_text("  - {id: BR1, text: Mgmt integrity concern, check: llm_flag}")
    )
    assert snap.thesis["status"] == "INTACT"
    assert snap.thesis["breakers"][0]["state"] == "UNKNOWN"
    assert snap.thesis["unchecked"] >= 1


@pytest.mark.ac("AC-F23.5")
def test_no_thesis_means_not_set_and_still_a_verdict(tmp_path) -> None:
    snap, _ = _month(tmp_path, None, owned=False)
    assert snap.thesis["status"] == "NOT_SET" and snap.thesis["present"] is False
    assert snap.verdict["verdict"]


@pytest.mark.ac("AC-F23.7")
def test_a_thesis_past_review_by_is_flagged_due(tmp_path) -> None:
    snap, _ = _month(
        tmp_path,
        thesis_text(
            "  - {id: BR1, text: Growth stalls, check: metric, rule: 'price < 0'}",
            review_by="2026-06-30",
        ),
    )
    assert snap.thesis["review_due"] is True


@pytest.mark.ac("AC-F23.3")
def test_a_status_change_writes_one_event_and_a_timeline_entry(tmp_path) -> None:
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD

    ok = thesis_text("  - {id: BR1, text: Price above 1, check: metric, rule: 'price < 0'}")
    _month(tmp_path, ok, dt.date(2026, 8, 31))
    broken = thesis_text("  - {id: BR1, text: Price above 1, check: metric, rule: 'price > 1'}")
    snap, res = _month(tmp_path, broken)
    changes = [
        e for e in get_sink().events_for_run(res.ctx.run_id) if e.event_type == AUD.THESIS_CHANGED
    ]
    assert len(changes) == 1
    assert changes[0].before == {"status": "INTACT"} and changes[0].after == {"status": "BROKEN"}
    assert snap.thesis["changed_from"] == "INTACT"
    assert [t["status"] for t in snap.thesis["timeline"]] == ["INTACT", "BROKEN"]
    saved = json.loads(snapshot_path(snap.cap, snap.symbol, "2026-09", tmp_path).read_text())
    assert saved["thesis"]["status"] == "BROKEN"


def test_an_unknown_variable_is_rejected_when_validating(tmp_path) -> None:
    snap, _ = _month(
        tmp_path,
        thesis_text(
            "  - {id: BR1, text: Bad variable, check: metric, rule: 'nonsense_metric < 3'}"
        ),
    )
    assert snap.thesis["valid"] is False and snap.thesis["status"] == "NOT_SET"
    assert any("nonsense_metric" in e for e in snap.thesis["errors"])
