"""Schemas for the Phase 2 lens, regime and verdict-policy configs (plan 01, 02, 00 §5).

Thresholds live in YAML only (plan 04 §3.2); each key carries a `# why:` comment there.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field, model_validator

from parakh.configs.models import Cap, Profile, Strict

Level = Literal["High", "Med", "Low"]


class Component(Strict):
    """One metric inside a sub-score: linear 0→1 between `bad` and `good` (either order)."""

    metric: str
    bad: float
    good: float
    weight: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _distinct(self) -> Component:
        if self.bad == self.good:
            raise ValueError(f"{self.metric}: bad and good must differ")
        return self


class ConfidenceRules(Strict):
    step_missing_weight: float = Field(
        gt=0, le=1
    )  # one level lost per this share of weight missing


# -- momentum.yaml ---------------------------------------------------------------------------
class MomentumCap(Strict):
    benchmark: str
    secondary_benchmark: str
    over_extension: float = Field(gt=0)  # fraction above the 200 DMA
    breakout_volume_x: float = Field(gt=1)
    trailing_stop_pct: float = Field(gt=0, lt=1)
    trailing_stop_atr_x: float = Field(gt=0)
    min_traded_value_cr: float | None = None
    weight_shift: dict[str, float] = {}


class MomentumHistory(Strict):
    listing_exclusion_sessions: int = Field(ge=0)
    listing_window_days: int = Field(ge=0)  # history "starts at listing" if it begins this close
    min_sessions: dict[str, int]
    since_listing_min_sessions: int  # high/low and vol substitutes need at least this many
    informational_below: int
    confidence_cap_below: int


class TrendTemplate(Strict):
    above_52w_low: float
    within_52w_high: float
    rs_percentile_min: float
    ma200_rising_sessions: int
    rs_percentile_unavailable: Literal["skip", "fail"]


class StageRules(Strict):
    slope_sessions: int
    flat_tolerance: float  # |150 DMA change over slope_sessions| below this is "flat"
    prior_trend_sessions: int
    points: dict[int, float]  # stage → 0–1 points in the trend sub-score


class MomentumViews(Strict):
    strong_score: float
    weak_score: float
    strong_template_min: int
    neutral_template_min: int
    strong_rs_percentile_min: float


class SignalParams(Strict):
    confirm_closes: int = Field(ge=1)
    confirm_buffer: float = Field(ge=0)
    base_min_sessions: int
    base_max_range: float
    rs_new_high_sessions: int
    breakout_volume_window: int
    pullback_touch: float
    bounce_volume_x: float
    below_ma_sessions: int  # M06: sessions below the 200 DMA before a reclaim counts
    divergence_lookback: int
    divergence_near_high: float
    rs_percentile_drop_from: float
    rs_percentile_drop_to: float
    climax_gain: float
    climax_sessions: int
    gap_threshold: float
    gap_volume_x: float
    gap_hold_sessions: int
    vcp_min_pullbacks: int
    cross_lookback: int  # a cross within this many sessions counts as "recent"
    distribution_days_min: int  # M22
    distribution_window: int
    distribution_drop: float
    stage_change_sessions: int  # M02/M22 compare the stage this many sessions ago


class MomentumConfig(Strict):
    lens_version: str
    weights: dict[str, float]
    cap_settings: dict[Cap, MomentumCap]
    history: MomentumHistory
    trend_template: TrendTemplate
    stage: StageRules
    views: MomentumViews
    signals: SignalParams
    confidence: ConfidenceRules
    subscores: dict[str, list[Component]]
    absolute_momentum_min: float  # dual momentum: 12M return must beat this (liquid-fund proxy)
    volatility_window: int
    atr_window: int
    rsi_window: int

    @model_validator(mode="after")
    def _weights(self) -> MomentumConfig:
        if abs(sum(self.weights.values()) - 100) > 1e-9:
            raise ValueError(f"momentum weights must sum to 100, got {sum(self.weights.values())}")
        unknown = set(self.subscores) ^ set(self.weights)
        if unknown:
            raise ValueError(f"weights and subscores differ on {sorted(unknown)}")
        return self


# -- regime.yaml -----------------------------------------------------------------------------
class RegimeConfig(Strict):
    risk_on_breadth_min: float
    risk_off_breadth_max: float
    breadth_unavailable: Literal["benchmark_only"]
    vix_percentile_high: float
    vix_rising_sessions: int
    ma_long: int
    ma_short: int
    market_valuation_top_decile: float  # percentile at/above which MoS uplift applies
    mos_uplift_pp: float
    risk_off_view_cap: str
    neutral_template_min: int
    flow_headwind_cr: float


# -- value.yaml ------------------------------------------------------------------------------
class ValueCap(Strict):
    weights: dict[str, float]
    required_mos: float
    min_traded_value_cr: float | None = None


class ValueHistory(Strict):
    h2_min_months: int
    h1_min_months: int
    own_history_min_years: dict[str, int]  # metric key → years of data needed


class ProfileSpec(Strict):
    description: str
    drop: list[str] = []  # metric ids removed
    add: dict[str, list[Component]] = {}  # sub-score → extra components
    replace: dict[str, list[Component]] = {}  # sub-score → whole component list
    informational: bool = False  # value lens informational by profile (new-age)
    intrinsic_methods: list[str]
    vetoes_disabled: list[str] = []
    notes: list[str] = []


class ValueVetoes(Strict):
    pledge_pct: dict[Cap, float]
    negative_cfo_years_of_5: int
    nnpa_pct_max: float
    runway_months_min: float


class ValueViews(Strict):
    undervalued_score: float
    fair_score: float
    overvalued_above_high: float  # price this far above intrinsic high → OVERVALUED


class Scenario(Strict):
    growth_mult: float  # multiple of the base EPS growth
    exit_pe_mult: float  # multiple of the stock's own median P/E
    probability: float


class Archetype(Strict):
    slow_grower_max_eps_cagr: float
    fast_grower_min_eps_cagr: float
    asset_play_max_pb: float
    cyclical_margin_cv: float = 0.0  # reserved


class Dcf(Strict):
    cost_of_equity: float
    terminal_growth: float
    fade_years: int
    explicit_years: int
    growth_cap: float
    reverse_dcf_max_growth: float
    holdco_discount: float
    holdco_discount_range: tuple[float, float]
    graham_multiplier: float
    hurdle_rate: float
    irr_years: int
    scenarios: dict[str, Scenario]


class HistoryBreak(Strict):
    isin: str
    break_on: dt.date
    reason: str


class ValueConfig(Strict):
    lens_version: str
    cap_settings: dict[Cap, ValueCap]
    history: ValueHistory
    profiles: dict[Profile, ProfileSpec]
    subscores: dict[str, list[Component]]  # the "standard" component list
    vetoes: ValueVetoes
    views: ValueViews
    dcf: Dcf
    confidence: ConfidenceRules
    history_breaks: list[HistoryBreak] = []
    informational_min_valuation_weight: float  # below this share computable → informational
    g_sec_yield: float | None = (
        None  # 10-year G-sec, for earnings yield vs bonds (config until F16 feeds it)
    )
    # Screener's Borrowings line already contains Ind AS 116 lease liabilities (IndiGo: 77,749 Cr
    # against 75,943 Cr of leases). When true, the airline metrics do not add the filed lease
    # liabilities a second time; they use them as a sanity check only.
    borrowings_include_leases: bool = False
    flags: dict[str, float]
    archetype: Archetype

    @model_validator(mode="after")
    def _cap_weights(self) -> ValueConfig:
        for cap, spec in self.cap_settings.items():
            if abs(sum(spec.weights.values()) - 100) > 1e-9:
                raise ValueError(f"value weights for {cap} must sum to 100")
            if set(spec.weights) != {
                "valuation",
                "quality",
                "balance_sheet",
                "growth",
                "governance",
            }:
                raise ValueError(f"value weights for {cap} need the five sub-scores")
        return self


# -- verdict_policy.yaml ---------------------------------------------------------------------
class Band(Strict):
    high: float  # ≥ this is "high" / "strong"
    low: float  # < this is "low" / "weak"


class Cell(Strict):
    """One cell of the decision matrix (plan 00 §5)."""

    verdict: str
    qualifier: str | None = None  # "staggered", "momentum-led": shown beside the verdict
    momentum_led: bool = False  # true when the cell is a buy that rests on momentum alone


class Refinement(Strict):
    """A cell that splits on a flag: e.g. cheap but falling is ACCUMULATE unless a value trap shows."""

    cell: str  # "high/weak"
    verdict: str
    qualifier: str | None = None
    requires_no_flag_prefix: str | None = None  # no value-lens flag starting with this text
    min_value_confidence: Level = "Med"


class VerdictPolicy(Strict):
    policy_version: str
    value_bands: Band
    momentum_bands: Band
    hysteresis: float = Field(ge=0)
    matrix: dict[str, dict[str, Cell]]  # value row → momentum column → cell
    refinements: list[Refinement] = []
    veto_matrix: dict[str, Cell]  # momentum column → cell
    owned_wording: dict[str, str]  # verdict → ADD / HOLD / TRIM / EXIT
    not_owned_remap: dict[str, str] = {}  # e.g. SELL → AVOID for a stock you do not hold
    thesis_broken_action: str = "EXIT"
    verdict_order: list[str]  # strongest first
    regime_momentum_downgrade: dict[str, dict[str, str]] = {}  # regime → {column: column}
    momentum_blockers: list[str] = []  # signal ids that stop a momentum-led buy (M27)
    informational_value_row: str
    informational_momentum_verdict: str  # when the momentum lens is informational: WATCH at best
    limited_history_label: str
    top_drivers: int = Field(gt=0)
    policy_lens_ids: list[str] = ["value", "momentum"]  # lenses with a policy row (AC-F08.3)

    @model_validator(mode="after")
    def _complete(self) -> VerdictPolicy:
        rows = {"high", "fair", "low"}
        cols = {"strong", "neutral", "weak"}
        if set(self.matrix) != rows or any(set(v) != cols for v in self.matrix.values()):
            raise ValueError("matrix needs rows high/fair/low and columns strong/neutral/weak")
        if set(self.veto_matrix) != cols:
            raise ValueError("veto_matrix needs columns strong/neutral/weak")
        if self.informational_value_row not in rows:
            raise ValueError("informational_value_row must be high, fair or low")
        known = set(self.verdict_order)
        cells = [c for r in self.matrix.values() for c in r.values()] + list(
            self.veto_matrix.values()
        )
        used = {c.verdict for c in cells} | {r.verdict for r in self.refinements}
        used |= (
            {self.informational_momentum_verdict}
            | set(self.owned_wording)
            | set(self.not_owned_remap.values())
        )
        if used - known:
            raise ValueError(f"verdicts missing from verdict_order: {sorted(used - known)}")
        for r in self.refinements:
            row, _, col = r.cell.partition("/")
            if row not in rows or col not in cols:
                raise ValueError(f"refinement cell {r.cell!r} must look like high/weak")
        for regime, moves in self.regime_momentum_downgrade.items():
            if not set(moves) | set(moves.values()) <= cols:
                raise ValueError(f"regime_momentum_downgrade[{regime}] uses unknown columns")
        if not set(self.owned_wording.values()) <= {"ADD", "HOLD", "TRIM", "EXIT"}:
            raise ValueError("owned_wording values must be ADD, HOLD, TRIM or EXIT")
        return self


# -- overrides.yaml (plan 10 §8: a reason and an expiry are required) ---------------------------
class Override(Strict):
    id: str
    isin: str
    field: Literal["verdict", "profile", "archetype", "thesis_status"]
    value: str
    reason: str = Field(min_length=10)
    set_on: dt.date
    expires_on: dt.date
    set_by: str = "avinash"

    @model_validator(mode="after")
    def _expiry(self) -> Override:
        if self.expires_on <= self.set_on:
            raise ValueError(f"override {self.id}: expires_on must be after set_on")
        if (self.expires_on - self.set_on).days > 366:
            raise ValueError(
                f"override {self.id}: longest allowed life is one year; re-set it to extend"
            )
        return self


class OverridesConfig(Strict):
    overrides: list[Override] = []

    @model_validator(mode="after")
    def _unique(self) -> OverridesConfig:
        ids = [o.id for o in self.overrides]
        if len(ids) != len(set(ids)):
            raise ValueError("override ids must be unique")
        return self

    def active(self, isin: str, asof: dt.date, field: str | None = None) -> list[Override]:
        return [
            o
            for o in self.overrides
            if o.isin == isin
            and o.set_on <= asof <= o.expires_on
            and (field is None or o.field == field)
        ]


# -- portfolio.yaml (limits and tax rates; plan 05 §2, §4) --------------------------------------
class TaxRates(Strict):
    stcg_pct: float
    ltcg_pct: float
    ltcg_exempt_inr: float
    cess_pct: float
    long_term_days: int


class PortfolioConfig(Strict):
    single_stock_max_weight_pct: float
    sector_max_weight_pct: float
    near_ltcg_days: int  # flag "LTCG in < N days" in the segment summary
    tax: TaxRates


# -- indices.yaml ------------------------------------------------------------------------------
class IndexSpec(Strict):
    name: str
    yahoo: str


class IndicesConfig(Strict):
    indices: list[IndexSpec]

    def yahoo_for(self, name: str) -> str | None:
        return next((i.yahoo for i in self.indices if i.name == name), None)
