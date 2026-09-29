"""Broker P&L report → tax lots: the one-time cost-basis seed (plan 13 D8; plan 05 §2).

Supports Groww's "Stocks P&L Report" (.xlsx), the format of your broker. Findings from the
Phase 1 pilot files that shape this:
- "Trade Level" lists one row per open lot (buy date, quantity, price), not just averages, and
  its lots add up exactly to the "Scrip Level" holdings. Both are checked on every import.
- Buy price excludes charges: buy value = quantity × price exactly, and the scrip-level average
  is buy value ÷ quantity. Charges appear only as account totals.
- Dates are trade dates. The CAS counts settled shares, so a lot bought on the statement's last
  day is not in that statement (reconcile on settlement date; see parakh.holdings).
- The header holds your name and Unique Client Code, and the file name carries the client code.
  Neither is read into the result, and callers must not log the file name (P6).
"""

from __future__ import annotations

import datetime as dt
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field

import openpyxl

TRADE_SHEET = "Trade Level"
SCRIP_SHEET = "Scrip Level"
# Rows at the top of the report that identify you. They are skipped, never parsed (P6).
IDENTITY_LABELS = frozenset({"Name", "Unique Client Code"})
PERIOD = re.compile(r"from (\d{2}-\d{2}-\d{4}) TO (\d{2}-\d{2}-\d{4})", re.I)
HOLDINGS_AS_OF = re.compile(r"Holdings as on (\d{2}-\d{2}-\d{4})", re.I)
ISIN = re.compile(r"^IN[A-Z0-9]{9}\d$")
# why: the report rounds prices to 2 decimals, so an average recomputed from lots can differ
# from the printed one by up to half a paisa; anything beyond 1 paisa is a real mismatch.
AVG_PRICE_TOLERANCE_INR = 0.01
QTY_TOLERANCE = 1e-6  # why: quantities are whole shares printed as floats


class BrokerReportError(ValueError):
    pass


@dataclass(frozen=True)
class BrokerLot:
    """One open buy lot as the broker reports it (trade date, price excluding charges)."""

    isin: str
    name: str
    qty: float
    trade_date: dt.date
    price_inr: float

    @property
    def value_inr(self) -> float:
        return self.qty * self.price_inr


@dataclass(frozen=True)
class RealisedTrade:
    isin: str
    name: str
    qty: float
    buy_date: dt.date
    buy_price_inr: float
    sell_date: dt.date
    sell_price_inr: float


@dataclass(frozen=True)
class ScripHolding:
    isin: str
    name: str
    qty: float
    avg_price_inr: float


@dataclass
class BrokerPnl:
    broker: str
    period_from: dt.date
    period_to: dt.date
    holdings_as_of: dt.date
    open_lots: list[BrokerLot]
    realised: list[RealisedTrade]
    holdings: dict[str, ScripHolding]
    issues: list[str] = field(default_factory=list)

    def lots_for(self, isin: str) -> list[BrokerLot]:
        return sorted(
            (lot for lot in self.open_lots if lot.isin == isin), key=lambda x: x.trade_date
        )

    def avg_cost_inr(self, isin: str) -> float | None:
        lots = self.lots_for(isin)
        qty = sum(lot.qty for lot in lots)
        return sum(lot.value_inr for lot in lots) / qty if qty else None


def _date(value: object) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.datetime.strptime(value.strip(), "%d-%m-%Y").date()
    raise BrokerReportError(f"expected a date, got {type(value).__name__}")


def _num(value: object) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise BrokerReportError(f"expected a number, got {type(value).__name__}")


def _is_isin(value: object) -> bool:
    return isinstance(value, str) and bool(ISIN.match(value.strip()))


def _rows(wb: openpyxl.Workbook, sheet: str) -> list[tuple[object, ...]]:
    if sheet not in wb.sheetnames:
        raise BrokerReportError(f"no '{sheet}' sheet (got {wb.sheetnames}); not a Groww P&L report")
    rows = []
    for row in wb[sheet].iter_rows(values_only=True):
        if row and isinstance(row[0], str) and row[0].strip() in IDENTITY_LABELS:
            continue  # P6: identity rows are dropped before anything reads them
        rows.append(tuple(row))
    return rows


def parse_groww_pnl(data: bytes) -> BrokerPnl:
    """Parse a Groww Stocks P&L report. Raises BrokerReportError if the layout is unknown."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        trade_rows = _rows(wb, TRADE_SHEET)
        scrip_rows = _rows(wb, SCRIP_SHEET)
    finally:
        wb.close()

    period = next(
        (PERIOD.search(str(r[0])) for r in trade_rows if r and r[0] and PERIOD.search(str(r[0]))),
        None,
    )
    if period is None:
        raise BrokerReportError("statement period line not found")
    as_of = next(
        (
            HOLDINGS_AS_OF.search(str(r[0]))
            for r in scrip_rows
            if r and r[0] and HOLDINGS_AS_OF.search(str(r[0]))
        ),
        None,
    )
    if as_of is None:
        raise BrokerReportError("'Holdings as on' line not found")

    open_lots: list[BrokerLot] = []
    realised: list[RealisedTrade] = []
    section = None
    for r in trade_rows:
        first = str(r[0]).strip() if r and r[0] is not None else ""
        if first == "Realised trades":
            section = "realised"
            continue
        if first == "Unrealised trades":
            section = "open"
            continue
        if first.startswith("Disclaimer"):
            section = None
        if section is None or len(r) < 6 or not _is_isin(r[1]):
            continue
        name, isin = first, str(r[1]).strip()
        if section == "open":
            open_lots.append(BrokerLot(isin, name, _num(r[2]), _date(r[3]), _num(r[4])))
        else:
            realised.append(
                RealisedTrade(
                    isin, name, _num(r[2]), _date(r[3]), _num(r[4]), _date(r[6]), _num(r[7])
                )
            )

    holdings: dict[str, ScripHolding] = {}
    in_unrealised = False
    for r in scrip_rows:
        first = str(r[0]).strip() if r and r[0] is not None else ""
        if HOLDINGS_AS_OF.search(first):
            in_unrealised = True
            continue
        if in_unrealised and len(r) > 3 and _is_isin(r[1]):
            isin = str(r[1]).strip()
            holdings[isin] = ScripHolding(isin, first, _num(r[2]), _num(r[3]))

    report = BrokerPnl(
        broker="groww",
        period_from=_date(period.group(1)),
        period_to=_date(period.group(2)),
        holdings_as_of=_date(as_of.group(1)),
        open_lots=open_lots,
        realised=realised,
        holdings=holdings,
    )
    _check(report)
    return report


def _check(report: BrokerPnl) -> None:
    """Lots must add up to the per-stock holdings, at the broker's own average price.

    Issue texts name the ISIN only: quantities and costs are holdings data and never go into
    text that may be logged (AC-F21.11).
    """
    lot_qty: dict[str, float] = defaultdict(float)
    for lot in report.open_lots:
        lot_qty[lot.isin] += lot.qty
    for isin in sorted(set(lot_qty) | set(report.holdings)):
        held = report.holdings.get(isin)
        if held is None:
            report.issues.append(f"{isin}: lots with no holdings row")
            continue
        if abs(lot_qty.get(isin, 0.0) - held.qty) > QTY_TOLERANCE:
            report.issues.append(f"{isin}: lots do not add up to the holdings row")
            continue
        avg = report.avg_cost_inr(isin)
        if avg is not None and abs(avg - held.avg_price_inr) > AVG_PRICE_TOLERANCE_INR:
            report.issues.append(f"{isin}: average cost from lots differs from the report's")
