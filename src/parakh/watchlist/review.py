"""The monthly watchlist review over the month's snapshots (plan 06 §3.3).

snaps = load_snapshots("2026-10")                      # every cap folder, that month
result = monthly_review(svc, snaps, period="2026-10", today=day, event_rows=log.rows())
result.line                                            # the one line for the monthly Telegram message
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from parakh.services.watchlist import WatchlistService
from parakh.snapshots.store import PERIOD, all_stock_dirs, read_snapshot_dict
from parakh.watchlist.engine import Act
from parakh.watchlist.facts import Facts, facts_for_cap

CAPS = ("large", "mid", "small")


def load_snapshots(period: str | None = None, root: Path | None = None) -> list[dict[str, Any]]:
    """Each stock's snapshot for `period`, or its newest one when `period` is None."""
    out: list[dict[str, Any]] = []
    for cap in CAPS:
        for folder in all_stock_dirs(cap, root):
            snap_dir = folder / "snapshots"
            if not snap_dir.exists():
                continue
            names = sorted(p.stem for p in snap_dir.glob("*.json") if PERIOD.match(p.stem))
            pick = period if period in names else (names[-1] if period is None and names else None)
            if pick is None:
                continue
            snap = read_snapshot_dict(snap_dir / f"{pick}.json")
            if snap:
                out.append(snap)
    return out


def facts_by_cap(
    snaps: list[dict[str, Any]],
    bundle_watchlist: Any,
    *,
    event_rows: list[dict[str, Any]] | None,
    today: dt.date,
) -> list[Facts]:
    facts: list[Facts] = []
    for cap in CAPS:
        in_cap = [s for s in snaps if s["cap"] == cap]
        if in_cap:
            facts += facts_for_cap(in_cap, bundle_watchlist, event_rows=event_rows, today=today)
    return facts


@dataclass
class ReviewResult:
    acts: list[Act] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)
    pending: int = 0
    line: str = ""


def summary_line(counts: Counter[str], pending: int) -> str:
    """'🗂 Watchlist review: 3 to review, 2 flagged, 4 auto-added, 3 auto-removed' (plan 06 §5.2)."""
    parts = [
        f"{pending} to review",
        f"{counts['flagged']} flagged",
        f"{counts['added'] + counts['urgent_add']} auto-added",
        f"{counts['removed'] + counts['bumped']} auto-removed",
    ]
    return "🗂 Watchlist review: " + ", ".join(parts)


def monthly_review(
    svc: WatchlistService,
    snaps: list[dict[str, Any]],
    *,
    period: str,
    today: dt.date,
    event_rows: list[dict[str, Any]] | None = None,
) -> ReviewResult:
    facts = facts_by_cap(snaps, svc.bundle.watchlist, event_rows=event_rows, today=today)
    acts = svc.run_monthly(facts, period=period, today=today)
    counts = Counter(a.kind for a in acts)
    pending = len(svc.pending())
    return ReviewResult(acts, counts, pending, summary_line(counts, pending))
