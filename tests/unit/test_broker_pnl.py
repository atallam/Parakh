"""Broker P&L (Groww) importer against the synthetic report. T-ADP-20…"""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
from pathlib import Path

import openpyxl
import pytest

from parakh.adapters.broker_pnl import BrokerReportError, parse_groww_pnl

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "broker" / "synthetic_groww_pnl.xlsx"
DATA = FIXTURE.read_bytes()


def _edit(fn) -> bytes:  # type: ignore[no-untyped-def]
    wb = openpyxl.load_workbook(io.BytesIO(DATA))
    fn(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_lots_holdings_and_dates_are_read() -> None:
    """T-ADP-20"""
    r = parse_groww_pnl(DATA)
    assert r.broker == "groww"
    assert (r.period_from, r.period_to) == (dt.date(2025, 7, 1), dt.date(2026, 10, 6))
    assert r.holdings_as_of == dt.date(2026, 10, 6)
    assert len(r.open_lots) == 7 and len(r.realised) == 1
    assert set(r.holdings) == {"INE0HOQ01053", "INE0LEZ01016", "INE12UN01015", "INE154A01025"}
    assert r.issues == []
    ather = r.lots_for("INE0LEZ01016")
    assert [lot.trade_date for lot in ather] == [dt.date(2026, 6, 23), dt.date(2026, 9, 15)]


def test_average_cost_from_lots_matches_the_report() -> None:
    """T-ADP-21 (AC-F03.1 average-cost part): lots rebuild the broker's own average."""
    r = parse_groww_pnl(DATA)
    for isin, held in r.holdings.items():
        assert r.avg_cost_inr(isin) == pytest.approx(held.avg_price_inr, abs=0.01)


@pytest.mark.ac("AC-F03.7")
def test_name_and_client_code_never_leave_the_parser() -> None:
    """T-ADP-22: the identity rows are dropped before parsing (P6)."""
    r = parse_groww_pnl(DATA)
    text = repr(dataclasses.asdict(r))
    assert "PARAKH TEST INVESTOR" not in text
    assert "9000000001" not in text


def test_lots_that_do_not_add_up_are_flagged_without_numbers() -> None:
    """T-ADP-23: issue text names the ISIN only (quantities are holdings data)."""

    def bump(wb: openpyxl.Workbook) -> None:
        ws = wb["Trade Level"]
        for row in ws.iter_rows():
            if row[1].value == "INE154A01025" and row[6].value == "06-10-2026":
                ws.cell(row=row[0].row or 0, column=3, value=401.0)

    issues = parse_groww_pnl(_edit(bump)).issues
    assert issues == ["INE154A01025: lots do not add up to the holdings row"]
    assert not any(ch.isdigit() for ch in issues[0].split(":", 1)[1])


def test_a_different_workbook_is_refused() -> None:
    """T-ADP-24"""
    with pytest.raises(BrokerReportError, match="Trade Level"):
        parse_groww_pnl(_edit(lambda wb: setattr(wb["Trade Level"], "title", "Sheet1")))
