"""Schema for config/calibration.yaml (F17; plan 04 §2, plan 06 §6, plan 10 §5).

Every threshold the calibration, drift and replay code uses lives here, never in code (plan 04 §3.2).
A parameter that can be tuned in the walk-forward is capped (`max_tunable_parameters`) so the
backtest cannot be over-fitted by adding knobs (plan 04 §2, "out-of-sample discipline").
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from parakh.configs.models import Strict

Cap = Literal["large", "mid", "small"]


class CostSide(Strict):
    statutory_buy_bps: float  # STT + stamp duty + exchange and SEBI fees on a purchase
    statutory_sell_bps: float  # STT + exchange and SEBI fees on a sale
    impact_bps: dict[Cap, float]  # slippage and market impact per side, by cap


class PortfolioRules(Strict):
    top_pct: float = Field(gt=0, le=100)  # share of eligible names to hold
    min_score: float = Field(ge=0, le=100)  # a name below this momentum score is never bought
    buffer_pct: float = Field(gt=0, le=100)  # rank buffer: a holder stays while inside this share
    min_names: int = Field(ge=1)  # fewer eligible names than this and the month is held in cash
    rebalance_band_pct: float = Field(ge=0)  # trade an existing name only if it drifts this far
    initial_capital_inr: float = Field(gt=0)
    execution_lag_sessions: int = Field(ge=0)  # trade this many sessions after the signal close

    @model_validator(mode="after")
    def _buffer(self) -> PortfolioRules:
        if self.buffer_pct < self.top_pct:
            raise ValueError("buffer_pct must be at least top_pct")
        return self


class WalkForward(Strict):
    train_years: int = Field(ge=1)
    test_years: int = Field(ge=1)
    step_years: int = Field(ge=1)
    grid: dict[Literal["top_pct", "min_score"], list[float]]
    select_by: Literal["after_cost_sharpe", "after_cost_cagr"]
    max_tunable_parameters: int = Field(ge=1)

    @model_validator(mode="after")
    def _cap_parameters(self) -> WalkForward:
        if len(self.grid) > self.max_tunable_parameters:
            raise ValueError(
                f"{len(self.grid)} tunable parameters exceed max_tunable_parameters "
                f"({self.max_tunable_parameters}); plan 04 §2 caps the knobs"
            )
        if any(len(v) == 0 for v in self.grid.values()):
            raise ValueError("an empty grid axis")
        return self


class BacktestConfig(Strict):
    benchmark: str  # an indices.yaml name; buy-and-hold over the same dates
    risk_free_pct: float  # annual; for Sharpe
    min_history_sessions: int = Field(ge=1)  # a name needs this many sessions to be scored
    require_membership_history: bool  # refuse headline numbers without point-in-time membership
    membership_indices: dict[Cap, str]  # which index defines each cap's constituents
    portfolio: PortfolioRules
    costs: CostSide
    walk_forward: WalkForward


class OutcomesConfig(Strict):
    horizons_trading_days: dict[str, int]  # label → sessions, e.g. {"1M": 21, "3M": 63}
    min_observations: int = Field(ge=1)  # below this a hit rate is shown but not concluded
    delisted_gap_days: int = Field(
        ge=1
    )  # a series that ends this long before the horizon = delisted


class QuintileConfig(Strict):
    horizons_months: list[int]
    buckets: int = Field(ge=2)
    min_stocks_per_period: int = Field(ge=2)  # a month with fewer scored names is skipped
    min_periods: int = Field(ge=1)  # fewer usable months and the verdict is "insufficient"
    min_ic_t_stat: float  # mean rank-IC divided by its standard error
    primary_horizon_months: int


class AlertConfig(Strict):
    min_rated: int = Field(ge=1)  # below this a signal's precision is an anecdote
    target_precision_pct: float  # plan 09 go-live gate: at most 30% judged noise
    feedback_tags: list[str]  # optional reason tags for a 👎 from the Streamlit page


class ScorecardConfig(Strict):
    horizons_months: list[int]
    min_entries: int = Field(ge=1)  # per source; fewer and the row says "not enough yet"


class JournalConfig(Strict):
    default_review_months: int = Field(ge=1)
    max_field_chars: int = Field(ge=20)  # three short lines, not an essay
    actions: list[str]


class DriftConfig(Strict):
    baseline_months: int = Field(ge=2)
    min_stocks: int = Field(ge=2)  # PSI on fewer names is noise
    bins: int = Field(ge=3)
    psi_warn: float
    psi_alert: float
    verdict_mix_shift_pct: float  # largest change in any verdict's share, percentage points
    signal_rate_ratio_low: float  # fired-signal rate this month ÷ baseline, below → warn
    signal_rate_ratio_high: float

    @model_validator(mode="after")
    def _order(self) -> DriftConfig:
        if not 0 < self.psi_warn < self.psi_alert:
            raise ValueError("psi_warn must be positive and below psi_alert")
        return self


class ReplayConfig(Strict):
    score_tolerance: float  # points on the 0–100 scores
    price_tolerance_pct: float  # a stored close that moved more than this is a data change
    fields: list[str]  # snapshot fields that must reproduce exactly


class RestoreConfig(Strict):
    max_backup_age_days: int = Field(ge=1)
    min_rows_ratio: float = Field(gt=0, le=1.0)  # restored rows ÷ manifest rows must reach this


class CalibrationConfig(Strict):
    version: str
    backtest: BacktestConfig
    outcomes: OutcomesConfig
    quintiles: QuintileConfig
    alerts: AlertConfig
    scorecard: ScorecardConfig
    journal: JournalConfig
    drift: DriftConfig
    replay: ReplayConfig
    restore: RestoreConfig
