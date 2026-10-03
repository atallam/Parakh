"""The NSE trading calendar (plan 03 §3, §7; AC-F11.1, AC-F12.5).

    cal = Calendar.from_config(bundle.holidays)
    cal.is_trading_day(date(2026, 10, 2))        # False: Gandhi Jayanti
    cal.last_trading_day_of_month(2026, 10)      # the monthly as-of date (AC-F11.1)
    cal.monthly_asof(date(2026, 11, 2))          # 2026-10-30

A year that the config does not list (NSE publishes the next year's holidays in December) is
treated as weekends-only and reported by `gaps()`, so the heartbeat can warn before it matters.
Special sessions (Muhurat) are holidays for the regular session and, by default, not trading
days (config `special_sessions_trade`).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from parakh.configs.notify_models import HolidaysConfig


@dataclass(frozen=True)
class Calendar:
    holidays: frozenset[dt.date]
    special_sessions: frozenset[dt.date]
    years: frozenset[int]
    special_sessions_trade: bool = False
    names: dict[dt.date, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: HolidaysConfig) -> Calendar:
        holidays: set[dt.date] = set()
        special: set[dt.date] = set()
        names: dict[dt.date, str] = {}
        for cal in cfg.years.values():
            for h in cal.holidays:
                holidays.add(h.date)
                names[h.date] = h.name
            for s in cal.special_sessions:
                special.add(s.date)
                names.setdefault(s.date, s.name)
        return cls(
            frozenset(holidays),
            frozenset(special),
            frozenset(cfg.years),
            cfg.special_sessions_trade,
            names,
        )

    # -- single days -------------------------------------------------------------------------
    def is_weekend(self, day: dt.date) -> bool:
        return day.weekday() >= 5

    def is_trading_day(self, day: dt.date) -> bool:
        if day in self.special_sessions:
            return self.special_sessions_trade
        return not self.is_weekend(day) and day not in self.holidays

    def is_special_session(self, day: dt.date) -> bool:
        return day in self.special_sessions

    def holiday_name(self, day: dt.date) -> str | None:
        if self.is_trading_day(day):
            return None
        if day in self.names:
            return self.names[day]
        return "weekend" if self.is_weekend(day) else None

    def known(self, day: dt.date) -> bool:
        """False when the config has no holiday list for the day's year (weekends-only guess)."""
        return day.year in self.years

    # -- walking -----------------------------------------------------------------------------
    def previous_trading_day(self, day: dt.date, *, inclusive: bool = False) -> dt.date:
        cur = day if inclusive else day - dt.timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= dt.timedelta(days=1)
        return cur

    def next_trading_day(self, day: dt.date, *, inclusive: bool = False) -> dt.date:
        cur = day if inclusive else day + dt.timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += dt.timedelta(days=1)
        return cur

    def add_trading_days(self, day: dt.date, n: int) -> dt.date:
        step = 1 if n >= 0 else -1
        cur = day
        for _ in range(abs(n)):
            cur = self.next_trading_day(cur) if step > 0 else self.previous_trading_day(cur)
        return cur

    def trading_days_between(self, start: dt.date, end: dt.date) -> int:
        """Trading days after `start` up to and including `end` (0 when end <= start)."""
        if end <= start:
            return 0
        count, cur = 0, start
        while cur < end:
            cur += dt.timedelta(days=1)
            if self.is_trading_day(cur):
                count += 1
        return count

    def trading_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        out: list[dt.date] = []
        cur = start
        while cur <= end:
            if self.is_trading_day(cur):
                out.append(cur)
            cur += dt.timedelta(days=1)
        return out

    def last_n_trading_days(self, end: dt.date, n: int) -> list[dt.date]:
        out: list[dt.date] = []
        cur = self.previous_trading_day(end, inclusive=True)
        while len(out) < n:
            out.append(cur)
            cur = self.previous_trading_day(cur)
        return sorted(out)

    # -- months ------------------------------------------------------------------------------
    def last_trading_day_of_month(self, year: int, month: int) -> dt.date:
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        return self.previous_trading_day(nxt)

    def monthly_asof(self, run_day: dt.date) -> dt.date:
        """The as-of date of the monthly run started on `run_day` (AC-F11.1).

        The last trading day of the previous month, whether or not the 1st was a holiday. A
        run started on the last trading day of a month itself still analyses the month before:
        the data for the running month is not complete until the next day.
        """
        first = run_day.replace(day=1)
        prev = first - dt.timedelta(days=1)
        return self.last_trading_day_of_month(prev.year, prev.month)

    # -- health ------------------------------------------------------------------------------
    def gaps(self, today: dt.date, horizon_days: int = 45) -> list[int]:
        """Years inside the horizon that the config does not cover."""
        end = today + dt.timedelta(days=horizon_days)
        return sorted({y for y in {today.year, end.year} if y not in self.years})

    def drop_special_sessions(self, frame: Any, date_col: str = "trade_date") -> Any:
        """Remove symbolic-session bars (Muhurat) from a price frame."""
        if self.special_sessions_trade or frame is None or len(frame) == 0:
            return frame
        import pandas as pd

        dates = pd.to_datetime(frame[date_col]).dt.date
        return frame[~dates.isin(self.special_sessions)].reset_index(drop=True)


def default_calendar() -> Calendar:
    from parakh.configs import load_all

    return Calendar.from_config(load_all().holidays)
