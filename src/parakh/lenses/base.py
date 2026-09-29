"""The Lens contract (plan 04 §1.2). Every investing style is a Lens that returns a LensResult.

The platform computes a lens's declared metrics first, then calls `evaluate`. Results are
rendered, stored and alerted generically, so a new lens needs no new plumbing (5-file recipe,
plan 04 §1.3). Contract tests run for every registered lens (AC-F18.2).
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Confidence = Literal["High", "Med", "Low"]
HistoryClass = Literal["H0", "H1", "H2", "H3"]  # limited-history classes (D24; plan 01 §3.1)


class StockContext(BaseModel):
    """Everything a lens may read about one stock at one as-of date. No I/O inside lenses."""

    model_config = ConfigDict(frozen=True)

    isin: str
    symbol: str
    asof: dt.date
    profile: str
    history_class: HistoryClass = "H3"
    metrics: dict[str, float | None] = Field(default_factory=dict)  # MET.* id → value
    owned: bool = False


class LensConfig(BaseModel):
    """A lens's thresholds and weights, from config/lenses/<id>.yaml (Phase 2)."""

    model_config = ConfigDict(frozen=True)

    lens_version: str
    params: dict[str, Any] = Field(default_factory=dict)


class LensResult(BaseModel):
    """Standard output every lens must return."""

    lens_id: str  # "value", "momentum", "dividend"
    lens_version: str  # semver; stored in every snapshot
    score: float | None = Field(default=None, ge=0, le=100)  # None = not applicable
    subscores: dict[str, float] = Field(default_factory=dict)  # 0–1 each
    view: str  # lens-specific label, e.g. "UNDERVALUED"
    confidence: Confidence
    informational: bool = False  # limited history or new lens: shown, not used by the verdict
    metrics_used: list[str] = Field(default_factory=list)  # MET.* ids (traceability)
    signals: list[str] = Field(default_factory=list)  # signal ids fired
    vetoes: list[str] = Field(default_factory=list)  # RULE.* ids
    explanations: list[str] = Field(default_factory=list)  # top drivers

    @field_validator("subscores")
    @classmethod
    def _unit_interval(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: x for k, x in v.items() if not 0.0 <= x <= 1.0}
        if bad:
            raise ValueError(f"subscores must be within 0–1: {bad}")
        return v


class Lens(ABC):
    lens_id: ClassVar[str]
    lens_version: ClassVar[str]
    required_metrics: ClassVar[list[str]]  # declared, so the platform computes them first
    applicable_profiles: ClassVar[list[str]]  # empty = every profile

    def applies_to(self, ctx: StockContext) -> bool:
        return not self.applicable_profiles or ctx.profile in self.applicable_profiles

    @abstractmethod
    def evaluate(self, ctx: StockContext, cfg: LensConfig) -> LensResult: ...
