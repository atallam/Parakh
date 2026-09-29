"""Corporate actions: price back-adjustment and gap detection (plan 04 §4 #1, #8; spike ④).

Everything is keyed on ISIN. Splits and bonuses change the share count without changing value,
so prices before the ex-date are multiplied by a factor < 1. A price jump over the threshold
with no recorded action is a data-quality failure that blocks the verdict, never a signal.

Known pilot events used in the tests (checked 29 Sep 2026):
- MAZDOCK split 1:2 (face value ₹10 → ₹5), ex-date 27 Dec 2024.
- HDFCBANK bonus 1:1, ex-date 26 Aug 2025.
- M&M bonus 1:1, FY2018 (seen as "New Bonus Shares" in the Screener export).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

ActionType = Literal["split", "bonus", "rights", "demerger", "dividend"]
MAX_UNEXPLAINED_MOVE_RATIO = 0.40  # why: plan 04 §4 #8: a >40% one-day jump needs a reason


@dataclass(frozen=True)
class CorporateAction:
    isin: str
    ex_date: dt.date
    type: ActionType
    # split: old_fv / new_fv (10 → 5 gives 2.0). bonus: new shares per held share (1:1 gives 1.0).
    ratio: float
    source: str = "manual"

    @property
    def price_factor(self) -> float:
        """Multiply pre-ex-date prices by this to make them comparable with post-ex-date prices."""
        if self.type == "split":
            return 1.0 / self.ratio
        if self.type == "bonus":
            return 1.0 / (1.0 + self.ratio)
        raise NotImplementedError(
            f"{self.type}: handled explicitly (plan 04 §4 #1), not by a factor"
        )


def back_adjust(
    closes: dict[dt.date, float], actions: list[CorporateAction]
) -> dict[dt.date, float]:
    """Prices adjusted so every day is comparable with the latest share structure."""
    factors = [(a.ex_date, a.price_factor) for a in actions if a.type in ("split", "bonus")]
    out = {}
    for day, price in closes.items():
        factor = 1.0
        for ex_date, f in factors:
            if day < ex_date:
                factor *= f
        out[day] = price * factor
    return out


@dataclass(frozen=True)
class Gap:
    day: dt.date
    prev_close: float
    close: float
    move_ratio: float
    explained_by: CorporateAction | None


def find_gaps(
    closes: dict[dt.date, float],
    actions: list[CorporateAction],
    threshold: float = MAX_UNEXPLAINED_MOVE_RATIO,
) -> list[Gap]:
    """Day-over-day moves beyond the threshold, each matched to an action on that day if any."""
    by_date = {a.ex_date: a for a in actions}
    days = sorted(closes)
    gaps = []
    for prev, day in zip(days, days[1:], strict=False):
        p0, p1 = closes[prev], closes[day]
        if p0 <= 0:
            continue
        move = abs(p1 / p0 - 1.0)
        if move > threshold:
            gaps.append(Gap(day, p0, p1, move, by_date.get(day)))
    return gaps


def unexplained(gaps: list[Gap]) -> list[Gap]:
    return [g for g in gaps if g.explained_by is None]
