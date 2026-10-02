"""Verdict policy engine (F08; plan 00 §5). Pure rules over two lens results; no I/O.

    result = decide(PolicyInput(value=..., momentum=..., regime="Neutral", owned=False), policy)

Order of decisions, each one recorded in `result.trail` so `explain` can replay it:

1. Informational lenses (limited history, D24). A value lens that is informational puts the
   stock in the Fair-value row with Low confidence. A momentum lens that is informational
   means the verdict comes from vetoes only: WATCH at best.
2. Bands with hysteresis: a lens's band only changes when its score is more than `hysteresis`
   points past the cut-off, measured from last month's band (AC-F08.2).
3. Regime and blockers: a Risk-Off segment, or a circuit-trap / surveillance signal, stops
   momentum counting as strong (AC-F05.3, AC-F05.4).
4. The matrix cell, the veto row when any red flag fired, and the one split on a flag (cheap
   but falling → ACCUMULATE only without a value-trap warning).
5. Wording for what you own (ADD / HOLD / TRIM / EXIT), the thesis check, and any active
   override, which needs a reason and an expiry and is shown beside the verdict.

A lens that is registered but has no policy row is listed under `informational_lenses` and can
never change a verdict (AC-F08.3). Every threshold is read from config/verdict_policy.yaml.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from parakh.configs.lens_models import Cell, Override, VerdictPolicy
from parakh.lenses.base import Confidence, LensResult

Level = Literal["low", "mid", "high"]
LEVELS: tuple[Level, ...] = ("low", "mid", "high")
ROW = {"low": "low", "mid": "fair", "high": "high"}  # value band names
COL = {"low": "weak", "mid": "neutral", "high": "strong"}  # momentum band names
CONF_RANK = {"Low": 0, "Med": 1, "High": 2}


def raw_level(score: float, low: float, high: float) -> int:
    return 2 if score >= high else 0 if score < low else 1


def level_with_hysteresis(
    score: float, low: float, high: float, hysteresis: float, prev: int | None
) -> tuple[int, bool]:
    """The band index (0 low, 1 mid, 2 high) and whether hysteresis held last month's band.

    Moving up from mid needs score > high + h, from low needs score > low + h; moving down
    from high needs score < high - h, from mid score < low - h. Jumps over a band cross both.
    """
    raw = raw_level(score, low, high)
    if prev is None or prev == raw:
        return raw, False
    level = prev
    while level != raw:
        if raw > level:
            cut = high if level == 1 else low
            if not score > cut + hysteresis:
                break
            level += 1
        else:
            cut = low if level == 1 else high
            if not score < cut - hysteresis:
                break
            level -= 1
    return level, level != raw


class PrevState(BaseModel):
    """What the policy needs from last month's snapshot."""

    verdict: str | None = None
    action: str | None = None
    value_level: int | None = None
    momentum_level: int | None = None
    asof: str | None = None


class PolicyInput(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    value: LensResult | None
    momentum: LensResult | None
    other_lenses: dict[str, LensResult] = Field(default_factory=dict)
    regime: str = "Neutral"
    owned: bool = False
    weight_pct: float | None = None
    target_weight_pct: float | None = None
    thesis_status: str = "NOT_SET"
    data_confidence: Confidence = "High"
    prev: PrevState | None = None
    override: Override | None = None


class VerdictResult(BaseModel):
    policy_version: str
    verdict: str  # STRONG_BUY … AVOID, before owned wording
    qualifier: str | None = None
    action: str | None = None  # ADD / HOLD / TRIM / EXIT for a stock you own
    headline: str  # what a surface prints first: the action if owned, else the verdict
    owned: bool
    confidence: Confidence
    label: str | None = None  # "limited history"
    rule_id: str  # VP.matrix.fair_value×strong_momentum
    value_band: str | None  # high / fair / low (None when informational)
    momentum_band: str | None  # strong / neutral / weak (None when informational)
    value_band_raw: str | None = None
    momentum_band_raw: str | None = None
    held_by_hysteresis: list[str] = Field(default_factory=list)
    value_level: int | None = None
    momentum_level: int | None = None
    vetoes: list[str] = Field(default_factory=list)
    informational_lenses: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    trail: list[str] = Field(default_factory=list)
    thesis_status: str = "NOT_SET"
    override: dict[str, Any] | None = None
    prev_verdict: str | None = None
    prev_action: str | None = None
    changed: bool = False
    direction: Literal["upgrade", "downgrade", "same", "new"] = "new"
    drivers: list[dict[str, Any]] = Field(default_factory=list)


def _min_conf(*levels: Confidence) -> Confidence:
    return min(levels, key=lambda c: CONF_RANK[c])


def _cell_for(
    policy: VerdictPolicy, row: str, col: str, value_conf: Confidence, value_flags: list[str]
) -> tuple[Cell, str]:
    cell = policy.matrix[row][col]
    rule = f"VP.matrix.{row}_value×{col}_momentum"
    for r in policy.refinements:
        if r.cell != f"{row}/{col}":
            continue
        trapped = bool(
            r.requires_no_flag_prefix
            and any(f.startswith(r.requires_no_flag_prefix) for f in value_flags)
        )
        if not trapped and CONF_RANK[value_conf] >= CONF_RANK[r.min_value_confidence]:
            return Cell(
                verdict=r.verdict, qualifier=r.qualifier, momentum_led=cell.momentum_led
            ), rule + ".refined"
    return cell, rule


def decide(inp: PolicyInput, policy: VerdictPolicy) -> VerdictResult:
    trail: list[str] = []
    reasons: list[str] = []
    held: list[str] = []
    value, mom = inp.value, inp.momentum
    informational = [lid for lid in inp.other_lenses if lid not in policy.policy_lens_ids]
    prev = inp.prev or PrevState()

    # 1. informational lenses
    value_info = value is None or value.informational or value.score is None
    mom_info = mom is None or mom.informational or mom.score is None
    vetoes = sorted(set((value.vetoes if value else []) + (mom.vetoes if mom else [])))
    value_flags = value.flags if value else []

    v_level: int | None = None
    m_level: int | None = None
    v_raw = m_raw = None
    if value_info:
        row = policy.informational_value_row
        trail.append(f"value lens informational: placed in the {row}-value row")
        reasons.append("value lens informational (limited history): Fair-value row, Low confidence")
    else:
        assert value is not None and value.score is not None
        b = policy.value_bands
        v_raw = raw_level(value.score, b.low, b.high)
        v_level, held_v = level_with_hysteresis(
            value.score, b.low, b.high, policy.hysteresis, prev.value_level
        )
        row = ROW[LEVELS[v_level]]
        if held_v:
            held.append("value")
            trail.append(
                f"value {value.score:.0f}: raw band {ROW[LEVELS[v_raw]]}, held at {row} by hysteresis (±{policy.hysteresis:g})"
            )
            reasons.append(
                f"value score {value.score:.0f} is within {policy.hysteresis:g} points of a cut-off: band held at {row}"
            )
        else:
            trail.append(f"value {value.score:.0f} → {row}")

    col: str
    if mom_info:
        col = "neutral"
        trail.append("momentum lens informational: verdict from vetoes only")
        reasons.append(
            "momentum lens informational (under 126 sessions): vetoes only, WATCH at best"
        )
    else:
        assert mom is not None and mom.score is not None
        b = policy.momentum_bands
        m_raw = raw_level(mom.score, b.low, b.high)
        m_level, held_m = level_with_hysteresis(
            mom.score, b.low, b.high, policy.hysteresis, prev.momentum_level
        )
        col = COL[LEVELS[m_level]]
        if held_m:
            held.append("momentum")
            trail.append(
                f"momentum {mom.score:.0f}: raw band {COL[LEVELS[m_raw]]}, held at {col} by hysteresis (±{policy.hysteresis:g})"
            )
            reasons.append(
                f"momentum score {mom.score:.0f} is within {policy.hysteresis:g} points of a cut-off: band held at {col}"
            )
        else:
            trail.append(f"momentum {mom.score:.0f} → {col}")
        # the lens's own view can be stricter than the score band (stage 3/4, confirmed exits)
        if mom.view == "WEAK" and col != "weak":
            col = "weak"
            trail.append("momentum view WEAK (stage or exit signal): column weak")
            reasons.append("; ".join(mom.explanations[:1]) or "momentum view is weak")
        gate = mom.details.get("strong_gate")
        if col == "strong" and gate and not gate.get("passed", True):
            col = "neutral"
            failed = ", ".join(gate.get("failed", [])) or "a structural test"
            trail.append(
                f"strong needs Trend Template, stage 2 and RS; failed: {failed}: column neutral"
            )
            reasons.append(f"momentum score is strong but {failed} not met")

    # 3. regime and blockers
    if col == "strong":
        moves = policy.regime_momentum_downgrade.get(inp.regime, {})
        if "strong" in moves:
            col = moves["strong"]
            trail.append(f"regime {inp.regime}: strong momentum counted as {col}")
            reasons.append(f"{inp.regime} regime: strong momentum is held at {col}")
        fired = [s for s in (mom.signals if mom else []) if s in policy.momentum_blockers]
        if col == "strong" and fired:
            col = "neutral"
            trail.append(f"{', '.join(fired)} blocks a momentum-led buy: column neutral")
            reasons.append(f"{', '.join(fired)} fired: no momentum-led buy")

    # 4. the verdict
    value_conf: Confidence = value.confidence if value else "Low"
    mom_conf: Confidence = mom.confidence if mom else "Low"
    if mom_info and not vetoes:
        verdict, qualifier, rule = (
            policy.informational_momentum_verdict,
            None,
            "VP.limited_history.momentum",
        )
    elif vetoes:
        cell = policy.veto_matrix["neutral" if mom_info else col]
        verdict, qualifier = cell.verdict, cell.qualifier
        rule = f"VP.veto.{'informational' if mom_info else col}_momentum"
        trail.append(f"veto {', '.join(vetoes)} → {verdict}")
        reasons.append("veto: " + ", ".join(vetoes))
    else:
        cell, rule = _cell_for(policy, row, col, value_conf, value_flags)
        verdict, qualifier = cell.verdict, cell.qualifier
        trail.append(f"{rule} → {verdict}")

    confidence = _min_conf(value_conf, mom_conf, inp.data_confidence)
    if value_info or mom_info:
        confidence = "Low"
    label = policy.limited_history_label if (value_info or mom_info) else None

    # not-owned remap, owned wording
    if not inp.owned and verdict in policy.not_owned_remap:
        verdict = policy.not_owned_remap[verdict]
    action: str | None = None
    if inp.owned:
        action = policy.owned_wording[verdict]
        if (
            action == "ADD"
            and inp.weight_pct is not None
            and inp.target_weight_pct is not None
            and inp.weight_pct >= inp.target_weight_pct
        ):
            action = "HOLD"
            trail.append("at or above target weight: ADD becomes HOLD")
        if inp.thesis_status == "BROKEN":
            action = policy.thesis_broken_action
            reasons.append("thesis BROKEN: exit suggested")
            trail.append("thesis BROKEN → " + action)

    # 5. override
    override_block = None
    if inp.override is not None and inp.override.field == "verdict":
        original = verdict
        verdict = inp.override.value
        if inp.owned:
            action = policy.owned_wording.get(verdict, action)
        override_block = {
            "id": inp.override.id,
            "from": original,
            "to": verdict,
            "reason": inp.override.reason,
            "expires_on": inp.override.expires_on.isoformat(),
        }
        trail.append(
            f"override {inp.override.id}: {original} → {verdict} until {inp.override.expires_on}"
        )

    headline = action if inp.owned and action else verdict
    order = {v: i for i, v in enumerate(policy.verdict_order)}
    changed, direction = False, "new"
    if prev.verdict is not None:
        changed = prev.verdict != verdict or (
            inp.owned and prev.action is not None and prev.action != action
        )
        if prev.verdict == verdict:
            direction = "same"
        else:
            direction = (
                "upgrade" if order.get(verdict, 99) < order.get(prev.verdict, 99) else "downgrade"
            )

    return VerdictResult(
        policy_version=policy.policy_version,
        verdict=verdict,
        qualifier=qualifier,
        action=action,
        headline=headline,
        owned=inp.owned,
        confidence=confidence,
        label=label,
        rule_id=rule,
        value_band=None if value_info else row,
        momentum_band=None if mom_info else col,
        value_band_raw=None if v_raw is None else ROW[LEVELS[v_raw]],
        momentum_band_raw=None if m_raw is None else COL[LEVELS[m_raw]],
        held_by_hysteresis=held,
        value_level=v_level,
        momentum_level=m_level,
        vetoes=vetoes,
        informational_lenses=informational,
        reasons=reasons,
        trail=trail,
        thesis_status=inp.thesis_status,
        override=override_block,
        prev_verdict=prev.verdict,
        prev_action=prev.action,
        changed=changed,
        direction=direction,  # type: ignore[arg-type]
    )
