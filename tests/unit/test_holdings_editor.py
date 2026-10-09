"""The manual lot editor validates before it writes (AC-F15.3)."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.services.holdings_editor import MANUAL_ACCOUNT, LotInput, MemoryLotWriter, add_lot

GOOD = {"isin": "INE040A01034", "qty": 10, "price_inr": 1500.5, "trade_date": dt.date(2026, 9, 1)}


@pytest.mark.ac("AC-F15.3")
@pytest.mark.parametrize(
    "patch",
    [
        {"qty": 0},
        {"qty": -1},
        {"price_inr": 0},
        {"price_inr": -5},
        {"trade_date": dt.date.today() + dt.timedelta(days=1)},
        {"isin": "INE040A01035"},  # wrong check digit
        {"isin": "HDFCBANK"},
    ],
)
def test_bad_input_is_refused(patch) -> None:
    with pytest.raises(ValidationError):
        LotInput(**{**GOOD, **patch})


@pytest.mark.ac("AC-F15.3")
def test_a_valid_lot_is_written_with_a_buy_transaction_and_a_quiet_audit_event() -> None:
    w = MemoryLotWriter()
    lot = add_lot(w, LotInput(**GOOD))
    assert w.lots[0]["lot_id"] == w.txns[0]["lot_id"] == lot.lot_id
    assert w.lots[0]["account_ref"] == MANUAL_ACCOUNT and w.lots[0]["source"] == "cli"
    assert lot.settle_date > lot.trade_date
    ev = [e for e in get_sink().events() if e.event_type == AUD.HOLDINGS_LOT_ADDED]
    assert len(ev) == 1 and "qty" not in str(ev[0].details) and "1500" not in str(ev[0].details)
