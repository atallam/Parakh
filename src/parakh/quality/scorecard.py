"""Data-quality scorecard (plan 10 §13): the latest result of every check, per stock.

    card = scorecard(rows, symbols)      # rows from `dq_results`, newest run wins per check

`score_pct` is the share of checks that pass (a warning counts as half), the "DQ 97%" figure in
the governance line. A stock's confidence follows `quality.confidence`: any failure → low.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from parakh.quality import DataConfidence, DqResult, confidence


@dataclass(frozen=True)
class ScoreRow:
    isin: str  # "*" for run-level checks
    symbol: str
    areas: dict[str, str]  # area → worst status among its latest checks
    passed: int
    warned: int
    failed: int
    confidence: DataConfidence


@dataclass(frozen=True)
class Scorecard:
    rows: list[ScoreRow]
    areas: list[str]

    @property
    def checks(self) -> int:
        return sum(r.passed + r.warned + r.failed for r in self.rows)

    @property
    def score_pct(self) -> float | None:
        if not self.checks:
            return None
        good = sum(r.passed + 0.5 * r.warned for r in self.rows)
        return round(100 * good / self.checks, 1)


def latest_results(rows: list[dict[str, Any]]) -> list[DqResult]:
    """One result per (check, ISIN): the newest run's (run ids are ULIDs, so they sort by time)."""
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["check_id"], r["isin"])
        if key not in newest or r["run_id"] > newest[key]["run_id"]:
            newest[key] = r
    return [
        DqResult(r["check_id"], r["isin"], r["status"], r.get("detail") or {})
        for r in newest.values()
    ]


def scorecard(rows: list[dict[str, Any]], symbols: dict[str, str]) -> Scorecard:
    by_isin: dict[str, list[DqResult]] = {}
    for result in latest_results(rows):
        by_isin.setdefault(result.isin, []).append(result)
    order = {"pass": 0, "warn": 1, "fail": 2}
    out, areas = [], set()
    for isin in sorted(by_isin, key=lambda i: (i == "*", symbols.get(i, i))):
        results = by_isin[isin]
        per_area: dict[str, str] = {}
        for r in results:
            area = r.check_id.split(".")[1]
            areas.add(area)
            if order[r.status] >= order.get(per_area.get(area, "pass"), 0):
                per_area[area] = r.status
        out.append(
            ScoreRow(
                isin,
                symbols.get(isin, "(run-level)" if isin == "*" else isin),
                per_area,
                sum(1 for r in results if r.status == "pass"),
                sum(1 for r in results if r.status == "warn"),
                sum(1 for r in results if r.status == "fail"),
                confidence(results),
            )
        )
    return Scorecard(out, sorted(areas))
