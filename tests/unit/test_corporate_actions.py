"""Corporate-action adjustment (spike ④; plan 04 §4 #1, #8). T-ADP-20…

Prices are illustrative round numbers placed on the real pilot ex-dates.
"""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.adapters.corporate_actions import CorporateAction, back_adjust, find_gaps, unexplained

MAZDOCK = "INE249Z01020"
HDFCBANK = "INE040A01034"
SPLIT = CorporateAction(MAZDOCK, dt.date(2024, 12, 27), "split", 2.0)
BONUS = CorporateAction(HDFCBANK, dt.date(2025, 8, 26), "bonus", 1.0)


def test_split_and_bonus_factors() -> None:
    """T-ADP-20"""
    assert SPLIT.price_factor == 0.5
    assert BONUS.price_factor == 0.5
    assert CorporateAction(
        HDFCBANK, dt.date(2025, 1, 1), "bonus", 0.5
    ).price_factor == pytest.approx(2 / 3)


def test_split_day_is_a_gap_explained_by_the_action_and_disappears_after_adjustment() -> None:
    """T-ADP-21: MAZDOCK around 27 Dec 2024."""
    closes = {
        dt.date(2024, 12, 24): 4400.0,
        dt.date(2024, 12, 26): 4420.0,
        dt.date(2024, 12, 27): 2215.0,
        dt.date(2024, 12, 30): 2230.0,
    }
    gaps = find_gaps(closes, [SPLIT])
    assert len(gaps) == 1 and gaps[0].explained_by == SPLIT and unexplained(gaps) == []
    adjusted = back_adjust(closes, [SPLIT])
    assert adjusted[dt.date(2024, 12, 26)] == pytest.approx(2210.0)
    assert find_gaps(adjusted, []) == []


def test_bonus_without_a_recorded_action_is_flagged() -> None:
    """T-ADP-22: plan 04 §4 #8: a >40% jump with no action blocks the verdict."""
    closes = {dt.date(2025, 8, 25): 1960.0, dt.date(2025, 8, 26): 975.0}
    gaps = find_gaps(closes, [])
    assert len(unexplained(gaps)) == 1
    assert gaps[0].move_ratio == pytest.approx(0.5025, abs=1e-3)


def test_multiple_actions_compound() -> None:
    """T-ADP-23"""
    early = CorporateAction(MAZDOCK, dt.date(2020, 1, 1), "bonus", 1.0)
    adjusted = back_adjust(
        {dt.date(2019, 12, 31): 800.0, dt.date(2025, 1, 2): 2000.0}, [early, SPLIT]
    )
    assert adjusted[dt.date(2019, 12, 31)] == pytest.approx(200.0)
    assert adjusted[dt.date(2025, 1, 2)] == 2000.0


def test_demergers_are_not_silently_factor_adjusted() -> None:
    """T-ADP-24: the parent continues and the child starts new history (plan 04 §4 #1)."""
    with pytest.raises(NotImplementedError):
        _ = CorporateAction(MAZDOCK, dt.date(2025, 1, 1), "demerger", 1.0).price_factor
