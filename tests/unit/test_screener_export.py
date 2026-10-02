"""Screener export parser against the real M&M export (spike ③). T-ADP-10…"""

from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import openpyxl
import pytest

from parakh.adapters.screener_export import ExportFormatError, parse_export

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "sources"
    / "screener"
    / "MM_export_2026-09-27.xlsx"
)
DATA = FIXTURE.read_bytes()


def test_company_is_identified_by_the_name_cell_not_the_file_name() -> None:
    """T-ADP-10 (plan 13 §8 item 3: the file was called 'M & M.xlsx')."""
    export = parse_export(DATA)
    assert export.company_name == "MAHINDRA & MAHINDRA LTD"
    assert export.version == 2.1


def test_ten_years_and_ten_quarters_in_crore() -> None:
    """T-ADP-11"""
    export = parse_export(DATA)
    annual = export.periods("annual_pl")
    assert (
        annual[0] == dt.date(2017, 3, 31)
        and annual[-1] == dt.date(2026, 3, 31)
        and len(annual) == 10
    )
    quarters = export.periods("quarterly_pl")
    assert len(quarters) == 10 and quarters[-1] == dt.date(2026, 6, 30)
    assert export.series("quarterly_pl", "Sales")[dt.date(2026, 6, 30)] == pytest.approx(58187.57)
    assert export.series("annual_pl", "Net profit")[dt.date(2026, 3, 31)] == pytest.approx(17098.85)
    units = {f.item: f.unit for f in export.facts}
    assert (
        units["Sales"] == "cr"
        and units["No. of Equity Shares"] == "count"
        and units["PRICE:"] == "inr"
    )


def test_balance_sheet_balances_and_known_pitfalls_are_flagged() -> None:
    """T-ADP-12"""
    export = parse_export(DATA)
    assert not any("does not balance" in i for i in export.issues)
    assert any("Number of shares" in i for i in export.issues)
    assert any("adjusted shares" in i for i in export.issues)


def test_market_cap_uses_adjusted_shares() -> None:
    """T-ADP-13: 3,035 × 124.35 Cr ≈ Screener's 3,77,411 Cr; the balance-sheet count would be 10% low."""
    export = parse_export(DATA)
    adjusted_cr = export.series("derived", "Adjusted Equity Shares in Cr")[dt.date(2026, 3, 31)]
    assert adjusted_cr is not None
    implied = export.meta["Current Price"] * adjusted_cr  # type: ignore[operator]
    assert implied == pytest.approx(export.meta["Market Capitalization"], rel=0.001)


def test_unsupported_version_is_refused() -> None:
    """T-ADP-14"""
    wb = openpyxl.load_workbook(io.BytesIO(DATA))
    wb["Data Sheet"]["B3"] = 3.0
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ExportFormatError, match="version"):
        parse_export(buf.getvalue())


def _young_company(data: bytes, blank: int = 3) -> bytes:
    """The M&M export with the first `blank` data columns emptied, like a company listed
    seven years ago (Ather, Shadowfax)."""
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb["Data Sheet"]
    in_meta = False
    for r, row in enumerate(ws.iter_rows(min_row=5), start=5):
        label = str(row[0].value or "").strip()
        if label == "META":
            in_meta = True
        elif label in {"PROFIT & LOSS", "Quarters", "BALANCE SHEET", "CASH FLOW:", "DERIVED:"}:
            in_meta = False
        if not in_meta:
            for col in range(2, 2 + blank):
                ws.cell(row=r, column=col, value=None)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_price_and_derived_rows_stay_aligned_when_early_years_are_blank() -> None:
    """T-ADP-15: regression from the Phase 1 pilot exports (Ather, Shadowfax), where PRICE and
    DERIVED values shifted three years left because leading blank columns were dropped."""
    full = parse_export(DATA)
    young = parse_export(_young_company(DATA))
    fy26 = dt.date(2026, 3, 31)
    for section, item in (("derived", "Adjusted Equity Shares in Cr"), ("annual_price", "PRICE:")):
        assert young.series(section, item)[fy26] == full.series(section, item)[fy26]


def test_pre_listing_share_counts_are_flagged() -> None:
    """T-ADP-16: Screener leaves pre-IPO years at the pre-bonus count."""
    wb = openpyxl.load_workbook(io.BytesIO(DATA))
    ws = wb["Data Sheet"]
    for r, row in enumerate(ws.iter_rows(min_row=5), start=5):
        if row[0].value == "Adjusted Equity Shares in Cr":
            for col in range(2, 5):
                ws.cell(row=r, column=col, value=0.01)
    buf = io.BytesIO()
    wb.save(buf)
    issues = parse_export(buf.getvalue()).issues
    assert any("pre-listing" in i and "2019-03-31" in i for i in issues)


def test_every_fact_has_a_unique_key() -> None:
    """T-ADP-17: the balance sheet's two "Total" rows collided in the fundamentals table
    (found on the first real load, 1 Oct 2026)."""
    from collections import Counter

    export = parse_export(DATA)
    keys = Counter((f.section, f.item, f.period_end) for f in export.facts)
    assert max(keys.values()) == 1
    fy26 = dt.date(2026, 3, 31)
    assets = export.series("balance_sheet", "Total Assets")[fy26]
    liabilities = export.series("balance_sheet", "Total Liabilities")[fy26]
    assert assets is not None and assets == pytest.approx(liabilities)
