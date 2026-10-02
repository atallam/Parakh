"""Synthetic fundamentals rows in the long format of the `fundamentals` table (no network)."""

from __future__ import annotations

import datetime as dt
from typing import Any

YEARS = [dt.date(2017 + i, 3, 31) for i in range(10)]  # FY17..FY26
QUARTERS = [dt.date(2023, 9, 30), dt.date(2023, 12, 31), dt.date(2024, 3, 31), dt.date(2024, 6, 30),
            dt.date(2024, 9, 30), dt.date(2024, 12, 31), dt.date(2025, 3, 31), dt.date(2025, 6, 30),
            dt.date(2025, 9, 30), dt.date(2025, 12, 31), dt.date(2026, 3, 31), dt.date(2026, 6, 30)]  # fmt: skip


def rows(
    isin: str = "INE000000000",
    years: list[dt.date] | None = None,
    sales0: float = 1000.0,
    growth: float = 0.12,
    margin: float = 0.18,
    pat_margin: float = 0.10,
    shares_cr: float = 10.0,
    borrowings0: float = 200.0,
    cfo_ratio: float = 0.9,
    price0: float = 100.0,
    price_growth: float = 0.12,
    receivable_days: float = 60.0,
    cfo_override: list[float] | None = None,
    quarters: bool = True,
) -> list[dict[str, Any]]:
    """A steadily growing company. Amounts are ₹ crore; shares in crore; prices in ₹."""
    out: list[dict[str, Any]] = []
    ys = years or YEARS

    def add(
        section: str, item: str, ptype: str, end: dt.date, value: float, unit: str = "cr"
    ) -> None:
        out.append(
            {
                "isin": isin,
                "metric_id": f"{section}.{item}",
                "period_type": ptype,
                "period_end": end.isoformat(),
                "reported_on": None,
                "value": value,
                "unit": unit,
                "source_id": "screener_export",
                "raw_hash": "t",
                "version": 1,
            }
        )

    sales = sales0
    equity = 300.0
    for i, y in enumerate(ys):
        sales *= 1 + growth
        pbt = sales * (pat_margin * 1.35)
        pat = sales * pat_margin
        dep = sales * 0.03
        intr = max(1.0, borrowings0 * 0.09)
        oth = sales * 0.01
        add("annual_pl", "Sales", "annual", y, sales)
        add("annual_pl", "Other Income", "annual", y, oth)
        add("annual_pl", "Depreciation", "annual", y, dep)
        add("annual_pl", "Interest", "annual", y, intr)
        add("annual_pl", "Profit before tax", "annual", y, pbt)
        add("annual_pl", "Net profit", "annual", y, pat)
        add("annual_pl", "Dividend Amount", "annual", y, pat * 0.2)
        equity += pat * 0.8
        add("balance_sheet", "Equity Share Capital", "annual", y, 50.0)
        add("balance_sheet", "Reserves", "annual", y, equity - 50.0)
        add("balance_sheet", "Borrowings", "annual", y, borrowings0)
        add("balance_sheet", "Total Assets", "annual", y, equity + borrowings0 + 150.0)
        add("balance_sheet", "Net Block", "annual", y, 250.0 + 40.0 * i)
        add("balance_sheet", "Capital Work in Progress", "annual", y, 20.0)
        add("balance_sheet", "Receivables", "annual", y, sales * receivable_days / 365)
        add("balance_sheet", "Cash & Bank", "annual", y, 60.0 + 5.0 * i)
        add("balance_sheet", "No. of Equity Shares", "annual", y, shares_cr * 1e7, "count")
        cfo = cfo_override[i] if cfo_override else pat * cfo_ratio + dep
        add("cash_flow", "Cash from Operating Activity", "annual", y, cfo)
        add("derived", "Adjusted Equity Shares in Cr", "annual", y, shares_cr, "count_cr")
        add("annual_price", "PRICE:", "annual", y, price0 * (1 + price_growth) ** (i + 1), "inr")
    if quarters:
        q_sales = sales / 4
        for j, q in enumerate(QUARTERS):
            qs = q_sales * (1.02 ** (j - 11))
            add("quarterly_pl", "Sales", "quarter", q, qs)
            add("quarterly_pl", "Operating Profit", "quarter", q, qs * margin)
            add("quarterly_pl", "Net profit", "quarter", q, qs * pat_margin)
            add("quarterly_pl", "Profit before tax", "quarter", q, qs * pat_margin * 1.35)
    return out


def shareholding(
    isin: str = "INE000000000", pledge_pct: float = 0.0, promoter: float = 55.0
) -> list[dict[str, Any]]:
    ends = [
        dt.date(2025, 6, 30),
        dt.date(2025, 9, 30),
        dt.date(2025, 12, 31),
        dt.date(2026, 3, 31),
        dt.date(2026, 6, 30),
    ]
    return [
        {
            "isin": isin,
            "period_end": e,
            "reported_on": e + dt.timedelta(days=20),
            "promoter_pct": promoter,
            "pledge_pct": pledge_pct,
            "fii_pct": 18.0 + i * 0.5,
            "dii_pct": 12.0 + i * 0.4,
        }
        for i, e in enumerate(ends)
    ]
