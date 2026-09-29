"""Tax lots, settlement dates and CAS reconciliation (plan 05 §2; plan 13 D8; F03).

The CAS says how many shares each account holds; the cost-basis seed (a broker P&L report, or
`parakh holdings add`) says what each lot cost. This module joins the two:

- `settlement_date`: the CAS counts settled shares, so a lot is compared with a statement only
  if it settled on or before the statement's end date. India moved to T+1 on 27 Jan 2023
  (T+2 before). Found on the Phase 1 files: two buys on 31 Aug 2026 reached the demat on 1 Sep
  and were missing from the August CAS; on trade dates the reconciliation failed, on settlement
  dates all 12 holdings matched.
- `reconcile`: per ISIN, CAS quantity vs settled lot quantity. A shortfall of lots becomes a
  "complete this trade" prompt with cost pending (AC-F03.6), never a guessed cost.
- `sell_fifo`: sales reduce the oldest lots first and record realised P&L (AC-F03.2).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from parakh.adapters.broker_pnl import BrokerPnl
from parakh.adapters.cas import CasStatement
from parakh.audit.ids import new_ulid

T1_FROM = dt.date(2023, 1, 27)  # why: SEBI's T+1 rollout completed on this date for all stocks
QTY_TOLERANCE = 1e-6  # why: whole shares (and ETF units to 3 dp) compared as floats

LotSource = Literal["broker_pnl", "cli", "cas_prompt"]
ReconStatus = Literal["match", "lots_missing", "cas_missing", "not_in_cas", "no_lots"]


def settlement_date(trade_date: dt.date, holidays: Iterable[dt.date] = ()) -> dt.date:
    """Trade date + 1 (or 2 before 27 Jan 2023) trading days, skipping weekends and `holidays`.

    Formula: advance day by day, counting only weekdays not in `holidays`.
    Pitfall: without the exchange holiday list a holiday is treated as a trading day, which only
    matters when a holiday falls right after a month-end trade.
    """
    days = 1 if trade_date >= T1_FROM else 2
    closed = set(holidays)
    d = trade_date
    while days:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d not in closed:
            days -= 1
    return d


@dataclass(frozen=True)
class Lot:
    lot_id: str
    account_ref: str
    isin: str
    qty: float
    trade_date: dt.date
    settle_date: dt.date
    price_inr: float | None  # None = cost pending (AC-F03.6)
    source: LotSource

    @property
    def cost_pending(self) -> bool:
        return self.price_inr is None


def lots_from_broker(
    report: BrokerPnl, account_ref: str, holidays: Iterable[dt.date] = ()
) -> list[Lot]:
    closed = tuple(holidays)
    return [
        Lot(
            lot_id=new_ulid(),
            account_ref=account_ref,
            isin=b.isin,
            qty=b.qty,
            trade_date=b.trade_date,
            settle_date=settlement_date(b.trade_date, closed),
            price_inr=b.price_inr,
            source="broker_pnl",
        )
        for b in sorted(report.open_lots, key=lambda x: (x.trade_date, x.isin))
    ]


def settled_qty(lots: Iterable[Lot], as_of: dt.date) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = defaultdict(float)
    for lot in lots:
        if lot.settle_date <= as_of:
            out[(lot.account_ref, lot.isin)] += lot.qty
    return dict(out)


def match_broker_account(
    cas: CasStatement, report: BrokerPnl, holidays: Iterable[dt.date] = ()
) -> str | None:
    """The one CAS account whose holdings equal the broker's settled lots, or None.

    The broker report doesn't name the demat account, so the account is inferred: every ISIN
    the broker holds (settled by the CAS date) must be in that account at the same quantity.
    """
    closed = tuple(holidays)
    broker_qty: dict[str, float] = defaultdict(float)
    for b in report.open_lots:
        if settlement_date(b.trade_date, closed) <= cas.period_to:
            broker_qty[b.isin] += b.qty
    candidates = []
    for ref in cas.account_refs:
        held: dict[str, float] = defaultdict(float)
        for h in cas.holdings:
            if h.account_ref == ref:
                held[h.isin] += h.qty
        if broker_qty and all(
            abs(held.get(isin, 0.0) - q) <= QTY_TOLERANCE for isin, q in broker_qty.items()
        ):
            candidates.append(ref)
    return candidates[0] if len(candidates) == 1 else None


@dataclass(frozen=True)
class ReconRow:
    account_ref: str
    isin: str
    cas_qty: float
    lot_qty: float  # settled by the statement date
    in_transit_qty: float  # lots traded before, settling after, the statement date
    status: ReconStatus

    @property
    def gap(self) -> float:
        return self.cas_qty - self.lot_qty


def reconcile(
    cas: CasStatement, lots: Iterable[Lot], accounts: Iterable[str] | None = None
) -> list[ReconRow]:
    """Compare a statement with the stored lots, per account and ISIN.

    Only accounts in `accounts` are compared (default: every account that has lots), because an
    account with no cost-basis seed yet would otherwise show every holding as "no_lots".
    Statuses: match; lots_missing (CAS holds more: a buy to complete, cost pending);
    cas_missing (lots exceed the CAS: an unrecorded sale); not_in_cas (lots for an ISIN the
    account no longer holds); no_lots (the account holds it, no lot recorded).
    """
    lots = list(lots)
    as_of = cas.period_to
    scope = set(accounts) if accounts is not None else {lot.account_ref for lot in lots}
    cas_qty: dict[tuple[str, str], float] = defaultdict(float)
    for h in cas.holdings:
        if h.account_ref in scope:
            cas_qty[(h.account_ref, h.isin)] += h.qty
    settled = settled_qty((lot for lot in lots if lot.account_ref in scope), as_of)
    transit: dict[tuple[str, str], float] = defaultdict(float)
    for lot in lots:
        if lot.account_ref in scope and lot.trade_date <= as_of < lot.settle_date:
            transit[(lot.account_ref, lot.isin)] += lot.qty
    rows = []
    for key in sorted(set(cas_qty) | set(settled)):
        c, s = cas_qty.get(key, 0.0), settled.get(key, 0.0)
        if abs(c - s) <= QTY_TOLERANCE:
            status: ReconStatus = "match"
        elif s == 0:
            status = "no_lots"
        elif c == 0:
            status = "not_in_cas"
        elif c > s:
            status = "lots_missing"
        else:
            status = "cas_missing"
        rows.append(ReconRow(key[0], key[1], c, s, transit.get(key, 0.0), status))
    return rows


def pending_lots(rows: Iterable[ReconRow], cas: CasStatement) -> list[Lot]:
    """One cost-pending lot per shortfall: the "complete this trade" prompts (AC-F03.6)."""
    out = []
    for row in rows:
        if row.status in ("lots_missing", "no_lots") and row.gap > QTY_TOLERANCE:
            out.append(
                Lot(
                    lot_id=new_ulid(),
                    account_ref=row.account_ref,
                    isin=row.isin,
                    qty=row.gap,
                    trade_date=cas.period_to,  # latest possible; you confirm the real date
                    settle_date=cas.period_to,
                    price_inr=None,
                    source="cas_prompt",
                )
            )
    return out


@dataclass(frozen=True)
class RealisedLot:
    lot_id: str
    isin: str
    qty: float
    buy_date: dt.date
    buy_price_inr: float | None
    sell_date: dt.date
    sell_price_inr: float

    @property
    def pnl_inr(self) -> float | None:
        if self.buy_price_inr is None:
            return None
        return self.qty * (self.sell_price_inr - self.buy_price_inr)


def sell_fifo(
    lots: list[Lot], account_ref: str, isin: str, qty: float, price_inr: float, date: dt.date
) -> tuple[list[Lot], list[RealisedLot]]:
    """Reduce the oldest lots first (demat shares are FIFO for capital gains; plan 05 §2.2)."""
    mine = sorted(
        (lot for lot in lots if lot.account_ref == account_ref and lot.isin == isin),
        key=lambda x: (x.trade_date, x.lot_id),
    )
    if sum(lot.qty for lot in mine) + QTY_TOLERANCE < qty:
        raise ValueError(f"{isin}: selling more than the account's lots hold")
    remaining = qty
    realised: list[RealisedLot] = []
    changed: dict[str, Lot | None] = {}
    for lot in mine:
        if remaining <= QTY_TOLERANCE:
            break
        take = min(lot.qty, remaining)
        realised.append(
            RealisedLot(lot.lot_id, isin, take, lot.trade_date, lot.price_inr, date, price_inr)
        )
        left = lot.qty - take
        changed[lot.lot_id] = replace(lot, qty=left) if left > QTY_TOLERANCE else None
        remaining -= take
    out = []
    for lot in lots:
        if lot.lot_id in changed:
            updated = changed[lot.lot_id]
            if updated is not None:
                out.append(updated)
        else:
            out.append(lot)
    return out, realised
