"""The NSE calendar (AC-F11.1, AC-F12.5): holidays, special sessions and the monthly as-of date."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from parakh.calendar import Calendar, default_calendar

D = dt.date


@pytest.fixture(scope="module")
def cal() -> Calendar:
    return default_calendar()


@pytest.mark.ac("AC-F11.1")
@pytest.mark.parametrize(
    ("run_day", "expected"),
    [
        (D(2026, 11, 2), D(2026, 10, 30)),  # 31 Oct is a Saturday
        (D(2026, 12, 2), D(2026, 11, 30)),
        (D(2026, 10, 2), D(2026, 9, 30)),  # the 2nd itself is a holiday (Gandhi Jayanti)
        (D(2026, 4, 2), D(2026, 3, 30)),  # 31 Mar is Mahavir Jayanti, 30 Mar the last session
        (D(2026, 1, 2), D(2025, 12, 31)),  # year boundary: 2025 is not in the config, Wednesday
    ],
)
def test_monthly_asof_is_the_last_trading_day_of_the_previous_month(cal, run_day, expected) -> None:
    assert cal.monthly_asof(run_day) == expected


@pytest.mark.ac("AC-F12.5")
def test_holidays_and_weekends_are_not_trading_days(cal) -> None:
    assert not cal.is_trading_day(D(2026, 10, 2))  # Gandhi Jayanti
    assert not cal.is_trading_day(D(2026, 11, 10))  # Diwali-Balipratipada, NSE's date
    assert not cal.is_trading_day(D(2026, 10, 3))  # Saturday
    assert cal.is_trading_day(D(2026, 10, 5))
    assert cal.holiday_name(D(2026, 10, 2)) == "Mahatma Gandhi Jayanti"
    assert cal.holiday_name(D(2026, 10, 3)) == "weekend"
    assert cal.holiday_name(D(2026, 10, 5)) is None


def test_muhurat_session_is_a_holiday_for_the_watcher(cal) -> None:
    assert cal.is_special_session(D(2026, 11, 8))
    assert not cal.is_trading_day(D(2026, 11, 8))


def test_special_session_bar_is_dropped_from_price_frames(cal) -> None:
    frame = pd.DataFrame(
        {"trade_date": [D(2026, 11, 6), D(2026, 11, 8), D(2026, 11, 9)], "close": [1.0, 2.0, 3.0]}
    )
    assert list(cal.drop_special_sessions(frame)["close"]) == [1.0, 3.0]


def test_walking_the_calendar(cal) -> None:
    assert cal.previous_trading_day(D(2026, 10, 5)) == D(2026, 10, 1)  # skips 2 Oct and the weekend
    assert cal.next_trading_day(D(2026, 11, 9)) == D(2026, 11, 11)
    assert cal.trading_days_between(D(2026, 10, 1), D(2026, 10, 5)) == 1
    assert cal.add_trading_days(D(2026, 10, 1), 10) == D(2026, 10, 16)  # 20 Oct is Dussehra
    assert cal.last_n_trading_days(D(2026, 10, 7), 3) == [
        D(2026, 10, 5),
        D(2026, 10, 6),
        D(2026, 10, 7),
    ]


def test_unlisted_year_is_weekends_only_and_reported_as_a_gap(cal) -> None:
    assert cal.is_trading_day(D(2027, 1, 26))  # Republic Day is not known yet
    assert not cal.known(D(2027, 1, 26))
    assert cal.gaps(D(2026, 12, 10)) == [2027]
    assert cal.gaps(D(2026, 10, 4)) == []
