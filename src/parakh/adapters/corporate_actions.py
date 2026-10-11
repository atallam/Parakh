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
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

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
    amount_inr: float | None = None  # dividends: ₹ per share (the ratio is unused)

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


# -- NSE corporate-actions feed (www.nseindia.com/api/corporates-corporateActions) ------------
# Subjects seen on the pilots (spike ④, 29 Sep 2026):
#   "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share"
#   "Bonus 1:1"
#   "Interim Dividend - Rs 7.50 Per Share", "Annual General Meeting/Dividend - Rs  1.63 Per Share"
# Pitfall: the feed keeps the pre-split ISIN on every row (MAZDOCK INE249Z01012), so ISINs are
# resolved through isin_history before anything is stored.
_SPLIT = re.compile(
    r"Split.*?From\s+(?:Rs\.?|Re\.?)\s*(\d[\d.]*).*?To\s+(?:Rs\.?|Re\.?)\s*(\d[\d.]*)", re.I
)
_BONUS = re.compile(r"Bonus\s+(\d+)\s*:\s*(\d+)", re.I)
_DIVIDEND = re.compile(r"Dividend\s*-\s*(?:Rs\.?|Re\.?)\s*(\d[\d.]*)", re.I)


def _number(text: str) -> float | None:
    """Parse an amount from a feed subject. The feed has typos such as "62..50" (a doubled dot):
    collapse repeated dots, and return None for anything still unreadable instead of crashing."""
    try:
        return float(re.sub(r"\.{2,}", ".", text).rstrip("."))
    except ValueError:
        return None


def _nse_date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip(), "%d-%b-%Y").date()


def parse_nse_subject(subject: str) -> list[tuple[ActionType, float, float | None]]:
    """(type, ratio, amount) for each action a subject line announces. Unknown subjects → []."""
    out: list[tuple[ActionType, float, float | None]] = []
    if m := _SPLIT.search(subject):
        old_fv, new_fv = _number(m.group(1)), _number(m.group(2))
        if old_fv is not None and new_fv is not None and new_fv > 0 and old_fv > new_fv:
            out.append(("split", old_fv / new_fv, None))
    if m := _BONUS.search(subject):
        new, held = int(m.group(1)), int(m.group(2))
        if held > 0:
            out.append(("bonus", new / held, None))
    amounts = [a for x in _DIVIDEND.findall(subject) if (a := _number(x)) is not None]
    if amounts:
        out.append(("dividend", 0.0, sum(amounts)))
    return out


def parse_nse_corporate_actions(
    rows: Iterable[Mapping[str, Any]], resolve_isin: Callable[[str], str] = lambda i: i
) -> list[CorporateAction]:
    """NSE feed rows → actions keyed on the current ISIN. Rows without an ex-date are skipped."""
    actions: dict[tuple[str, dt.date, str], CorporateAction] = {}
    for row in rows:
        ex = str(row.get("exDate") or "").strip()
        if not ex or ex == "-":
            continue
        isin = resolve_isin(str(row["isin"]).strip())
        for kind, ratio, amount in parse_nse_subject(str(row.get("subject") or "")):
            key = (isin, _nse_date(ex), kind)
            prev = actions.get(key)
            if prev and kind == "dividend" and prev.amount_inr is not None and amount is not None:
                amount += prev.amount_inr  # two dividend rows on one ex-date (final + special)
            actions[key] = CorporateAction(isin, key[1], kind, ratio, "nse_archives", amount)
    return sorted(actions.values(), key=lambda a: (a.isin, a.ex_date, a.type))
