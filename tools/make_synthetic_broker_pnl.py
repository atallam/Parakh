"""Generate the synthetic broker P&L fixture (plan 14 §4.3). Real broker reports are never committed.

Shaped like Groww's "Stocks P&L Report" as confirmed on your real report (30 Sep 2026): two
sheets, "Trade Level" (a summary block, then "Realised trades" and "Unrealised trades" with one
row per lot) and "Scrip Level" (per-ISIN totals, with "Unrealised (Holdings as on DD-MM-YYYY)").
Dates are DD-MM-YYYY strings; quantities and prices are floats. The header carries a Name and a
Unique Client Code, which the importer must drop (P6); fake values here let tests prove that.

The lots cover demat account acct-c of the synthetic CAS (tools/make_synthetic_cas.py). One
Shadowfax lot is bought on 30 Sep, the September statement's last day: it settles on 1 Oct, so it
reconciles only when lots are dated by settlement, the pitfall found on the real files.
Regenerate with `uv run python tools/make_synthetic_broker_pnl.py`.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "broker" / "synthetic_groww_pnl.xlsx"

NAME = "PARAKH TEST INVESTOR"
CLIENT_CODE = 9000000001  # fake; the real report stores it as a number
FROM, TO = "01-07-2025", "06-10-2026"
# (name, isin, qty, buy date, buy price)
OPEN_LOTS = [
    ("BILLIONBRAINS GARAGE VN L", "INE0HOQ01053", 200.0, "10-11-2025", 151.25),
    ("BILLIONBRAINS GARAGE VN L", "INE0HOQ01053", 100.0, "02-03-2026", 168.4),
    ("ATHER ENERGY LIMITED", "INE0LEZ01016", 200.0, "23-06-2026", 612.0),
    ("ATHER ENERGY LIMITED", "INE0LEZ01016", 50.0, "15-09-2026", 701.55),
    ("SHADOWFAX TECHNOLOGIES L", "INE12UN01015", 150.0, "10-09-2026", 98.1),
    ("SHADOWFAX TECHNOLOGIES L", "INE12UN01015", 50.0, "30-09-2026", 104.0),
    ("ITC LTD", "INE154A01025", 400.0, "01-12-2025", 402.35),
]
# (name, isin, qty, buy date, buy price, sell date, sell price)
REALISED = [
    ("ITC LTD", "INE154A01025", 100.0, "01-08-2025", 415.0, "10-02-2026", 430.5),
]
CLOSE = {"INE0HOQ01053": 180.0, "INE0LEZ01016": 740.0, "INE12UN01015": 110.0, "INE154A01025": 410.0}


def build() -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    tl = wb.active
    assert tl is not None
    tl.title = "Trade Level"
    tl.append(["Name", NAME])
    tl.append(["Unique Client Code", CLIENT_CODE])
    tl.append([])
    tl.append([f"P&L Statement for stocks from {FROM} TO {TO}"])
    tl.append([])
    tl.append(["Summary"])
    tl.append([])
    tl.append(["P&L"])
    tl.append(["Realised P&L", sum(q * (s - b) for _, _, q, _, b, _, s in REALISED)])
    tl.append(["Unrealised P&L", sum(q * (CLOSE[i] - p) for _, i, q, _, p in OPEN_LOTS)])
    tl.append([])
    tl.append(["Charges"])
    for charge in ("Exchange Transaction Charges", "SEBI Charges", "STT", "Stamp Duty"):
        tl.append([charge, 1.0])
    tl.append(["Total", 4.0])
    tl.append([])
    tl.append(["Realised trades"])
    tl.append([])
    header = ["Stock name", "ISIN", "Quantity", "Buy date", "Buy price", "Buy value"]
    tl.append([*header, "Sell date", "Sell price", "Sell value", "Realised P&L", "Remark"])
    for name, isin, q, bd, bp, sd, sp in REALISED:
        tl.append([name, isin, q, bd, bp, q * bp, sd, sp, q * sp, q * (sp - bp), ""])
    tl.append([])
    tl.append(["Unrealised trades"])
    tl.append([])
    tl.append(
        [*header, "Closing date", "Closing price", "Closing value", "Unrealised P&L", "Remark"]
    )
    for name, isin, q, bd, bp in OPEN_LOTS:
        c = CLOSE[isin]
        tl.append([name, isin, q, bd, bp, q * bp, TO, c, q * c, q * (c - bp), ""])
    tl.append([])
    tl.append(["Disclaimer: "])
    tl.append(["This report is provided at your request (synthetic fixture)."])

    sl = wb.create_sheet("Scrip Level")
    sl.append(["Realised"])
    sl.append([])
    cols = ["Stock name", "ISIN", "Quantity", "Avg Buy price", "Buy value"]
    sl.append([*cols, "Avg Sell price", "Sell value", "Realised P&L", "Realised P&L %"])
    for name, isin, q, _, bp, _, sp in REALISED:
        sl.append([name, isin, q, bp, q * bp, sp, q * sp, q * (sp - bp), (sp - bp) / bp * 100])
    sl.append(["Total", None, None, None, 0.0, None, 0.0, 0.0, "#NUM!"])
    sl.append([])
    sl.append([f"Unrealised (Holdings as on {TO})"])
    sl.append([])
    sl.append([*cols, "Closing price", "Closing value", "Unrealised P&L", "Unrealised P&L %"])
    qty: dict[str, float] = defaultdict(float)
    value: dict[str, float] = defaultdict(float)
    names: dict[str, str] = {}
    for name, isin, q, _, bp in OPEN_LOTS:
        qty[isin] += q
        value[isin] += q * bp
        names[isin] = name
    for isin in sorted(qty, key=names.__getitem__):
        q, v, c = qty[isin], value[isin], CLOSE[isin]
        sl.append(
            [names[isin], isin, q, round(v / q, 2), v, c, q * c, q * c - v, (q * c - v) / v * 100]
        )
    sl.append(["Total", None, None, None, sum(value.values())])
    return wb


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
