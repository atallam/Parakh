"""Add a holding by hand, validated (F03 editor; AC-F15.3).

    lot = add_lot(writer, LotInput(isin=..., qty=10, price_inr=1500.0, trade_date=date(2026, 9, 1)))

Quantity and price must be above zero, the trade date cannot be in the future and the ISIN must pass
the ISO 6166 check digit. The lot is stored with source `cli` under a fixed manual account reference, plus
one `buy` transaction (history is append-only). The audit event carries the ISIN only, never quantity or cost.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.ids import new_ulid
from parakh.configs.models import isin_check_digit_ok
from parakh.holdings.lots import Lot, settlement_date

MANUAL_ACCOUNT = "acct_" + hashlib.sha256(b"parakh-manual-account").hexdigest()[:12]


class LotInput(BaseModel):
    isin: str
    qty: float = Field(gt=0, description="shares bought")
    price_inr: float = Field(gt=0, description="price per share")
    trade_date: dt.date

    @field_validator("isin")
    @classmethod
    def _isin(cls, v: str) -> str:
        v = v.strip().upper()
        if not isin_check_digit_ok(v):
            raise ValueError("not a valid ISIN (format or check digit)")
        return v

    @field_validator("trade_date")
    @classmethod
    def _past(cls, v: dt.date) -> dt.date:
        if v > dt.date.today():
            raise ValueError("trade date cannot be in the future")
        return v


class LotWriter(Protocol):
    def insert_lot(self, lot_row: dict[str, Any], txn_row: dict[str, Any]) -> None: ...


class MemoryLotWriter:
    def __init__(self) -> None:
        self.lots: list[dict[str, Any]] = []
        self.txns: list[dict[str, Any]] = []

    def insert_lot(self, lot_row: dict[str, Any], txn_row: dict[str, Any]) -> None:
        self.lots.append(lot_row)
        self.txns.append(txn_row)


class SupabaseLotWriter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def insert_lot(self, lot_row: dict[str, Any], txn_row: dict[str, Any]) -> None:
        self.client.table("holdings_lots").insert(lot_row).execute()
        self.client.table("transactions").insert(txn_row).execute()


def add_lot(
    writer: LotWriter,
    inp: LotInput,
    *,
    holidays: Iterable[dt.date] = (),
    ctx: RunContext | None = None,
    sink: AuditSink | None = None,
) -> Lot:
    lot = Lot(
        lot_id=new_ulid(), account_ref=MANUAL_ACCOUNT, isin=inp.isin, qty=inp.qty,
        trade_date=inp.trade_date, settle_date=settlement_date(inp.trade_date, holidays),
        price_inr=inp.price_inr, source="cli",
    )  # fmt: skip
    txn = {
        "txn_id": new_ulid(), "lot_id": lot.lot_id, "account_ref": lot.account_ref, "isin": lot.isin,
        "side": "buy", "qty": lot.qty, "price_inr": lot.price_inr,
        "trade_date": lot.trade_date.isoformat(), "source": "cli",
    }  # fmt: skip
    row = {
        "lot_id": lot.lot_id, "account_ref": lot.account_ref, "isin": lot.isin, "qty": lot.qty,
        "trade_date": lot.trade_date.isoformat(), "settle_date": lot.settle_date.isoformat(),
        "price_inr": lot.price_inr, "source": lot.source,
    }  # fmt: skip
    writer.insert_lot(row, txn)
    (sink or get_sink()).emit(
        ctx or RunContext.create(mode="holdings-editor", actor_type="user", actor_id="owner"),
        AUD.HOLDINGS_LOT_ADDED, entity_type="lot", entity_id=lot.lot_id, isin=lot.isin,
        details={"source": "cli"},
    )  # fmt: skip
    return lot
