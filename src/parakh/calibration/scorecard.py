# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Watchlist scorecard v1 (F17; plan 06 §6): which idea source works, and does your judgement add value?

    card = build_scorecard(state, book, bench, cfg.scorecard, first_buys, gap_days)

Answers the five questions in plan 06 §6 from the watchlist's own record:
1. forward 3M/6M/12M return against the cap benchmark, by add source;
2. My Watchlist against System Watchlist (hit rate = share that beat the benchmark);
3. the archive: names removed from a list and what they did afterwards (are the rules too eager?);
4. approve, reject and expiry rates by source, rule-made against agent-made;
5. days from entering the list to buying, and how the purchase has done since.

Archived entries stay in every group, so a source that adds names which later fade cannot hide them.
A group with fewer than `min_entries` entries is shown with "not enough yet" instead of a hit rate.
"""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from parakh.calibration.backtest import PriceBook, series_from
from parakh.calibration.quintiles import add_months, forward_months
from parakh.configs.calibration_models import ScorecardConfig
from parakh.watchlist.models import Entry, WatchlistState


@dataclass
class Cell:
    horizon: str
    matured: int = 0
    mean_pct: float | None = None
    mean_excess_pct: float | None = None
    hit_rate_pct: float | None = None  # share that beat the benchmark


@dataclass
class Group:
    name: str
    entries: int
    cells: dict[str, Cell] = field(default_factory=dict)
    note: str = ""


@dataclass
class DecisionRow:
    source: str
    origin: str
    approved: int = 0
    rejected: int = 0
    snoozed: int = 0
    expired: int = 0
    pending: int = 0

    @property
    def approve_rate_pct(self) -> float | None:
        decided = self.approved + self.rejected
        return 100 * self.approved / decided if decided else None


@dataclass
class Scorecard:
    as_of: str
    by_source: list[Group] = field(default_factory=list)
    by_list: list[Group] = field(default_factory=list)
    archive_after_removal: list[Group] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    purchase: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def bench_return(
    bench: tuple[list[dt.date], list[float]] | None, start: dt.date, end: dt.date
) -> float | None:
    if bench is None:
        return None
    ds, vs = bench
    i, j = bisect.bisect_right(ds, start) - 1, bisect.bisect_right(ds, end) - 1
    if i < 0 or j < 0 or vs[i] <= 0:
        return None
    return vs[j] / vs[i] - 1


def _cell(
    book: PriceBook,
    bench: dict[str, tuple[list[dt.date], list[float]] | None],
    items: list[tuple[str, str, dt.date]],  # (isin, cap, start date)
    months: int,
    gap_days: int,
) -> Cell:
    c = Cell(f"{months}M")
    rets, excess = [], []
    for isin, cap, start in items:
        r, status = forward_months(book, isin, start, months, gap_days)
        if r is None:
            continue
        b = bench_return(bench.get(cap), start, add_months(start, months))
        rets.append(r * 100)
        if b is not None:
            excess.append((r - b) * 100)
    c.matured = len(rets)
    if rets:
        c.mean_pct = statistics.fmean(rets)
    if excess:
        c.mean_excess_pct = statistics.fmean(excess)
        c.hit_rate_pct = 100 * sum(1 for e in excess if e > 0) / len(excess)
    return c


def _group(
    name: str,
    items: list[tuple[str, str, dt.date]],
    book: PriceBook,
    bench: dict[str, tuple[list[dt.date], list[float]] | None],
    cfg: ScorecardConfig,
    gap_days: int,
) -> Group:
    g = Group(name, len(items))
    for m in cfg.horizons_months:
        g.cells[f"{m}M"] = _cell(book, bench, items, m, gap_days)
    if len(items) < cfg.min_entries:
        g.note = f"not enough yet ({len(items)} of {cfg.min_entries})"
    return g


def _sources(e: Entry) -> list[str]:
    return list(e.sources) or ["manual"]


def build_scorecard(
    state: WatchlistState,
    book: PriceBook,
    bench_by_cap: Mapping[str, pd.Series | None],
    cfg: ScorecardConfig,
    first_buys: dict[str, dt.date] | None = None,
    gap_days: int = 15,
) -> Scorecard:
    bench = {k: series_from(v) for k, v in bench_by_cap.items()}
    card = Scorecard(as_of=book.days[-1].isoformat() if book.days else "")
    entries = list(state.entries.values())
    by_src: dict[str, list[tuple[str, str, dt.date]]] = {}
    by_list: dict[str, list[tuple[str, str, dt.date]]] = {}
    after_removal: dict[str, list[tuple[str, str, dt.date]]] = {
        "removed by a rule": [],
        "removed by you": [],
    }
    for e in entries:
        item = (e.isin, e.cap, e.added_on)
        for s in _sources(e):
            by_src.setdefault(s, []).append(item)
        by_list.setdefault(f"{e.list_kind} watchlist", []).append(item)
        if e.removed_on:
            key = (
                "removed by a rule"
                if (e.removal_rule or "").startswith("RM.")
                else "removed by you"
            )
            after_removal[key].append((e.isin, e.cap, e.removed_on))
    card.by_source = [_group(n, v, book, bench, cfg, gap_days) for n, v in sorted(by_src.items())]
    card.by_list = [_group(n, v, book, bench, cfg, gap_days) for n, v in sorted(by_list.items())]
    card.archive_after_removal = [
        _group(n, v, book, bench, cfg, gap_days) for n, v in after_removal.items() if v
    ]
    rows: dict[tuple[str, str], DecisionRow] = {}
    for s in state.suggestions.values():
        origin = "agent" if s.is_agent else "rule"
        for src in s.sources or ["manual"]:
            row = rows.setdefault((src, origin), DecisionRow(src, origin))
            setattr(row, s.status, getattr(row, s.status) + 1)
    card.decisions = [
        {**asdict(r), "approve_rate_pct": r.approve_rate_pct} for _, r in sorted(rows.items())
    ]
    if first_buys:
        days, results = [], []
        end = book.days[-1] if book.days else None
        for e in entries:
            bought = first_buys.get(e.isin)
            if bought is None or bought < e.added_on or end is None:
                continue
            days.append((bought - e.added_on).days)
            a, b = book.price(e.isin, bought), book.price(e.isin, end)
            if a and b:
                results.append((b / a - 1) * 100)
        card.purchase = {
            "bought": len(days),
            "median_days_to_buy": statistics.median(days) if days else None,
            "mean_return_since_buy_pct": statistics.fmean(results) if results else None,
        }
    return card
