"""Report, history, segment summary and share export (F09, F10; UX-05, UX-11)."""

from __future__ import annotations

import csv
import datetime as dt
import re

import pytest

from parakh.configs import load_all
from parakh.holdings.lots import Lot
from parakh.orchestration.analysis import run_monthly
from parakh.orchestration.render_outputs import render_month
from parakh.render.report import SECTION_TITLES, render_report
from parakh.render.share import share_card, share_markdown
from parakh.services import reports as svc
from parakh.snapshots.history import COLUMNS, history_md_text, trend_flags
from parakh.snapshots.store import stock_dir
from tests.helpers.pilot import END, pilot_data

HOLD = "INE040A01034"  # HDFCBANK: the stock we give a position to


def months(tmp_path, n: int = 2, owned: bool = True):
    bundle = load_all()
    data = pilot_data(bundle)
    if owned:
        data.lots = [
            Lot("L1", "acct", HOLD, 123.0, dt.date(2025, 1, 10), dt.date(2025, 1, 11), 150.0, "cli")
        ]
    out = []
    ends = [
        dt.date(2026, 9, 30),
        dt.date(2026, 8, 31),
        dt.date(2026, 7, 31),
        dt.date(2026, 6, 30),
        dt.date(2026, 5, 29),
    ][:n][::-1]
    for end in ends:
        res = run_monthly(bundle, data, end, out_root=tmp_path)
        render_month(bundle, [s.model_dump(mode="json") for s in res.snapshots], tmp_path)
        out.append(res)
    return bundle, out, tmp_path


@pytest.fixture(scope="module")
def four(tmp_path_factory, module_isolation):
    """One four-month pilot run shared by the module (the pipeline is the slow part)."""
    return months(tmp_path_factory.mktemp("pilot"), 4)


@pytest.fixture
def two(four):
    bundle, runs, tmp = four
    return bundle, runs[-2:], tmp


def snap_of(res, isin):
    return next(s for s in res.snapshots if s.isin == isin).model_dump(mode="json")


@pytest.mark.ac("AC-F09.1")
def test_the_report_has_every_section_and_says_n_a_when_empty(two) -> None:
    _, runs, tmp = two
    for sec_snap in runs[-1].snapshots:
        text = (stock_dir(sec_snap.cap, sec_snap.symbol, tmp) / "reports" / "2026-09.md").read_text(
            encoding="utf-8"
        )
        for title in SECTION_TITLES:
            plain = (
                title.replace("&", "&amp;")
                if title[0].isdigit() and int(title.split(".")[0]) >= 4
                else title
            )
            assert plain in text, f"{sec_snap.symbol}: missing section {title!r}"
        assert "N/A" in text


@pytest.mark.ac("AC-F09.6")
def test_top_block_and_folded_sections(two) -> None:
    _, runs, tmp = two
    snap = snap_of(runs[-1], HOLD)
    text = (stock_dir(snap["cap"], snap["symbol"], tmp) / "reports" / "2026-09.md").read_text(
        encoding="utf-8"
    )
    top, rest = text.split("<details>", 1)
    assert (
        "## 0. TL;DR" in top
        and "What changed since last month" in top
        and "## 2. Action box" in top
    )
    bullets = re.findall(
        r"^- ", top.split("What changed since last month")[1].split("## 1.")[0], re.M
    )
    assert 1 <= len(bullets) <= 4
    assert "→" in top or "(unchanged)" in top  # verdict chip: prev → now
    for n in range(4, 16):
        assert f"<strong>{n}." in rest
    assert text.count("<details>") == text.count("</details>") == 12


@pytest.mark.ac("AC-F09.7")
def test_a_check_that_could_not_run_is_unknown_never_clean(two) -> None:
    _, runs, _ = two
    snap = snap_of(runs[-1], HOLD)
    rows = svc.check_rows(snap)
    unknown = [r for r in rows if r["state"] == "UNKNOWN"]
    assert unknown
    for r in unknown:
        assert (
            r["text"].startswith("❔")
            and "couldn't check" in r["detail"]
            and "tried" in r["detail"]
        )
    text = render_report(snap)
    assert "no red flags" not in text.lower()


def test_what_changed_is_capped_and_ordered() -> None:
    cur = {
        "thesis": {
            "changed_from": "INTACT",
            "status": "WATCH",
            "status_source": "x",
            "review_due": False,
        },
        "verdict": {
            "changed": True,
            "prev_verdict": "HOLD",
            "prev_action": None,
            "verdict": "BUY",
            "action": None,
            "drivers": [{"text": "value valuation +6.0 pts"}],
            "held_by_hysteresis": [],
        },
        "value": {"score": 70},
        "momentum": {
            "score": 40,
            "details": {"active_signals": [{"id": "M20", "status": "fired"}]},
        },
        "regime": {"regime": "Risk-Off"},
        "position": {"cost_pending": False, "days_to_long_term": 10},
    }
    prev = {"value": {"score": 60}, "momentum": {"score": 50}, "regime": {"regime": "Neutral"}}
    out = svc.what_changed(cur, prev)
    assert len(out) == svc.MAX_CHANGES == 4
    assert out[0].startswith("Thesis") and out[1].startswith("Verdict")  # thesis first (UX-03)


def test_first_month_says_so(two) -> None:
    _, runs, _ = two
    snap = runs[0].snapshots[0].model_dump(mode="json")
    assert svc.what_changed(snap, None) == [
        "First report for this stock; there is no earlier month to compare with."
    ]


@pytest.mark.ac("AC-F09.3")
def test_history_has_trend_flags_and_a_row_per_month(four) -> None:
    bundle, runs, tmp = four
    sec = next(s for s in bundle.universe.pilot if s.isin == HOLD)
    rows = list(
        csv.DictReader((stock_dir(sec.cap, sec.symbol, tmp) / "history.csv").open(encoding="utf-8"))
    )
    assert [r["period"] for r in rows] == ["2026-06", "2026-07", "2026-08", "2026-09"]
    assert list(rows[0].keys()) == COLUMNS and len(COLUMNS) >= 40
    md = (stock_dir(sec.cap, sec.symbol, tmp) / "HISTORY.md").read_text(encoding="utf-8")
    assert "## Trend flags" in md and "2026-06" in md and "## Verdict changes" in md


def test_trend_flags_notice_three_month_runs() -> None:
    def snap(p, v, m):
        return {
            "period": p,
            "value": {"score": v},
            "momentum": {"score": m},
            "verdict": {"verdict": "HOLD"},
            "regime": {"regime": "Neutral"},
        }

    flags = trend_flags([snap("2026-07", 50, 70), snap("2026-08", 55, 60), snap("2026-09", 61, 50)])
    assert any("Value score has risen" in f for f in flags) and any(
        "Momentum score has fallen" in f for f in flags
    )


def test_history_flags_a_change_of_rules(two) -> None:
    _, runs, _ = two
    a, b = (r.snapshots[0].model_dump(mode="json") for r in runs)
    b["framework"]["weights_hash"] = "deadbeef"
    assert "⚑" in history_md_text([a, b])


@pytest.mark.ac("AC-F09.8", "AC-F22.1")
def test_share_export_contains_nothing_personal(two, tmp_path) -> None:
    _, runs, _ = two
    snap = snap_of(runs[-1], HOLD)
    snap["position"]["sizing_rationale"] = "SECRET-SIZING"
    snap["thesis"]["sizing_rationale"] = "SECRET-SIZING"
    snap["notes"] = ["SECRET-NOTE"]
    pos = snap["position"]
    assert pos["quantity"] == 123.0
    text = share_markdown(snap)
    banned = [
        "123 sh",
        "123",
        "SECRET",
        "avg",
        "P&L",
        "OWNED",
        "wt ",
        "LTCG",
        "tax",
        "ADD",
        "TRIM",
        "EXIT",
        str(int(pos["market_value_inr"])),
        f"{pos['market_value_inr']:,.0f}",
    ]
    for b in banned:
        assert b not in text, f"share export leaked {b!r}"
    assert "Not investment advice" in text and "SEBI" in text
    png = share_card(snap, tmp_path / "card.png")
    assert png.exists() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_masked_snapshot_keeps_the_verdict_but_not_the_position(two) -> None:
    _, runs, _ = two
    snap = snap_of(runs[-1], HOLD)
    m = svc.mask_snapshot(snap)
    assert m["position"] is None and m["verdict"]["verdict"] == snap["verdict"]["verdict"]
    assert m["verdict"]["action"] is None and m["thesis"]["status"] == "NOT_SET"
    assert "position" in snap and snap["position"] is not None  # the original is untouched


@pytest.mark.ac("AC-F10.1", "AC-F10.2", "AC-F10.3", "AC-F10.6", "AC-F16.4")
def test_segment_summary(four) -> None:
    bundle, runs, tmp = four
    md = (tmp / "large_cap" / "_SEGMENT_SUMMARY" / "2026-09.md").read_text(encoding="utf-8")
    large = [s.symbol for s in bundle.universe.pilot if s.cap == "large"]
    for sym in large:
        assert f"[[{sym}]]" in md  # AC-F10.2 (every stock) and AC-F10.6 (Obsidian links)
    held = md.split("## Holdings (owned first)")[1].split("## Best new ideas")[0]
    assert "[[HDFCBANK]]" in held  # AC-F10.1: owned stocks lead
    assert "Regime history:" in md  # AC-F16.4
    for ext in ("csv", "xlsx", "json"):
        assert (tmp / "large_cap" / "_SEGMENT_SUMMARY" / f"2026-09.{ext}").exists()
    import openpyxl

    ws = openpyxl.load_workbook(tmp / "large_cap" / "_SEGMENT_SUMMARY" / "2026-09.xlsx").active
    assert ws.max_row == len(large) + 1 and ws["A1"].value == "symbol"


@pytest.mark.ac("AC-F10.3")
def test_concentration_flags_use_the_config_limits(tmp_path) -> None:
    from parakh.services.segment import concentration

    pf = load_all().portfolio
    rows = [
        {"symbol": "AAA", "weight_pct": pf.single_stock_max_weight_pct + 1, "sector": "S1"},
        {"symbol": "BBB", "weight_pct": pf.sector_max_weight_pct, "sector": "S1"},
        {"symbol": "CCC", "weight_pct": None, "sector": "S2"},
    ]
    out = concentration(rows, pf)
    assert any("AAA" in o and "single-stock" in o for o in out)
    assert any("S1" in o and "sector limit" in o for o in out)
    assert not any(
        "S2" in o or "CCC" in o for o in out
    )  # an unpriced holding is skipped, not guessed


@pytest.mark.ac("AC-F21.12")
def test_active_overrides_are_listed_until_they_expire(tmp_path) -> None:
    import dataclasses

    from parakh.configs.lens_models import Override, OverridesConfig

    bundle = load_all()
    ov = Override(
        id="OV-T-9",
        isin=HOLD,
        field="thesis_status",
        value="WATCH",
        reason="manual review pending",
        set_on=dt.date(2026, 9, 1),
        expires_on=dt.date(2026, 10, 10),
    )
    b2 = dataclasses.replace(bundle, overrides=OverridesConfig(overrides=[ov]))
    res = run_monthly(b2, pilot_data(b2), END, out_root=tmp_path)
    render_month(b2, [s.model_dump(mode="json") for s in res.snapshots], tmp_path)
    md = (tmp_path / "large_cap" / "_SEGMENT_SUMMARY" / "2026-09.md").read_text(encoding="utf-8")
    assert "thesis_status = WATCH until 2026-10-10" in md and "expiring within 30 days" in md


def test_charts_are_written_from_tokens_only(two) -> None:
    _, runs, tmp = two
    snap = runs[-1].snapshots[0]
    charts = stock_dir(snap.cap, snap.symbol, tmp) / "charts"
    assert (charts / "2026-09-price.png").exists() and (charts / "2026-09-scores.png").exists()
