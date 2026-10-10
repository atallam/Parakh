"""Decision journal: what you decided, why, and what you expected, reviewed later (AC-F17.4).

    store = JournalStore()
    entry = new_entry(cfg.journal, symbol="TCS", isin=..., action="buy", reason="...",
                      expected="...", today=today)
    store.add(entry)
    store.due(today)          # entries whose review date has arrived and are still open

Three short fields, never amounts or quantities (P6: the journal is read by agents). An entry stays
`open` until you review it, when you record what happened in your own words. A due entry is shown in
the monthly summary and on the Calibration page; nothing is ever closed for you.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from parakh.audit.ids import new_ulid
from parakh.calibration.quintiles import add_months
from parakh.configs.calibration_models import JournalConfig
from parakh.watch.state import StateStore

STATE_NAME = "journal"
Status = Literal["open", "reviewed"]
Verdict = Literal["right", "wrong", "mixed", "too_early"]
AMOUNT_RE = re.compile(r"(₹|rs\.?|inr)\s*\d|\d[\d,]*\s*(shares|qty|units|lakh|crore|cr\b)", re.I)


class JournalError(ValueError):
    """A refusal with a reason a person can act on (UX-10)."""


class JournalEntry(BaseModel):
    entry_id: str = Field(default_factory=new_ulid)
    isin: str
    symbol: str
    decided_on: dt.date
    action: str
    reason: str
    expected: str
    review_on: dt.date
    status: Status = "open"
    reviewed_on: dt.date | None = None
    verdict: Verdict | None = None
    outcome_note: str = ""
    channel: str = "cli"

    @field_validator("reason", "expected", "outcome_note")
    @classmethod
    def _no_amounts(cls, v: str) -> str:
        if AMOUNT_RE.search(v):
            raise ValueError("leave amounts and quantities out; the journal records the thinking")
        return v

    def is_due(self, today: dt.date) -> bool:
        return self.status == "open" and self.review_on <= today


def _clip(label: str, text: str, cfg: JournalConfig, *, required: bool) -> str:
    t = " ".join(text.split())
    if required and not t:
        raise JournalError(f"{label} is empty; one short line is enough")
    if len(t) > cfg.max_field_chars:
        raise JournalError(f"{label} is {len(t)} characters; keep it under {cfg.max_field_chars}")
    return t


def new_entry(
    cfg: JournalConfig,
    *,
    isin: str,
    symbol: str,
    action: str,
    reason: str,
    expected: str,
    today: dt.date,
    review_on: dt.date | None = None,
    channel: str = "cli",
) -> JournalEntry:
    if action not in cfg.actions:
        raise JournalError(f"action must be one of {', '.join(cfg.actions)}")
    when = review_on or add_months(today, cfg.default_review_months)
    if when <= today:
        raise JournalError("the review date must be after today")
    try:
        return JournalEntry(
            isin=isin,
            symbol=symbol,
            decided_on=today,
            action=action,
            reason=_clip("reason", reason, cfg, required=True),
            expected=_clip("expected outcome", expected, cfg, required=True),
            review_on=when,
            channel=channel,
        )
    except ValidationError as exc:
        raise JournalError(exc.errors()[0]["msg"].removeprefix("Value error, ")) from exc


class JournalStore:
    def __init__(self, store: StateStore | None = None) -> None:
        self.store = store or StateStore()

    def all(self) -> list[JournalEntry]:
        raw = self.store.load(STATE_NAME).get("entries", [])
        return [JournalEntry.model_validate(r) for r in raw]

    def save(self, entries: list[JournalEntry]) -> None:
        self.store.save(STATE_NAME, {"entries": [e.model_dump(mode="json") for e in entries]})

    def add(self, entry: JournalEntry) -> JournalEntry:
        self.save([*self.all(), entry])
        return entry

    def get(self, entry_id: str) -> JournalEntry | None:
        return next((e for e in self.all() if e.entry_id == entry_id), None)

    def due(self, today: dt.date) -> list[JournalEntry]:
        return sorted((e for e in self.all() if e.is_due(today)), key=lambda e: e.review_on)

    def replace(self, entry: JournalEntry) -> None:
        self.save([entry if e.entry_id == entry.entry_id else e for e in self.all()])


def stats(entries: list[JournalEntry]) -> dict[str, object]:
    """How the reviewed decisions went, for the quarterly report."""
    reviewed = [e for e in entries if e.status == "reviewed"]
    by_verdict: dict[str, int] = {}
    for e in reviewed:
        by_verdict[e.verdict or "unrated"] = by_verdict.get(e.verdict or "unrated", 0) + 1
    judged = by_verdict.get("right", 0) + by_verdict.get("wrong", 0) + by_verdict.get("mixed", 0)
    return {
        "entries": len(entries),
        "open": len(entries) - len(reviewed),
        "reviewed": len(reviewed),
        "by_verdict": by_verdict,
        "right_pct": 100 * by_verdict.get("right", 0) / judged if judged else None,
    }
