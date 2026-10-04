"""Schemas for config/holidays.yaml, notify.yaml and events.yaml (plan 03, plan 12 §6, ADR-008)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from parakh.configs.models import Strict

Severity = Literal["High", "Medium", "Low"]
Direction = Literal["entry", "exit", "warning", "info"]
Valence = Literal["positive", "negative", "neutral"]


# -- holidays.yaml -----------------------------------------------------------------------------
class Holiday(Strict):
    date: dt.date
    name: str = Field(min_length=3)


class YearCalendar(Strict):
    holidays: list[Holiday]
    special_sessions: list[Holiday] = []


class HolidaysConfig(Strict):
    source: str
    special_sessions_trade: bool
    years: dict[int, YearCalendar]

    @model_validator(mode="after")
    def _check(self) -> HolidaysConfig:
        for year, cal in self.years.items():
            seen: set[dt.date] = set()
            for h in [*cal.holidays, *cal.special_sessions]:
                if h.date.year != year:
                    raise ValueError(f"{h.date} is listed under {year}")
            for h in cal.holidays:
                if h.date in seen:
                    raise ValueError(f"duplicate holiday {h.date}")
                seen.add(h.date)
        return self


# -- notify.yaml -------------------------------------------------------------------------------
class EmailChannel(Strict):
    enabled: bool
    smtp_host: str
    smtp_port: int = Field(ge=1, le=65535)


class NtfyChannel(Strict):
    enabled: bool
    server: str


class Channels(Strict):
    telegram_enabled: bool
    email: EmailChannel
    ntfy: NtfyChannel


class Routing(Strict):
    cooldown_trading_days: int = Field(ge=0)
    top_decile_rs_percentile: float = Field(ge=0, le=100)
    digest_max_items: int = Field(ge=1)
    agent_daily_cap: int = Field(ge=0)
    confirm_closes: dict[str, int] = {}
    signal_direction: dict[str, Direction]
    signal_catalogue_start: str = "M01"


class Bot(Strict):
    button_token_ttl_days: int = Field(ge=1)
    mute_days: int = Field(ge=1)
    max_updates_per_poll: int = Field(ge=1, le=100)
    owner_commands: list[str]


class Retry(Strict):
    wait_minutes: int = Field(ge=0)
    max_attempts: int = Field(ge=1)


class ServiceLevels(Strict):
    monthly_summary_by_ist: str = Field(pattern=r"^\d{2}:\d{2}$")
    watcher_by_ist: str = Field(pattern=r"^\d{2}:\d{2}$")
    failure_alert_minutes: int = Field(ge=1)


class Links(Strict):
    report_base: str  # prefix for the "Open ▸" link; a hosted Streamlit URL later (plan 12 §6)


class NotifyConfig(Strict):
    include_amounts: bool
    channels: Channels
    routing: Routing
    bot: Bot
    retry: Retry
    service_levels: ServiceLevels
    links: Links

    @model_validator(mode="after")
    def _signals(self) -> NotifyConfig:
        bad = [k for k in self.routing.signal_direction if not re.fullmatch(r"M\d{2}", k)]
        if bad:
            raise ValueError(f"signal ids must look like M03: {bad}")
        return self


# -- events.yaml -------------------------------------------------------------------------------
class EventRule(Strict):
    id: str = Field(pattern=r"^E\d{2}$")
    name: str
    source: Literal["announcement", "insider", "surveillance", "deals", "lockin"]
    severity: Severity
    max_severity: Severity
    valence: Valence
    refresh: bool = False
    signal_id: str | None = None  # the M-code this event stands in for (M28 surveillance, M30)
    desc_any: list[str] = []  # NSE announcement `desc` equals one of these (case-insensitive)
    text_any: list[str] = []  # regexes over the announcement text; any must match
    text_all: list[str] = []  # …all must match
    text_none: list[str] = []  # …none may match
    escalate_if: list[str] = []  # regexes that lift severity to max_severity
    relax_if: list[str] = []  # regexes that drop severity to Medium and flip valence to positive
    group_regex: str | None = None  # one alert per captured group (results: the period ended)
    person_categories: list[str] = []  # insider: personCategory contains one of these
    acq_modes: list[str] = []  # insider: acqMode contains one of these (case-insensitive)

    @field_validator("desc_any")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [x.lower() for x in v]

    @field_validator("text_any", "text_all", "text_none", "escalate_if", "relax_if")
    @classmethod
    def _regex(cls, v: list[str]) -> list[str]:
        for pattern in v:
            re.compile(pattern)
        return v

    @field_validator("group_regex")
    @classmethod
    def _group(cls, v: str | None) -> str | None:
        if v is not None and re.compile(v).groups < 1:
            raise ValueError("group_regex needs one capture group")
        return v

    @model_validator(mode="after")
    def _cap(self) -> EventRule:
        order = {"Low": 0, "Medium": 1, "High": 2}
        if order[self.severity] > order[self.max_severity]:
            raise ValueError(f"{self.id}: severity is above max_severity")
        return self


class LockinSchedule(Strict):
    days_after_listing: int = Field(ge=1)
    label: str


class EventsConfig(Strict):
    lookback_days: int = Field(ge=1, le=30)
    lockin_warn_trading_days: int = Field(ge=1)
    lockin_schedule: list[LockinSchedule]
    lockin_max_age_days: int = Field(ge=30)
    rules: list[EventRule]

    @model_validator(mode="after")
    def _unique(self) -> EventsConfig:
        ids = [r.id for r in self.rules]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate event rule ids: {sorted(dupes)}")
        return self

    def rule(self, event_id: str) -> EventRule:
        return next(r for r in self.rules if r.id == event_id)
