"""T-VAL-10…: the value lens: profiles, history classes, vetoes, intrinsic value (AC-F04.1–12)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from parakh.analytics.value_build import build_inputs, value_context_parts
from parakh.configs import load_all, load_file
from parakh.configs.lens_models import ValueConfig
from parakh.lenses.base import LensConfig, LensResult, StockContext
from parakh.lenses.value import ValueLens
from parakh.storage.point_in_time import visible_asof
from tests.helpers import fundamentals as fx

ASOF = dt.date(2026, 10, 30)
CFG = load_file("value.yaml", ValueConfig)
V = "MET.value."


def evaluate(
    rows: list[dict[str, Any]],
    profile: str = "standard",
    cap: str = "large",
    price: float = 280.0,
    listed_on: dt.date | None = dt.date(2005, 1, 3),
    sh: list[dict[str, Any]] | None = None,
    inputs: dict[str, float | None] | None = None,
    stakes: list[dict[str, Any]] | None = None,
    isin: str = "INE000000000",
    extra_metrics: dict[str, float] | None = None,
) -> LensResult:
    vis = visible_asof(rows, ASOF, 75)
    inp = build_inputs(
        isin,
        "TEST",
        cap,
        profile,
        ASOF,
        price,
        vis,
        CFG,
        sh if sh is not None else fx.shareholding(isin),
        listed_on,
        inputs,
        None,
        stakes,
    )
    vals, reasons, extras = value_context_parts(inp, CFG)
    vals = vals | (extra_metrics or {})
    ctx = StockContext(
        isin=isin,
        symbol="TEST",
        asof=ASOF,
        profile=profile,
        cap=cap,
        metrics=vals,
        na_reasons=reasons,
        extras=extras,
    )
    return ValueLens().evaluate(ctx, LensConfig(lens_version="1"))


def test_a_healthy_compounder_scores_well_with_sources_stamped() -> None:
    """T-VAL-10 (AC-F04.6): every scored metric carries its source and as-of date."""
    r = evaluate(fx.rows())
    assert r.score is not None and r.score > 50
    assert r.details["metrics"], "no metric rows"
    for mid, row in r.details["metrics"].items():
        assert row["source"], mid
        if row["source"] != "profile_inputs":
            assert row["asof"], mid


@pytest.mark.ac("AC-F04.1")
def test_a_bank_is_scored_on_pb_roa_and_npa_not_ev_ebitda_or_de() -> None:
    """T-VAL-11"""
    r = evaluate(fx.rows(isin="INE040A01034"), profile="bank", isin="INE040A01034")
    used = set(r.metrics_used)
    assert V + "pb_discount_own_5y" in used and V + "roa_5y_avg" in used
    assert V + "ev_ebitda_discount_own" not in used and V + "debt_equity" not in used
    # asset-quality metrics are not in the export, so they are N/A with a reason and lower confidence
    assert V + "gnpa" in r.na and "not supplied" in r.na[V + "gnpa"]
    assert r.confidence != "High"


@pytest.mark.ac("AC-F04.2")
@pytest.mark.parametrize("growth,expect_na", [(-0.08, True), (0.12, False)])
def test_peg_is_na_when_eps_growth_is_not_positive(growth: float, expect_na: bool) -> None:
    """T-VAL-12"""
    r = evaluate(fx.rows(growth=growth))
    assert (V + "peg" in r.na) is expect_na


@pytest.mark.ac("AC-F04.2")
def test_peg_is_na_above_50_percent_eps_growth() -> None:
    """T-VAL-13: pat margin step-up makes 3-year EPS CAGR exceed 50%."""
    rows = fx.rows(growth=0.6, price0=10.0)
    r = evaluate(rows, price=200.0)
    assert V + "peg" in r.na and "50%" in r.na[V + "peg"]


@pytest.mark.ac("AC-F04.3")
def test_a_pledge_veto_forces_avoid_whatever_the_score() -> None:
    """T-VAL-14"""
    clean = evaluate(fx.rows(), sh=fx.shareholding(pledge_pct=0.0), cap="mid")
    pledged = evaluate(fx.rows(), sh=fx.shareholding(pledge_pct=35.0), cap="mid")
    assert clean.view != "AVOID" and not clean.vetoes
    assert pledged.view == "AVOID" and "RULE.value.pledge_cap" in pledged.vetoes
    assert pledged.score is not None and pledged.score > 40  # the score itself is not the reason


def test_pledge_unknown_is_not_clean() -> None:
    """T-VAL-15 (UX-05): no filing means the check is UNKNOWN, listed as such, and no veto fires."""
    r = evaluate(fx.rows(), sh=[])
    assert not r.vetoes
    assert any(u["check"] == "RULE.value.pledge_cap" for u in r.details["unknown_checks"])


@pytest.mark.ac("AC-F04.4")
def test_momentum_metrics_cannot_move_the_value_score() -> None:
    """T-VAL-16: DMAs live in the entry-timing overlay only."""
    base = evaluate(fx.rows())
    moved = evaluate(
        fx.rows(), extra_metrics={"MET.momentum.dma200": 1.0, "MET.momentum.dma50": 9999.0}
    )
    assert base.score == moved.score
    used = {c.metric for subs in CFG.subscores.values() for c in subs}
    used |= {c.metric for p in CFG.profiles.values() for subs in p.replace.values() for c in subs}
    assert not any(m.startswith("MET.momentum") for m in used)


@pytest.mark.ac("AC-F04.8")
def test_missing_own_history_is_na_with_reason_and_weights_renormalise() -> None:
    """T-VAL-17: a stock listed 11 months ago: 5-year band N/A with the reason, score still computed."""
    young = evaluate(fx.rows(), listed_on=ASOF - dt.timedelta(days=335))
    reason = young.na[V + "pe_discount_own_5y"]
    assert "listed 11 months" in reason and "needs 60" in reason
    assert young.score is not None


@pytest.mark.ac("AC-F04.9")
def test_h0_stock_is_informational_low_confidence_and_vetoes_still_apply() -> None:
    """T-VAL-18"""
    r = evaluate(
        fx.rows(),
        listed_on=ASOF - dt.timedelta(days=300),
        sh=fx.shareholding(pledge_pct=40.0),
        cap="small",
    )
    assert r.informational and r.confidence == "Low"
    assert any("limited history" in f for f in r.flags)
    assert r.details["history_class"] == "H0"
    assert "RULE.value.pledge_cap" in r.vetoes and r.view == "AVOID"


@pytest.mark.ac("AC-F04.10")
def test_airline_leverage_is_lease_adjusted_not_raw_debt_equity() -> None:
    """T-VAL-19"""
    r = evaluate(
        fx.rows(isin="INE646L01027"),
        profile="airline_lease_heavy",
        isin="INE646L01027",
        inputs={
            "lease_liabilities_cr": 150.0,
            "lease_cost_cr": 900.0,
        },  # leases sit inside borrowings (200)
    )
    assert V + "lease_adj_leverage" in r.metrics_used
    assert V + "debt_equity" not in r.metrics_used
    no_inputs = evaluate(
        fx.rows(isin="INE646L01027"), profile="airline_lease_heavy", isin="INE646L01027"
    )
    assert (
        "lease inputs" in no_inputs.na[V + "lease_adj_leverage"]
        or "not supplied" in no_inputs.na[V + "lease_adj_leverage"]
    )


@pytest.mark.ac("AC-F04.11")
def test_holdco_intrinsic_value_includes_sotp_and_uses_standalone_balance_sheet() -> None:
    """T-VAL-20"""
    stakes = [
        {"name": "Listed finance arm", "isin": "INE0AAA01010", "stake": 0.5, "mcap_cr": 20000.0},
        {"name": "Listed IT arm", "isin": "INE0BBB01010", "stake": 0.25, "mcap_cr": 100000.0},
    ]
    inputs: dict[str, float | None] = {
        "standalone_pat_cr": 500.0,
        "standalone_net_debt_cr": 100.0,
        "standalone_equity_cr": 1000.0,
    }
    r = evaluate(
        fx.rows(isin="INE101A01026"),
        profile="conglomerate_sotp",
        isin="INE101A01026",
        inputs=inputs,
        stakes=stakes,
    )
    iv = r.details["intrinsic_value"]
    assert "sotp" in iv["methods"]
    core = (
        500.0 * r.details["intrinsic_value"]["methods"]["sotp"] * 0
    )  # placeholder to keep the arithmetic explicit below
    assert core == 0
    # SOTP = core(500 × median P/E) + (0.5×20000 + 0.25×100000) × (1 − 20% holdco discount), per share (10 Cr shares)
    median_pe = 0.0
    vis = visible_asof(fx.rows(isin="INE101A01026"), ASOF, 75)
    inp = build_inputs(
        "INE101A01026",
        "T",
        "large",
        "conglomerate_sotp",
        ASOF,
        280.0,
        vis,
        CFG,
        [],
        dt.date(2005, 1, 3),
        inputs,
        None,
        stakes,
    )
    from parakh.analytics.value_build import _median_pe
    from parakh.analytics.value_calc import VCalc

    median_pe = _median_pe(VCalc(inp, CFG)) or 0.0
    expected = (500.0 * median_pe + (0.5 * 20000 + 0.25 * 100000) * 0.8) / 10.0
    assert iv["methods"]["sotp"] == pytest.approx(expected, rel=1e-9)
    assert (
        V + "standalone_debt_equity" in r.metrics_used and V + "debt_equity" not in r.metrics_used
    )
    assert (
        iv["sotp_range"]["sotp_low"] < iv["methods"]["sotp"] <= iv["sotp_range"]["sotp_high"]
    )  # base discount is the low end of the range


@pytest.mark.ac("AC-F04.12")
def test_pre_profit_negative_cfo_is_a_flag_with_runway_and_a_veto_without() -> None:
    """T-VAL-21"""
    neg = [-50.0, -60.0, -70.0, -80.0, -90.0, -100.0, -110.0, -120.0, -130.0, -140.0]
    healthy_cash = fx.rows(
        cfo_override=neg, borrowings0=10.0
    )  # cash & bank grows, burn small relative to cash
    flag_case = evaluate(healthy_cash, profile="new_age", listed_on=dt.date(2020, 1, 1))
    assert V + "cash_runway_months" in flag_case.metrics_used
    runway = flag_case.details["metrics"][V + "cash_runway_months"]["value"]
    assert runway is not None
    # runway depends on the synthetic cash; force both branches through the veto rule directly
    from parakh.lenses.base import StockContext as SC
    from parakh.lenses.value_rules import negative_cfo

    def mk(rw):
        return SC(
            isin="X",
            symbol="X",
            asof=ASOF,
            profile="new_age",
            cap="small",
            metrics={V + "cash_runway_months": rw},
            extras={"cfo_negative_years": 4, "cfo_years": 5},
        )

    assert negative_cfo(mk(30.0), CFG) is False  # runway ≥ 24 months: flag only
    assert negative_cfo(mk(10.0), CFG) is True  # below 24 months: veto
    assert negative_cfo(mk(None), CFG) is None


def test_a_loss_maker_has_no_pe_and_a_sound_company_with_negative_cfo_is_vetoed() -> None:
    """T-VAL-22"""
    loss = evaluate(fx.rows(pat_margin=-0.05))
    assert "loss-making" in loss.na[V + "pe_discount_own_5y"]
    neg = [10, 10, 10, 10, 10, 10, -5, -5, -5, -5]
    r = evaluate(fx.rows(cfo_override=[float(x) for x in neg]))
    assert "RULE.value.negative_cfo" in r.vetoes and r.view == "AVOID"


def test_history_break_cuts_growth_windows_but_not_per_share_ratios() -> None:
    """T-VAL-23: HDFC Bank's July 2023 merger: growth restarts at FY24; P/E history stays per share."""
    isin = "INE040A01034"
    r = evaluate(fx.rows(isin=isin), profile="bank", isin=isin)
    assert "restarts" in r.na.get(V + "revenue_cagr_3y", "")
    assert V + "pb_discount_own_5y" in r.metrics_used
    assert r.details["history_break"] == "2024-03-31"


def test_every_pilot_profile_exists_in_the_value_config() -> None:
    """T-VAL-24 (AC-F04.7): each pilot stock's profile has a spec; the history class is computed, not set."""
    bundle = load_all()
    for sec in bundle.universe.pilot:
        assert sec.profile in CFG.profiles, sec.symbol
    r = evaluate(fx.rows())
    assert r.details["profile"] == "standard" and r.details["history_class"] in ("H0", "H1", "H2")


def test_value_view_labels_follow_the_plan() -> None:
    """T-VAL-25"""
    r = evaluate(fx.rows(), price=60.0)  # cheap price: margin of safety large
    assert r.view in ("UNDERVALUED", "QUALITY_FAIRLY_PRICED", "FAIR")
    expensive = evaluate(fx.rows(), price=5000.0)
    assert expensive.view == "OVERVALUED"
