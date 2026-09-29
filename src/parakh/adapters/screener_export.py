"""Screener.in Excel export ("Data Sheet", v2.1) → long-format fundamentals (plan 13 D4).

The export is the primary fundamentals source (T2). Findings from spike ③ that shape this:
- Files are named by you (e.g. `M & M.xlsx`), so the company is identified by the
  COMPANY NAME cell, never the file name.
- Values are ₹ crore (`_cr`), except share counts (units), face value and prices (₹).
- Only period ends are given; there is no "reported on" date, so point-in-time scoring needs
  the result-announcement dates from the exchange feed (plan 04 §4 #3).
- "Number of shares" in META can be blank; "Adjusted Equity Shares in Cr" (DERIVED) can
  differ from "No. of Equity Shares" (M&M: 124.35 Cr vs 111.76 Cr after its trust shares
  were excluded). Per-share metrics must say which one they use.
"""

from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field

import openpyxl

SUPPORTED_VERSIONS = {2.1}
# why: a real share history never shrinks 100×; below 1% of today's count means pre-listing
# counts Screener did not adjust for the pre-IPO bonus issue.
PRE_LISTING_SHARE_RATIO = 0.01
SHEET = "Data Sheet"
# Section header text in column A → section key
SECTIONS = {
    "PROFIT & LOSS": "annual_pl",
    "Quarters": "quarterly_pl",
    "BALANCE SHEET": "balance_sheet",
    "CASH FLOW:": "cash_flow",
}
# Rows that are not ₹ crore amounts
UNIT_OVERRIDES = {
    "No. of Equity Shares": "count",
    "New Bonus Shares": "count",
    "Face value": "inr",
    "Face Value": "inr",
    "Current Price": "inr",
    "PRICE:": "inr",
    "Adjusted Equity Shares in Cr": "count_cr",
}


@dataclass(frozen=True)
class Fact:
    section: str
    item: str
    period_end: dt.date
    value: float | None
    unit: str  # cr | count | count_cr | inr


@dataclass
class ScreenerExport:
    company_name: str
    version: float
    meta: dict[str, float | None]
    facts: list[Fact]
    issues: list[str] = field(default_factory=list)

    def series(self, section: str, item: str) -> dict[dt.date, float | None]:
        return {
            f.period_end: f.value for f in self.facts if f.section == section and f.item == item
        }

    def periods(self, section: str) -> list[dt.date]:
        return sorted({f.period_end for f in self.facts if f.section == section})


class ExportFormatError(ValueError):
    pass


def _as_date(value: object) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def parse_export(data: bytes) -> ScreenerExport:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    if SHEET not in wb.sheetnames:
        raise ExportFormatError(f"no '{SHEET}' sheet (got {wb.sheetnames})")
    rows = [tuple(c for c in r) for r in wb[SHEET].iter_rows(values_only=True)]
    wb.close()

    header = {str(r[0]).strip(): r[1] for r in rows[:4] if r and r[0]}
    name = header.get("COMPANY NAME")
    version = _as_float(header.get("CURRENT VERSION"))
    if not isinstance(name, str) or not name.strip():
        raise ExportFormatError("COMPANY NAME cell is empty")
    if version not in SUPPORTED_VERSIONS:
        raise ExportFormatError(f"Data Sheet version {version} not supported {SUPPORTED_VERSIONS}")

    meta: dict[str, float | None] = {}
    facts: list[Fact] = []
    issues: list[str] = []
    section: str | None = None
    dates: list[dt.date | None] = []
    # The annual P&L header, kept positionally: companies with fewer than ten years of history
    # have blank leading columns, and PRICE/DERIVED rows line up with this header, not with a
    # compacted list of years (Ather, Shadowfax: found on the Phase 1 pilot exports).
    annual_header: list[dt.date | None] = []
    in_meta = False
    for row in rows[4:]:
        if not row or row[0] is None:
            continue
        label = str(row[0]).strip()
        if label == "META":
            in_meta = True
            continue
        if label in SECTIONS:
            section, dates, in_meta = SECTIONS[label], [], False
            continue
        if label == "DERIVED:":
            section, in_meta = "derived", False
            continue
        if in_meta:
            meta[label] = _as_float(row[1] if len(row) > 1 else None)
            continue
        if label == "Report Date":
            dates = [_as_date(v) for v in row[1:]]
            if section == "annual_pl" and not annual_header:
                annual_header = dates
            continue
        if label == "PRICE:":
            section_for_row, dates_for_row = "annual_price", annual_header
        else:
            section_for_row, dates_for_row = section, dates
        if section_for_row is None or not dates_for_row:
            continue
        if section_for_row == "derived":
            dates_for_row = annual_header
        unit = UNIT_OVERRIDES.get(label, "cr")
        for period_end, raw in zip(dates_for_row, row[1:], strict=False):
            if period_end is not None:
                facts.append(Fact(section_for_row, label, period_end, _as_float(raw), unit))

    export = ScreenerExport(name.strip(), version, meta, facts, issues)
    _check(export)
    return export


def _check(export: ScreenerExport) -> None:
    """Data-quality checks that should hold in every export (recorded, never silently fixed)."""
    issues = export.issues
    for key in ("annual_pl", "quarterly_pl", "balance_sheet", "cash_flow"):
        if not export.periods(key):
            issues.append(f"section {key} missing")
    if export.meta.get("Number of shares") is None:
        issues.append("META 'Number of shares' is blank; use balance-sheet share counts")
    totals = [f for f in export.facts if f.section == "balance_sheet" and f.item == "Total"]
    by_period: dict[dt.date, list[float]] = {}
    for f in totals:
        if f.value is not None:
            by_period.setdefault(f.period_end, []).append(f.value)
    for period, values in by_period.items():
        if len(values) == 2 and abs(values[0] - values[1]) > 1.0:
            issues.append(f"balance sheet does not balance at {period}: {values}")
    shares = export.series("balance_sheet", "No. of Equity Shares")
    adjusted = export.series("derived", "Adjusted Equity Shares in Cr")
    if shares and adjusted:
        last = max(shares)
        count, adj = shares[last], adjusted.get(last)
        if count and adj:
            gap = abs(count / 1e7 - adj) / adj
            if gap > 0.02:
                issues.append(
                    f"share count differs from adjusted shares by {gap:.0%} at {last} "
                    f"({count / 1e7:.2f} Cr vs {adj} Cr)"
                )
    # Recent IPOs: Screener leaves pre-listing years at the pre-bonus count (Ather 0.01 Cr vs
    # 38.27 Cr), so per-share history for those years is meaningless.
    if adjusted:
        latest = adjusted[max(adjusted)]
        tiny = sorted(
            p
            for p, v in adjusted.items()
            if v is not None and latest and v < PRE_LISTING_SHARE_RATIO * latest
        )
        if tiny:
            issues.append(
                f"adjusted shares up to {tiny[-1]} are under {PRE_LISTING_SHARE_RATIO:.0%} of the "
                "latest (pre-listing, not bonus-adjusted); per-share history before then is unusable"
            )
