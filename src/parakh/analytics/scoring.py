"""Shared scoring helpers for the value and momentum lenses (plan 01 §4, plan 02 §6).

A sub-score is the weighted mean of its components, each mapped linearly to 0–1. A missing
metric is never scored as zero: it drops out and the remaining weights re-normalise
(AC-F04.8). The share of weight that dropped out lowers confidence one level per step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from parakh.configs.lens_models import Component

Confidence = Literal["High", "Med", "Low"]
LEVELS: tuple[Confidence, ...] = ("High", "Med", "Low")


def linear(x: float, bad: float, good: float) -> float:
    """Map x to 0–1: `bad` → 0, `good` → 1, clipped. Works for either ordering."""
    t = (x - bad) / (good - bad)
    return max(0.0, min(1.0, t))


@dataclass
class SubScore:
    value: float | None
    used: list[str] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)  # metric id → reason
    weight_total: float = 0.0
    weight_missing: float = 0.0
    contributions: dict[str, float] = field(default_factory=dict)  # metric id → points (0–1)

    @property
    def missing_share(self) -> float:
        return self.weight_missing / self.weight_total if self.weight_total else 1.0


def score_subscore(
    components: Sequence[Component],
    metrics: Mapping[str, float | None],
    na_reasons: Mapping[str, str] | None = None,
) -> SubScore:
    reasons = na_reasons or {}
    total = sum(c.weight for c in components)
    used_weight = 0.0
    acc = 0.0
    out = SubScore(None, weight_total=total)
    for c in components:
        v = metrics.get(c.metric)
        if v is None:
            out.missing[c.metric] = reasons.get(c.metric, "not available")
            out.weight_missing += c.weight
            continue
        pts = linear(v, c.bad, c.good)
        out.contributions[c.metric] = pts
        out.used.append(c.metric)
        acc += pts * c.weight
        used_weight += c.weight
    out.value = acc / used_weight if used_weight else None
    return out


def combine(
    weights: Mapping[str, float], subs: Mapping[str, SubScore]
) -> tuple[float | None, float, dict[str, float]]:
    """Weighted 0–100 score over the sub-scores that exist; returns (score, missing share, parts).

    `parts` is each sub-score's contribution in score points, which feeds the attribution
    (AC-F08.4). A sub-score with no computable metric drops out and the rest re-normalise.
    """
    total = sum(weights.values())
    present = {k: w for k, w in weights.items() if subs[k].value is not None}
    if not present or total <= 0:
        return None, 1.0, {}
    wsum = sum(present.values())
    score = sum(subs[k].value * w for k, w in present.items()) / wsum * 100  # type: ignore[operator]
    parts = {k: subs[k].value * w / wsum * 100 for k, w in present.items()}  # type: ignore[operator]
    # missing share counts both whole sub-scores and the gaps inside the ones that exist
    missing = 1 - sum(w * (1 - subs[k].missing_share) for k, w in present.items()) / total
    return round(score, 2), missing, {k: round(v, 3) for k, v in parts.items()}


def lower(level: Confidence, steps: int) -> Confidence:
    return LEVELS[min(len(LEVELS) - 1, LEVELS.index(level) + max(0, steps))]


def cap_at(level: Confidence, ceiling: Confidence) -> Confidence:
    return LEVELS[max(LEVELS.index(level), LEVELS.index(ceiling))]


def confidence_from_missing(share: float, step: float) -> Confidence:
    return lower("High", int(share / step + 1e-9))
