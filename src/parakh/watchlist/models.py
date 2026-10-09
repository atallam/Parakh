"""Watchlist state: entries, suggestions and events (plan 06 §7).

IDs follow plan 04 §3.1: sources are `SRC.<name>`, automatic removals `RM.<name>`, My Watchlist
flags `FLAG.<name>`. A cycle is a monthly run, counted in whole months between `YYYY-MM` periods.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

Cap = Literal["large", "mid", "small"]
ListKind = Literal["my", "system"]
EntryStatus = Literal["active", "owned", "archived"]
Action = Literal["add_my", "remove_my", "promote"]
SuggestionStatus = Literal["pending", "approved", "rejected", "snoozed", "expired"]
Channel = Literal["streamlit", "telegram", "cli", "mcp", "system"]

SRC_TOP = "SRC.top_combined"
SRC_MOMENTUM = "SRC.momentum_setup"
SRC_VALUE = "SRC.value_zone"
SRC_SMART = "SRC.smart_money"
SOURCES = (SRC_TOP, SRC_MOMENTUM, SRC_VALUE, SRC_SMART)

RM_FADE = "RM.fade"
RM_VETO = "RM.veto"
RM_SETUP_FAILED = "RM.setup_failed"
RM_VALUE_CLOSED = "RM.value_closed"
RM_BUMPED = "RM.bumped"
RM_CAP_MIGRATION = "RM.cap_migration"
RM_CORPORATE = "RM.corporate"
RM_RULES = (
    RM_FADE, RM_VETO, RM_SETUP_FAILED, RM_VALUE_CLOSED, RM_BUMPED, RM_CAP_MIGRATION, RM_CORPORATE
)  # fmt: skip
# Rules that apply at once, with no minimum stay (plan 06 §4.1)
IMMEDIATE_RM = frozenset({RM_VETO, RM_CAP_MIGRATION, RM_CORPORATE})

FLAG_STALE = "FLAG.stale_review"
FLAG_WEAK = "FLAG.persistently_weak"
FLAG_VETO = "FLAG.veto"
FLAG_THESIS = "FLAG.thesis_broken"
FLAG_TARGET = "FLAG.target_hit"
FLAGS = (FLAG_STALE, FLAG_WEAK, FLAG_VETO, FLAG_THESIS, FLAG_TARGET)

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def months_between(earlier: str, later: str) -> int:
    """Whole months from one `YYYY-MM` period to a later one (negative if reversed)."""
    ey, em = int(earlier[:4]), int(earlier[5:7])
    ly, lm = int(later[:4]), int(later[5:7])
    return (ly - ey) * 12 + (lm - em)


def period_of(day: dt.date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


class Entry(BaseModel):
    entry_id: str
    isin: str
    symbol: str
    cap: Cap
    list_kind: ListKind
    status: EntryStatus = "active"
    added_on: dt.date
    added_period: str
    added_by: str  # user | rule | agent:<name> | telegram | streamlit
    sources: list[str] = Field(default_factory=list)
    reason: str = ""
    target_entry_inr: float | None = None
    review_on: dt.date | None = None
    # monthly counters, advanced once per period by `plan_monthly` (idempotent per period)
    last_period: str | None = None
    fade_runs: int = 0  # consecutive runs outside the top fade_rule.outside_top_pct
    top_runs: int = 0  # consecutive runs inside the top promotion.stay_top_pct
    weak_runs: int = 0  # consecutive runs in the bottom weak_flag.bottom_pct
    promote_rejections: int = 0
    promote_rejected_sources: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    thesis_pending: bool = False  # added without a thesis; counted in the Home banner
    removed_on: dt.date | None = None
    removal_rule: str | None = None
    removal_reason: str | None = None
    close_at_add: float | None = None  # for the scorecard (Phase 5)

    @property
    def is_open(self) -> bool:
        return self.status != "archived"


class Suggestion(BaseModel):
    sugg_id: str
    isin: str
    symbol: str
    cap: Cap
    action: Action
    sources: list[str] = Field(default_factory=list)
    origin: str = "rule"  # rule | agent:<name>
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    status: SuggestionStatus = "pending"
    created_on: dt.date
    expires_on: dt.date
    snoozed_until: dt.date | None = None
    decided_on: dt.date | None = None
    decided_by: str | None = None
    decision_note: str | None = None
    channel: Channel | None = None
    flag: str | None = None  # FLAG.* or RM.* that raised it

    @property
    def is_agent(self) -> bool:
        return self.origin.startswith("agent:")


class WatchEvent(BaseModel):
    event_id: str
    entry_id: str | None = None
    isin: str
    type: Literal[
        "added", "removed", "flagged", "promoted", "urgent_add", "missed", "suggested", "expired"
    ]
    rule_id: str | None = None
    run_id: str | None = None
    at: dt.datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class WatchlistState(BaseModel):
    entries: dict[str, Entry] = Field(default_factory=dict)
    suggestions: dict[str, Suggestion] = Field(default_factory=dict)
    events: list[WatchEvent] = Field(default_factory=list)

    def open_entries(self, cap: str | None = None, kind: ListKind | None = None) -> list[Entry]:
        return [
            e
            for e in self.entries.values()
            if e.is_open and (cap is None or e.cap == cap) and (kind is None or e.list_kind == kind)
        ]

    def entry_for(self, isin: str, kind: ListKind | None = None) -> Entry | None:
        for e in self.entries.values():
            if e.isin == isin and e.is_open and (kind is None or e.list_kind == kind):
                return e
        return None

    def pending(self) -> list[Suggestion]:
        return sorted(
            (s for s in self.suggestions.values() if s.status == "pending"),
            key=lambda s: (s.created_on, s.sugg_id),
        )

    def open_suggestion(self, isin: str, action: Action | None = None) -> Suggestion | None:
        for s in self.suggestions.values():
            if (
                s.isin == isin
                and s.status in ("pending", "snoozed")
                and (action is None or s.action == action)
            ):
                return s
        return None
