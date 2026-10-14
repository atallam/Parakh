"""Recorded source fixtures parse, and T1 and T2 agree where they should (spikes ①③④).

Captured from a GitHub-hosted runner on 29 Sep 2026 (plan 14 §4.2). These pin the formats that
Phase 1 adapters are written against; the weekly source canary compares live pages with them.
T-ADP-30…
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import openpyxl
import pytest

from parakh.adapters.screener_export import parse_export
from parakh.configs import load_all
from parakh.configs.models import isin_check_digit_ok

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
PILOT = {s.isin: s.symbol for s in load_all().universe.pilot}


def _udiff_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_nse_udiff_bhavcopy_has_every_pilot_stock() -> None:
    """T-ADP-30: UDiFF columns (ISIN, SctySrs, ClsPric) and all 7 pilots traded on 28 Sep 2026."""
    with zipfile.ZipFile(SRC / "nse" / "BhavCopy_NSE_CM_20260928.csv.zip") as z:
        rows = _udiff_rows(z.read(z.namelist()[0]).decode("utf-8"))
    eq = {r["ISIN"]: r for r in rows if r["SctySrs"] == "EQ"}
    assert set(PILOT) <= set(eq)
    assert eq["INE101A01026"]["TckrSymb"] == "M&M"
    assert all(float(eq[i]["ClsPric"]) > 0 for i in PILOT)
    assert {r["TradDt"] for r in rows} == {"2026-09-28"}


def test_bse_bhavcopy_uses_the_same_udiff_layout() -> None:
    """T-ADP-31: one parser serves both exchanges (the BSE fallback)."""
    rows = _udiff_rows(
        (SRC / "bse" / "BhavCopy_BSE_CM_20260928_pilot_and_first40.csv").read_text(encoding="utf-8")
    )
    assert {"ISIN", "TckrSymb", "ClsPric", "TradDt"} <= set(rows[0])
    assert "INE040A01034" in {r["ISIN"] for r in rows}


def test_equity_list_maps_symbols_to_current_isins() -> None:
    """T-ADP-32"""
    rows = list(
        csv.DictReader(
            io.StringIO((SRC / "nse" / "EQUITY_L_2026-09-29.csv").read_text(encoding="utf-8"))
        )
    )
    by_symbol = {r["SYMBOL"]: r[" ISIN NUMBER"].strip() for r in rows}
    for isin, symbol in PILOT.items():
        assert by_symbol[symbol] == isin, symbol


def test_split_changed_mazdocks_isin_and_nse_actions_still_use_the_old_one() -> None:
    """T-ADP-33 (spike ④ finding): the security master needs an ISIN history, like symbols."""
    actions = json.loads(
        (SRC / "nse" / "corp_actions_MAZDOCK_2026-09-29.json").read_text(encoding="utf-8")
    )
    split = next(a for a in actions if "Split" in a["subject"])
    assert split["exDate"] == "27-Dec-2024"
    old = split["isin"]
    assert old == "INE249Z01012" and isin_check_digit_ok(old)
    assert PILOT.get("INE249Z01020") == "MAZDOCK" and old not in PILOT
    assert {a["isin"] for a in actions} == {old}  # even 2026 dividends carry the pre-split ISIN


def test_index_constituents_and_amfi_list_cover_the_pilot() -> None:
    """T-ADP-34: Nifty 100/Midcap 150/Smallcap 250 lists and the AMFI Jun 2026 cap list."""
    constituents: set[str] = set()
    for name in ("ind_nifty100list", "ind_niftymidcap150list", "ind_niftysmallcap250list"):
        rows = list(
            csv.DictReader(
                io.StringIO(
                    (SRC / "niftyindices" / f"{name}_2026-09-29.csv").read_text(encoding="utf-8")
                )
            )
        )
        assert rows and "ISIN Code" in rows[0]
        constituents |= {r["ISIN Code"] for r in rows}
    assert {"INE040A01034", "INE101A01026", "INE646L01027"} <= constituents
    wb = openpyxl.load_workbook(
        SRC / "amfi" / "AverageMarketCapitalization30Jun2026.xlsx", read_only=True
    )
    cells = {
        str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c
    }
    assert set(PILOT) <= cells


def _xbrl(name: str, tag: str) -> float:
    text = (SRC / "nse" / name).read_text(encoding="utf-8")
    m = re.search(rf"<[^>]*:{tag}\b[^>]*contextRef=\"OneD\"[^>]*>([^<]+)<", text)
    assert m, tag
    return float(m.group(1))


def test_exchange_xbrl_revenue_ties_to_the_screener_export() -> None:
    """T-ADP-35: T1 (NSE XBRL, consolidated) vs T2 (Screener) for M&M, quarter to 31 Dec 2024."""
    export = parse_export((SRC / "screener" / "MM_export_2026-09-27.xlsx").read_bytes())
    screener_cr = export.series("quarterly_pl", "Sales")[dt.date(2024, 12, 31)]
    xbrl_cr = _xbrl("xbrl_MM_2024-12-31_consolidated.xml", "RevenueFromOperations") / 1e7
    assert xbrl_cr == pytest.approx(screener_cr, abs=0.01)


def test_profit_lines_need_a_definition_map() -> None:
    """T-ADP-36: XBRL ProfitLossForPeriod includes minority interest; Screener's net profit doesn't."""
    export = parse_export((SRC / "screener" / "MM_export_2026-09-27.xlsx").read_bytes())
    screener_pat = export.series("quarterly_pl", "Net profit")[dt.date(2024, 12, 31)]
    xbrl_pat = _xbrl("xbrl_MM_2024-12-31_consolidated.xml", "ProfitLossForPeriod") / 1e7
    assert screener_pat is not None and xbrl_pat > screener_pat * 1.1


def test_nse_financial_results_stop_at_dec_2024_and_carry_broadcast_times() -> None:
    """T-ADP-37: newer results sit in SEBI's integrated filing; broadcast time = reported_on."""
    rows = json.loads(
        (SRC / "nse" / "financial_results_MM_2026-09-29.json").read_text(encoding="utf-8")
    )
    rows = rows if isinstance(rows, list) else rows["data"]
    latest = max(dt.datetime.strptime(r["toDate"], "%d-%b-%Y").date() for r in rows)
    assert latest == dt.date(2024, 12, 31)
    assert all(r.get("broadCastDate") for r in rows[:10])


PEPB = SRC / "niftyindices" / "pepb"
PEPB_FILES = {
    "NIFTY 100": "NIFTY_100_Historical_PE_PB_DIV_Data_16102025to14102026.csv",
    "NIFTY MIDCAP 150": "NIFTY_MIDCAP_150_Historical_PE_PB_DIV_Data_16102025to14102026.csv",
    "NIFTY SMALLCAP 250": "NIFTY_SMALLCAP_250_Historical_PE_PB_DIV_Data_16102025to14102026.csv",
}


def _pepb(index: str) -> list[tuple[dt.date, float, float, float]]:
    """Oldest first: (date, P/E, P/B, dividend yield %). The file itself is newest first."""
    path = PEPB / PEPB_FILES[index]
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["IndexName", "Date", "P/E", "P/B", "Div Yield %"]
        rows = [
            (
                dt.datetime.strptime(r["Date"], "%d %b %Y").date(),
                float(r["P/E"]),
                float(r["P/B"]),
                float(r["Div Yield %"]),  # NSE writes ".75", not "0.75"
            )
            for r in reader
            if r["IndexName"] == index
        ]
    return sorted(rows)


@pytest.mark.parametrize("index", sorted(PEPB_FILES))
def test_nse_index_pe_pb_yield_download_keeps_one_layout(index: str) -> None:
    """T-ADP-38: the manual NSE Indices P/E, P/B and yield download (R3a, plan 17 §8b).

    Pins the layout a later loader reads: five quoted columns, `13 Oct 2026` dates, newest first,
    yield without a leading zero, one row per trading day, no duplicates, sane magnitudes.
    """
    rows = _pepb(index)
    days = [r[0] for r in rows]
    assert len(rows) == 245 and len(set(days)) == 245
    assert (days[0], days[-1]) == (dt.date(2025, 10, 16), dt.date(2026, 10, 13))
    # Sunday 1 Feb 2026 was the Union Budget special session, the only weekend date
    assert [d for d in days if d.weekday() >= 5] == [dt.date(2026, 2, 1)]
    assert all(5 < pe < 60 and 0.5 < pb < 10 and 0 < dy < 5 for _, pe, pb, dy in rows)
    first_line = (PEPB / PEPB_FILES[index]).read_text(encoding="utf-8-sig").splitlines()[1]
    assert first_line.startswith(f'"{index}","13 Oct 2026"')  # newest first


def test_nse_index_valuation_has_steps_that_are_not_price_moves() -> None:
    """T-ADP-39: the series moves in jumps that a price move cannot explain (R3a finding).

    A loader must flag these, not trade on them. Same-day yield steps hit all three indices on
    9 Oct 2026; Midcap 150 P/E falls 10.8% on 19 May 2026 while its price rises 0.8% that day.
    """
    mid = {d: (pe, pb, dy) for d, pe, pb, dy in _pepb("NIFTY MIDCAP 150")}
    assert mid[dt.date(2026, 5, 18)][0] / mid[dt.date(2026, 5, 19)][0] > 1.10
    for index in PEPB_FILES:
        series = {d: dy for d, _, _, dy in _pepb(index)}
        assert series[dt.date(2026, 10, 9)] / series[dt.date(2026, 10, 8)] > 1.20
    for index in PEPB_FILES:  # no decimal slip or unit change anywhere in the year
        rows = _pepb(index)
        steps = [abs(b[1] / a[1] - 1) for a, b in zip(rows, rows[1:], strict=False)]
        assert max(steps) < 0.15
