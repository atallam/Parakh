"""Point-in-time index membership (AC-F17.1; plan 05 §3.4).

    m = Membership.from_rows(rows)             # rows: index_id, isin, valid_from, valid_to
    m.members_on("NIFTY 100", date(2021, 3, 31))
    m.coverage_start("NIFTY 100")              # the first day membership is actually known

A security is a member on a day when `valid_from <= day < valid_to` (valid_to is the first day it is
no longer a member; open memberships have no end). The backtest asks only this question, so a stock
that joined an index after a rebalance date can never be bought on it, and one that left stays
tradable until the day it left.

The reference loader (`parakh reference load`) stamps a first-time membership with the day it was
loaded, which says nothing about when the stock really joined. `coverage_start` is therefore the
earliest day the table can vouch for; a backtest window that starts earlier is not point-in-time
unless historical constituents were imported (`parakh calibration membership-import`).
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED = ("index_id", "isin", "valid_from")


@dataclass(frozen=True)
class Span:
    index_id: str
    isin: str
    valid_from: dt.date
    valid_to: dt.date | None = None

    def covers(self, day: dt.date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day < self.valid_to)


def _date(value: Any) -> dt.date | None:
    if value in (None, "", "None"):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


class Membership:
    def __init__(self, spans: list[Span]) -> None:
        self.spans = list(spans)
        self._by_index: dict[str, list[Span]] = {}
        for s in self.spans:
            self._by_index.setdefault(s.index_id, []).append(s)

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> Membership:
        spans = []
        for r in rows:
            missing = [k for k in REQUIRED if not r.get(k)]
            if missing:
                raise ValueError(f"membership row {r} lacks {missing}")
            start, end = _date(r["valid_from"]), _date(r.get("valid_to"))
            assert start is not None
            if end is not None and end < start:
                raise ValueError(
                    f"membership of {r['isin']} in {r['index_id']} ends before it starts"
                )
            spans.append(Span(str(r["index_id"]), str(r["isin"]), start, end))
        return cls(spans)

    @classmethod
    def from_csv(cls, path: Path) -> Membership:
        with path.open(encoding="utf-8", newline="") as fh:
            return cls.from_rows(list(csv.DictReader(fh)))

    def merged(self, other: Membership) -> Membership:
        """Both sets of spans; an exact duplicate is kept once."""
        seen = {(s.index_id, s.isin, s.valid_from, s.valid_to) for s in self.spans}
        extra = [
            s for s in other.spans if (s.index_id, s.isin, s.valid_from, s.valid_to) not in seen
        ]
        return Membership(self.spans + extra)

    def indices(self) -> list[str]:
        return sorted(self._by_index)

    def members_on(self, index_id: str, day: dt.date) -> set[str]:
        return {s.isin for s in self._by_index.get(index_id, []) if s.covers(day)}

    def index_of(self, isin: str, day: dt.date, preference: list[str]) -> str | None:
        """The first index in `preference` that holds `isin` on `day` (large before mid before small)."""
        for index_id in preference:
            if any(s.isin == isin and s.covers(day) for s in self._by_index.get(index_id, [])):
                return index_id
        return None

    def coverage_start(self, index_id: str) -> dt.date | None:
        spans = self._by_index.get(index_id, [])
        return min((s.valid_from for s in spans), default=None)

    def covers_window(self, index_ids: list[str], start: dt.date) -> bool:
        """True when every index has membership known from `start` or earlier."""
        for i in index_ids:
            first = self.coverage_start(i)
            if first is None or first > start:
                return False
        return True


def import_csv(path: Path, target: Path) -> int:
    """Validate a historical-constituents CSV and merge it into `target` (the local history file).

    Columns: index_id, isin, valid_from, valid_to (blank while still a member). Returns rows now in
    the file. Existing rows are kept; exact duplicates are dropped.
    """
    new = Membership.from_csv(path)
    existing = Membership.from_csv(target) if target.exists() else Membership([])
    merged = existing.merged(new)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["index_id", "isin", "valid_from", "valid_to"])
        for s in sorted(merged.spans, key=lambda s: (s.index_id, s.isin, s.valid_from)):
            w.writerow([s.index_id, s.isin, s.valid_from.isoformat(), s.valid_to or ""])
    return len(merged.spans)
