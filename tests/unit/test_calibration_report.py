# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false, reportOperatorIssue=false, reportOptionalSubscript=false, reportAssignmentType=false
# why: tests build pandas/numpy fixtures and read optional result fields the assertions already prove are set
"""Quarterly calibration report: recommendation logic and rendering (AC-F17.3, AC-F17.5)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.calibration import report as rp
from parakh.configs import load_all

CAL = load_all().calibration


def cal(verdict: str, horizon: int = 6, spread: float = 2.0) -> dict:
    return {"horizon_months": horizon, "verdict": verdict, "reason": f"because {verdict}", "spread_pct": spread,
            "periods_used": 30, "ic_mean": 0.05, "ic_t": 2.4}  # fmt: skip


def build(parts: rp.Parts) -> rp.CalibrationReport:
    return rp.build_report(
        quarter="2026-Q4",
        cfg=CAL,
        framework_version="1.0.0",
        parts=parts,
        today=dt.date(2026, 12, 31),
    )


@pytest.mark.ac("AC-F17.3")
def test_recommendation_follows_the_primary_horizon_only() -> None:
    r = build(
        rp.Parts(
            quintiles={
                "momentum": [cal("reversed", 3, -2), cal("confirmed", 6)],
                "value": [cal("reversed", 6, -3.2)],
            }
        )
    )
    by = {x.lens: x for x in r.recommendations}
    assert by["momentum"].decision == rp.CONFIRM
    assert by["value"].decision == rp.REVIEW and "-3.2" in by["value"].reason
    assert r.overall == rp.REVIEW


@pytest.mark.ac("AC-F17.3")
def test_nothing_calibrated_is_insufficient_not_a_confirmation() -> None:
    r = build(rp.Parts())
    assert r.overall == rp.INSUFFICIENT
    md = r.to_markdown()
    assert "No lens has scored history" in md and "Not run this quarter" in md
    assert "Nothing below changes a weight by itself" in md


def test_inconclusive_is_insufficient() -> None:
    assert build(rp.Parts(quintiles={"value": [cal("inconclusive")]})).overall == rp.INSUFFICIENT


@pytest.mark.ac("AC-F17.5")
def test_markdown_carries_precision_per_signal_and_the_backtest_table() -> None:
    parts = rp.Parts(
        backtest={
            "status": "ok",
            "warnings": ["survivorship"],
            "gross": {"cagr_pct": 20.0, "start_inr": 100, "end_inr": 200},
        },
        alerts={
            "alerts": 20,
            "rated": 12,
            "coverage_pct": 60.0,
            "precision_pct": 75.0,
            "target_pct": 70.0,
            "signals": [
                {
                    "code": "M01",
                    "alerts": 20,
                    "rated": 12,
                    "useful": 9,
                    "precision_pct": 75.0,
                    "lower_bound_pct": 47.0,
                    "status": "meets target",
                }
            ],
        },  # fmt: skip
        journal={
            "entries": 3,
            "reviewed": 1,
            "open": 2,
            "right_pct": 100.0,
            "by_verdict": {"right": 1},
        },
        drift={"status": "ok"},
    )
    md = build(parts).to_markdown()
    assert "| M01 | 20 | 12 | 9 | 75% | 47% | meets target |" in md
    assert "| Gross | 20.0% |" in md and "100%" in md
    assert (
        "Warning: survivorship" in md
        and "Drift: **ok**" in md
        and "Replay determinism: not run" in md
    )


def test_refused_backtest_says_why() -> None:
    md = build(
        rp.Parts(backtest={"status": "refused", "reasons": ["no membership history"]})
    ).to_markdown()
    assert "**refused**" in md and "no membership history" in md


def test_quarter_and_review_template() -> None:
    assert (
        rp.quarter_of(dt.date(2026, 12, 31)) == "2026-Q4"
        and rp.quarter_of(dt.date(2027, 1, 1)) == "2027-Q1"
    )
    t = rp.review_template(build(rp.Parts()), 10)
    assert "# Governance review 2026-Q4" in t and "within 10 days" in t


# -- the service joins the pieces -----------------------------------------------------------------
def test_compute_parts_joins_every_section_on_a_synthetic_world() -> None:
    from parakh.services.calibration import CalibrationInputs, compute_parts, rebalance_dates
    from tests.helpers.calibration import securities, trailing_panel, world

    bundle = load_all()
    prices, bench, isins = world(n_stocks=30, years=8.0, seed=11, spread=0.0015)
    panel = trailing_panel(prices)
    inputs = CalibrationInputs(securities(isins), prices, {"large": bench}, wide_bench=bench)
    parts = compute_parts(bundle, inputs, panel)
    assert (
        parts.backtest["status"] == "refused"
    )  # no membership history: refuses rather than flatters
    assert parts.quintiles["momentum"][1]["horizon_months"] == 6
    assert parts.quintiles["momentum"][1]["verdict"] == "confirmed"
    assert parts.alerts["alerts"] == 0 and parts.scorecard is None
    report = build(parts)
    assert report.overall == rp.CONFIRM and "Score quintiles" in report.to_markdown()
    assert rebalance_dates(prices, dt.date(2026, 1, 1), dt.date(2026, 6, 30))[0].month == 1
    proxy = compute_parts(bundle, inputs, panel, allow_proxy=True)
    assert proxy.backtest["status"] == "ok" and any(
        "SURVIVORSHIP" in w for w in proxy.backtest["warnings"]
    )


def test_mcp_summary_reads_the_latest_report_and_is_honest_when_there_is_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from parakh.services import calibration_service as cs

    assert cs.report_summary(tmp_path).available is False
    folder = tmp_path / "docs" / "calibration"
    folder.mkdir(parents=True)
    (folder / "2026-Q4.json").write_text(
        build(rp.Parts(quintiles={"momentum": [cal("confirmed")]})).to_json()
    )
    out = cs.report_summary(tmp_path)
    assert out.available and out.overall == "CONFIRM" and out.recommendations[0].lens == "momentum"
