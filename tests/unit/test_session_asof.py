"""The daily jobs pick the latest session whose data can exist, even when GitHub starts them late."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.cli_watch import IST, session_asof
from parakh.configs import load_all

D = dt.date


@pytest.fixture(scope="module")
def bundle():  # type: ignore[no-untyped-def]
    return load_all()


def _at(day: dt.date, hh: int, mm: int) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (_at(D(2026, 10, 8), 18, 30), D(2026, 10, 8)),  # on time, Thursday evening
        (
            _at(D(2026, 10, 9), 0, 36),
            D(2026, 10, 8),
        ),  # the 6-hour-late run seen on 8 Oct (UTC 19:06)
        (_at(D(2026, 10, 9), 17, 44), D(2026, 10, 8)),  # a minute before the data is ready
        (_at(D(2026, 10, 9), 17, 45), D(2026, 10, 9)),  # data ready: today
        (_at(D(2026, 10, 10), 0, 30), D(2026, 10, 9)),  # Friday run that slips past midnight
        (_at(D(2026, 10, 12), 1, 0), D(2026, 10, 9)),  # Monday early: Friday is the last session
        (_at(D(2026, 10, 20), 18, 30), D(2026, 10, 20)),  # a holiday evening keeps its own date
    ],
)
def test_the_default_asof_is_the_latest_session_with_data(bundle, now, expected) -> None:  # type: ignore[no-untyped-def]
    assert session_asof(None, now=now, bundle=bundle) == expected


def test_an_explicit_date_always_wins(bundle) -> None:  # type: ignore[no-untyped-def]
    assert session_asof("2026-09-01", now=_at(D(2026, 10, 9), 0, 36), bundle=bundle) == D(
        2026, 9, 1
    )
