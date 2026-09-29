"""Lots, settlement dates, CAS reconciliation and FIFO sales. T-HLD-01…"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from parakh.adapters.broker_pnl import parse_groww_pnl
from parakh.adapters.cas import from_casparser
from parakh.holdings.lots import (
    lots_from_broker,
    match_broker_account,
    pending_lots,
    reconcile,
    sell_fifo,
    settlement_date,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures"
SEP = from_casparser(
    json.loads((FIX / "cas" / "synthetic_cas_2026-09.json").read_text(encoding="utf-8")), b"k"
)
BROKER = parse_groww_pnl((FIX / "broker" / "synthetic_groww_pnl.xlsx").read_bytes())
SHADOWFAX = "INE12UN01015"


def test_settlement_is_t_plus_one_trading_day() -> None:
    """T-HLD-01"""
    assert settlement_date(dt.date(2026, 8, 31)) == dt.date(2026, 9, 1)  # Mon → Tue
    assert settlement_date(dt.date(2026, 9, 4)) == dt.date(2026, 9, 7)  # Fri → Mon
    assert settlement_date(dt.date(2026, 9, 4), [dt.date(2026, 9, 7)]) == dt.date(2026, 9, 8)
    assert settlement_date(dt.date(2022, 6, 1)) == dt.date(2022, 6, 3)  # T+2 before 27 Jan 2023


def test_the_broker_account_is_inferred_from_the_cas() -> None:
    """T-HLD-02: the broker report doesn't name the demat account; exactly one CAS account fits."""
    ref = match_broker_account(SEP, BROKER)
    assert ref is not None
    cdsl = {h.account_ref for h in SEP.holdings if h.depository == "CDSL"}
    assert cdsl == {ref}


@pytest.mark.ac("AC-F03.1")
def test_seeded_lots_reconcile_with_the_cas_and_the_broker_average() -> None:
    """T-HLD-03: CAS quantity per ISIN and the broker's average cost both hold after the seed."""
    ref = match_broker_account(SEP, BROKER)
    assert ref is not None
    lots = lots_from_broker(BROKER, ref)
    rows = reconcile(SEP, lots)
    assert {r.status for r in rows} == {"match"}
    assert {r.isin: r.cas_qty for r in rows} == {
        isin: q for isin, q in SEP.qty_by_isin().items() if isin in BROKER.holdings
    }
    for isin, held in BROKER.holdings.items():
        mine = [lot for lot in lots if lot.isin == isin]
        avg = sum(lot.qty * (lot.price_inr or 0) for lot in mine) / sum(lot.qty for lot in mine)
        assert avg == pytest.approx(held.avg_price_inr, abs=0.01)


def test_a_last_day_buy_is_in_transit_not_a_mismatch() -> None:
    """T-HLD-04: the pitfall from the real files. On trade dates Shadowfax would not reconcile."""
    ref = match_broker_account(SEP, BROKER)
    assert ref is not None
    lots = lots_from_broker(BROKER, ref)
    row = next(r for r in reconcile(SEP, lots) if r.isin == SHADOWFAX)
    assert row.status == "match" and row.in_transit_qty == 50
    by_trade_date = [dataclasses.replace(lot, settle_date=lot.trade_date) for lot in lots]
    row = next(r for r in reconcile(SEP, by_trade_date) if r.isin == SHADOWFAX)
    assert row.status == "cas_missing"


@pytest.mark.ac("AC-F03.6")
def test_a_missing_buy_becomes_one_cost_pending_prompt() -> None:
    """T-HLD-05: never a guessed cost."""
    ref = match_broker_account(SEP, BROKER)
    assert ref is not None
    lots = [lot for lot in lots_from_broker(BROKER, ref) if lot.trade_date != dt.date(2025, 12, 1)]
    rows = reconcile(SEP, lots)
    assert [r.status for r in rows if r.status != "match"] == ["no_lots"]
    prompts = pending_lots(rows, SEP)
    assert len(prompts) == 1
    assert prompts[0].isin == "INE154A01025" and prompts[0].qty == 400
    assert prompts[0].cost_pending and prompts[0].source == "cas_prompt"


@pytest.mark.ac("AC-F03.2")
def test_a_partial_sale_reduces_the_oldest_lots_first() -> None:
    """T-HLD-06"""
    ref = match_broker_account(SEP, BROKER)
    assert ref is not None
    lots = lots_from_broker(BROKER, ref)
    groww = "INE0HOQ01053"  # lots: 200 @ 151.25 (Nov 2025), 100 @ 168.40 (Mar 2026)
    after, realised = sell_fifo(lots, ref, groww, 250, 190.0, dt.date(2026, 10, 1))
    assert [(r.qty, r.buy_price_inr) for r in realised] == [(200, 151.25), (50, 168.4)]
    assert sum(r.pnl_inr or 0 for r in realised) == pytest.approx(200 * 38.75 + 50 * 21.6)
    left = [lot for lot in after if lot.isin == groww]
    assert [(lot.qty, lot.price_inr) for lot in left] == [(50, 168.4)]
    assert len(after) == len(lots) - 1
    with pytest.raises(ValueError, match="more than"):
        sell_fifo(lots, ref, groww, 301, 190.0, dt.date(2026, 10, 1))
