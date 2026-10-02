"""F08 verdict policy: the matrix, vetoes, hysteresis, limited history, regime, wording (plan 00 §5)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.configs import load_file
from parakh.configs.lens_models import Override, VerdictPolicy
from parakh.lenses.base import LensResult
from parakh.policy.attribution import drivers
from parakh.policy.verdict import PolicyInput, PrevState, decide, level_with_hysteresis

POLICY = load_file("verdict_policy.yaml", VerdictPolicy)


def lens(
    lid: str,
    score: float | None,
    *,
    view: str = "FAIR",
    conf: str = "High",
    info: bool = False,
    vetoes: list[str] | None = None,
    flags: list[str] | None = None,
    signals: list[str] | None = None,
    gate_ok: bool = True,
) -> LensResult:
    details = (
        {"strong_gate": {"passed": gate_ok, "failed": [] if gate_ok else ["Trend Template"]}}
        if lid == "momentum"
        else {}
    )
    return LensResult(
        lens_id=lid,
        lens_version="1",
        score=score,
        view=view,
        confidence=conf,  # type: ignore[arg-type]
        informational=info,  # type: ignore[arg-type]
        vetoes=vetoes or [],
        flags=flags or [],
        signals=signals or [],
        details=details,
    )


def run(v: float | None, m: float | None, **kw):  # noqa: ANN003, ANN201
    value = kw.pop("value", None) or lens("value", v)
    mom = kw.pop("momentum", None) or lens("momentum", m, view="NEUTRAL")
    return decide(PolicyInput(value=value, momentum=mom, **kw), POLICY)


@pytest.mark.ac("AC-F08.1")
def test_high_value_and_strong_momentum_is_strong_buy_or_add() -> None:
    """T-POL-01"""
    r = run(75, 80)
    assert (r.verdict, r.headline) == ("STRONG_BUY", "STRONG_BUY")
    owned = run(75, 80, owned=True)
    assert owned.verdict == "STRONG_BUY" and owned.action == "ADD" and owned.headline == "ADD"


@pytest.mark.parametrize(
    ("v", "m", "verdict", "qualifier"),
    [
        (80, 55, "BUY", "staggered"),
        (80, 30, "ACCUMULATE", None),
        (60, 80, "BUY", "momentum-led"),
        (60, 55, "HOLD", None),
        (60, 30, "REDUCE", None),
        (30, 80, "MOMENTUM_ONLY", None),
        (30, 55, "REDUCE", None),
        (30, 30, "AVOID", None),  # SELL is AVOID for a stock you do not hold
    ],
)
def test_every_matrix_cell(v: float, m: float, verdict: str, qualifier: str | None) -> None:
    """T-POL-02: the nine cells of plan 00 §5."""
    r = run(v, m)
    assert (r.verdict, r.qualifier) == (verdict, qualifier)
    assert r.rule_id.startswith("VP.matrix.")


def test_sell_is_sell_when_owned_and_exit_is_the_action() -> None:
    """T-POL-03"""
    r = run(30, 30, owned=True)
    assert r.verdict == "SELL" and r.action == "EXIT"


def test_cheap_but_falling_accumulates_only_without_a_value_trap() -> None:
    """T-POL-04"""
    trapped = run(
        80, 30, value=lens("value", 80, flags=["value-trap risk: cheap, but ROCE falling"])
    )
    assert trapped.verdict == "WATCH"
    low_conf = run(80, 30, value=lens("value", 80, conf="Low"))
    assert low_conf.verdict == "WATCH"
    assert run(80, 30).verdict == "ACCUMULATE"


@pytest.mark.parametrize(
    ("m", "owned", "verdict"),
    [(80, False, "AVOID"), (55, False, "AVOID"), (80, True, "AVOID"), (30, True, "SELL")],
)
def test_veto_overrides_the_matrix(m: float, owned: bool, verdict: str) -> None:
    """T-POL-05: plan 00 §5 last row (AC-F04.3 at policy level)."""
    r = run(90, m, owned=owned, value=lens("value", 90, vetoes=["RULE.value.pledge_cap"]))
    assert r.verdict == verdict
    assert r.vetoes == ["RULE.value.pledge_cap"] and r.rule_id.startswith("VP.veto.")


def test_a_vetoed_stock_that_is_not_owned_is_never_a_sell() -> None:
    assert run(90, 30, value=lens("value", 90, vetoes=["RULE.value.nnpa_cap"])).verdict == "AVOID"
    owned = run(90, 30, value=lens("value", 90, vetoes=["RULE.value.nnpa_cap"]), owned=True)
    assert owned.verdict == "SELL" and owned.action == "EXIT"


@pytest.mark.ac("AC-F08.2")
@pytest.mark.parametrize(
    ("score", "prev", "expected"),
    [
        (69.9, 2, 2),  # high band, just under 70: held
        (65.0, 2, 2),  # exactly 5 below: held (needs MORE than 5)
        (64.9, 2, 1),  # more than 5 below: moves
        (72.0, 1, 1),  # fair, just over 70: held
        (75.0, 1, 1),
        (75.1, 1, 2),
        (44.0, 1, 1),  # fair, just under 45: held
        (40.0, 1, 1),
        (39.9, 1, 0),
        (47.0, 0, 0),  # low, just over 45: held
        (50.0, 0, 0),
        (50.1, 0, 1),
        (90.0, 0, 2),  # a jump crosses both cut-offs
        (10.0, 2, 0),
    ],
)
def test_hysteresis_band_changes_need_more_than_five_points(
    score: float, prev: int, expected: int
) -> None:
    """T-POL-06"""
    assert level_with_hysteresis(score, 45, 70, 5, prev)[0] == expected


@pytest.mark.ac("AC-F08.2")
def test_a_score_within_five_points_of_a_threshold_does_not_flip_the_verdict() -> None:
    """T-POL-07"""
    first = run(72, 55)
    assert first.verdict == "BUY"
    prev = PrevState(
        verdict=first.verdict, value_level=first.value_level, momentum_level=first.momentum_level
    )
    wobble = run(68, 55, prev=prev)  # raw band is fair, but only 2 below the cut-off
    assert wobble.verdict == "BUY" and wobble.held_by_hysteresis == ["value"]
    assert wobble.value_band_raw == "fair" and wobble.value_band == "high"
    assert not wobble.changed
    moved = run(63, 55, prev=PrevState(verdict="BUY", value_level=2, momentum_level=1))
    assert moved.verdict == "HOLD" and moved.changed and moved.direction == "downgrade"


@pytest.mark.ac("AC-F04.9")
def test_informational_value_uses_the_fair_row_with_low_confidence_and_a_label() -> None:
    """T-POL-08 (D24)"""
    r = run(None, 80, value=lens("value", 90, info=True, conf="Low"))
    assert (r.verdict, r.qualifier) == ("BUY", "momentum-led")
    assert r.confidence == "Low" and r.label == "limited history" and r.value_band is None
    veto = run(
        None, 80, value=lens("value", 90, info=True, conf="Low", vetoes=["RULE.value.pledge_cap"])
    )
    assert veto.verdict == "AVOID"  # vetoes still apply


@pytest.mark.ac("AC-F05.9")
def test_informational_momentum_is_vetoes_only_and_watch_at_best() -> None:
    """T-POL-09"""
    r = run(90, None, momentum=lens("momentum", 90, view="STRONG", info=True, conf="Low"))
    assert r.verdict == "WATCH" and r.confidence == "Low" and r.label == "limited history"
    both = run(
        None, None, value=lens("value", None, info=True), momentum=lens("momentum", None, info=True)
    )
    assert both.verdict == "WATCH"
    vetoed = run(
        90,
        None,
        value=lens("value", 90, vetoes=["RULE.value.negative_cfo"]),
        momentum=lens("momentum", None, info=True),
    )
    assert vetoed.verdict == "AVOID"


@pytest.mark.ac("AC-F05.3")
def test_risk_off_holds_strong_momentum_at_neutral() -> None:
    """T-POL-10: no momentum buy beyond HOLD in a Risk-Off segment."""
    assert run(60, 85, regime="Risk-On").verdict == "BUY"
    r = run(60, 85, regime="Risk-Off")
    assert r.verdict == "HOLD" and any("Risk-Off" in x for x in r.reasons)
    assert run(30, 85, regime="Risk-Off").verdict == "REDUCE"  # no momentum trade in Risk-Off


@pytest.mark.ac("AC-F05.4")
def test_a_circuit_trap_blocks_a_momentum_led_buy() -> None:
    """T-POL-11: M27."""
    mom = lens("momentum", 85, view="STRONG", signals=["M27"])
    r = decide(PolicyInput(value=lens("value", 60), momentum=mom), POLICY)
    assert r.verdict == "HOLD" and any("M27" in x for x in r.reasons)


def test_strong_needs_the_structural_gate_not_just_the_score() -> None:
    """T-POL-12: a high score without Trend Template / stage 2 counts as neutral."""
    mom = lens("momentum", 85, view="NEUTRAL", gate_ok=False)
    r = decide(PolicyInput(value=lens("value", 60), momentum=mom), POLICY)
    assert r.verdict == "HOLD" and r.momentum_band == "neutral"


def test_a_weak_lens_view_forces_the_weak_column() -> None:
    """T-POL-13: stage 3/4 or a confirmed exit signal is weak whatever the score."""
    mom = lens("momentum", 60, view="WEAK", signals=["M21"])
    r = decide(PolicyInput(value=lens("value", 60), momentum=mom), POLICY)
    assert r.verdict == "REDUCE" and r.momentum_band == "weak"


@pytest.mark.ac("AC-F08.3")
def test_a_lens_without_a_policy_row_is_informational_and_changes_nothing() -> None:
    """T-POL-14"""
    base = run(60, 55)
    extra = run(60, 55, other_lenses={"dividend": lens("dividend", 5)})
    assert extra.verdict == base.verdict and extra.informational_lenses == ["dividend"]


def test_owned_wording_and_target_weight() -> None:
    """T-POL-15 (plan 12 §3.2): ADD becomes HOLD at target weight; WATCH is HOLD for an owned stock."""
    assert run(80, 55, owned=True, weight_pct=3, target_weight_pct=8).action == "ADD"
    assert run(80, 55, owned=True, weight_pct=8, target_weight_pct=8).action == "HOLD"
    assert (
        run(80, 30, value=lens("value", 80, flags=["value-trap risk: x"]), owned=True).action
        == "HOLD"
    )
    assert run(60, 30, owned=True).action == "TRIM"
    assert run(60, 55, owned=False).action is None


@pytest.mark.ac("AC-F23.1")
def test_a_broken_thesis_leads_to_an_exit_for_an_owned_stock_only() -> None:
    """T-POL-16"""
    r = run(80, 80, owned=True, thesis_status="BROKEN")
    assert r.verdict == "STRONG_BUY" and r.action == "EXIT"
    assert run(80, 80, owned=False, thesis_status="BROKEN").action is None


def test_confidence_is_the_lowest_of_lens_and_data_confidence() -> None:
    """T-POL-17 (AC-F02.4: failed validation → Low)"""
    assert run(60, 55).confidence == "High"
    assert run(60, 55, data_confidence="Low").confidence == "Low"
    assert (
        run(60, 55, momentum=lens("momentum", 55, view="NEUTRAL", conf="Med")).confidence == "Med"
    )


@pytest.mark.ac("AC-F21.12")
def test_an_override_replaces_the_verdict_and_is_recorded() -> None:
    """T-POL-18"""
    o = Override(
        id="OV-1",
        isin="INE040A01034",
        field="verdict",
        value="HOLD",
        reason="Merger year: history distorted",
        set_on=dt.date(2026, 10, 1),
        expires_on=dt.date(2027, 1, 31),
    )
    r = run(80, 80, override=o)
    assert (
        r.verdict == "HOLD"
        and r.override
        and r.override["from"] == "STRONG_BUY"
        and r.override["id"] == "OV-1"
    )


def test_overrides_need_a_reason_and_a_short_life() -> None:
    """T-POL-19"""
    with pytest.raises(ValueError):
        Override(
            id="x",
            isin="INE040A01034",
            field="verdict",
            value="HOLD",
            reason="short",
            set_on=dt.date(2026, 10, 1),
            expires_on=dt.date(2027, 1, 1),
        )
    with pytest.raises(ValueError):
        Override(
            id="x",
            isin="INE040A01034",
            field="verdict",
            value="HOLD",
            reason="a good enough reason",
            set_on=dt.date(2026, 10, 1),
            expires_on=dt.date(2028, 1, 1),
        )


def test_change_direction_and_first_month() -> None:
    """T-POL-20"""
    assert run(60, 55).direction == "new"
    up = run(60, 80, prev=PrevState(verdict="HOLD", value_level=1, momentum_level=1))
    assert up.direction == "upgrade" and up.changed and up.prev_verdict == "HOLD"
    same = run(60, 55, prev=PrevState(verdict="HOLD", value_level=1, momentum_level=1))
    assert same.direction == "same" and not same.changed


@pytest.mark.ac("AC-F08.4")
def test_a_verdict_change_lists_its_top_three_drivers() -> None:
    """T-POL-21"""

    def snap(val: float, mom: float, sub_v: dict, sub_m: dict, vetoes=(), regime="Neutral"):  # noqa: ANN001, ANN202
        return {
            "value": {
                "subscores": sub_v,
                "details": {
                    "weights": {
                        "valuation": 40,
                        "quality": 25,
                        "balance_sheet": 10,
                        "growth": 10,
                        "governance": 15,
                    },
                    "metrics": {"MET.value.pe_discount_own_5y": {"value": val}},
                },
            },
            "momentum": {
                "subscores": sub_m,
                "details": {
                    "weights": {
                        "rs": 30,
                        "trend": 25,
                        "vol_adj": 20,
                        "high_prox": 10,
                        "volume": 10,
                        "earnings": 5,
                    },
                    "metric_values": {"MET.momentum.mom_12_1": mom},
                },
            },
            "verdict": {"vetoes": list(vetoes), "owned": False, "held_by_hysteresis": []},
            "regime": {"regime": regime},
            "thesis": {"status": "NOT_SET"},
        }

    prev = snap(
        -0.05,
        0.10,
        dict(valuation=0.4, quality=0.7, balance_sheet=0.6, growth=0.5, governance=0.8),
        dict(rs=0.5, trend=0.5, vol_adj=0.5, high_prox=0.5, volume=0.5, earnings=0.5),
    )
    cur = snap(
        0.12,
        0.30,
        dict(valuation=0.7, quality=0.7, balance_sheet=0.6, growth=0.5, governance=0.8),
        dict(rs=0.8, trend=0.5, vol_adj=0.5, high_prox=0.5, volume=0.5, earnings=0.5),
        regime="Risk-On",
    )
    got = drivers(
        prev, cur, 3, {"MET.value.pe_discount_own_5y": "valuation", "MET.momentum.mom_12_1": "rs"}
    )
    assert len(got) == 3
    assert got[0]["text"].startswith("regime Neutral → Risk-On")
    assert any("valuation" in d["text"] and "pe discount own 5y" in d["text"] for d in got)
    assert any(d["lens"] == "momentum" for d in got if "lens" in d)
    vetoed = drivers(prev, snap(0, 0, {}, {}, vetoes=["RULE.value.pledge_cap"]), 3)
    assert vetoed[0]["text"] == "new veto RULE.value.pledge_cap"
    assert drivers(None, cur, 3) == []


@pytest.mark.ac("AC-F08.5")
def test_the_policy_is_config_driven_and_a_change_changes_the_hash(tmp_path) -> None:  # noqa: ANN001
    """T-POL-22: edit the matrix in a copy of the config and the decision and the config hash move."""
    import shutil

    import yaml

    from parakh.audit.context import config_hash
    from parakh.config import config_dir

    copy = tmp_path / "config"
    shutil.copytree(config_dir(), copy)
    before = config_hash(copy)
    raw = yaml.safe_load((copy / "verdict_policy.yaml").read_text(encoding="utf-8"))
    raw["matrix"]["fair"]["neutral"]["verdict"] = "WATCH"
    raw["policy_version"] = "1.0.1"
    (copy / "verdict_policy.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    changed = load_file("verdict_policy.yaml", VerdictPolicy, copy)
    r = decide(
        PolicyInput(value=lens("value", 60), momentum=lens("momentum", 55, view="NEUTRAL")), changed
    )
    assert r.verdict == "WATCH" and r.policy_version == "1.0.1"
    assert config_hash(copy) != before


def test_the_policy_schema_rejects_an_incomplete_matrix() -> None:
    """T-POL-23"""
    raw = POLICY.model_dump()
    del raw["matrix"]["low"]["weak"]
    with pytest.raises(ValueError):
        VerdictPolicy.model_validate(raw)
