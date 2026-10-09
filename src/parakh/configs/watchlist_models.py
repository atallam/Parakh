"""config/watchlist.yaml (plan 06 §8; F14)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Cap = Literal["large", "mid", "small"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FadeRule(_Strict):
    outside_top_pct: float = Field(gt=0, le=100)
    consecutive_runs: int = Field(ge=1)


class UrgentAdds(_Strict):
    enabled: bool
    max_per_cap_per_week: int = Field(ge=0)
    signals: list[str]


class SystemWatchlistConfig(_Strict):
    capacity: dict[Cap, int]
    min_stay_cycles: int = Field(ge=0)
    bump_margin_points: float = Field(ge=0)
    fade_rule: FadeRule
    urgent_adds: UrgentAdds

    @model_validator(mode="after")
    def _all_caps(self) -> SystemWatchlistConfig:
        missing = {"large", "mid", "small"} - set(self.capacity)
        if missing:
            raise ValueError(f"capacity needs every cap, missing {sorted(missing)}")
        if any(v < 1 for v in self.capacity.values()):
            raise ValueError("capacity must be at least 1 per cap")
        return self


class TopCombined(_Strict):
    top_pct: float = Field(gt=0, le=100)


class MomentumSetup(_Strict):
    signals: list[str]
    blocked_by_signals: list[str]
    blocked_regimes: list[str]


class ValueZone(_Strict):
    views: list[str]
    min_quality_subscore: float = Field(ge=0, le=1)
    trap_flag_text: list[str]


class SmartMoney(_Strict):
    signals: list[str]
    event_codes: list[str]
    buy_text: list[str]
    exclude_text: list[str]
    lookback_days: int = Field(ge=1)


class Sources(_Strict):
    top_combined: TopCombined
    momentum_setup: MomentumSetup
    value_zone: ValueZone
    smart_money: SmartMoney


class WeakFlag(_Strict):
    bottom_pct: float = Field(gt=0, le=100)
    months: int = Field(ge=1)


class MyWatchlistConfig(_Strict):
    default_review_months: int = Field(ge=1)
    weak_flag: WeakFlag
    soft_size_warning_per_cap: int = Field(ge=1)


class PromotionConfig(_Strict):
    min_months_on_system: int = Field(ge=1)
    stay_top_pct: float = Field(gt=0, le=100)
    max_rejections_before_mute: int = Field(ge=1)


class SuggestionsConfig(_Strict):
    expire_after_days: int = Field(ge=1)
    snooze_days: int = Field(ge=1)
    telegram_max_cards: int = Field(ge=0, le=10)


class AgentProposalsConfig(_Strict):
    max_per_run: int = Field(ge=0)
    dedupe_open: bool


class WatchlistConfig(_Strict):
    system_watchlist: SystemWatchlistConfig
    sources: Sources
    liquidity_floor_ok_required: bool
    my_watchlist: MyWatchlistConfig
    promotion: PromotionConfig
    suggestions: SuggestionsConfig
    agent_proposals: AgentProposalsConfig
