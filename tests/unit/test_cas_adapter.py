"""CAS dict → CasStatement against the synthetic statements. T-ADP-30…"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from pathlib import Path

import pytest

from parakh.adapters.cas import CasFormatError, account_ref, from_casparser
from parakh.privacy import contains_pii

CAS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cas"
AUG = json.loads((CAS_DIR / "synthetic_cas_2026-08.json").read_text(encoding="utf-8"))
SEP = json.loads((CAS_DIR / "synthetic_cas_2026-09.json").read_text(encoding="utf-8"))
KEY = b"test-key-not-secret"


def test_holdings_and_period() -> None:
    """T-ADP-30"""
    s = from_casparser(SEP, KEY)
    assert (s.period_from, s.period_to) == (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert len(s.account_refs) == 3
    qty = s.qty_by_isin()
    assert qty["INE101A01026"] == 30 and "INE249Z01020" not in qty  # MAZDOCK sold in Sep
    assert all(h.avg_cost_inr is None for h in s.holdings if h.is_equity)


def test_account_refs_are_stable_across_statements_and_keyed() -> None:
    """T-ADP-31"""
    assert from_casparser(AUG, KEY).account_refs == from_casparser(SEP, KEY).account_refs
    assert account_ref("IN300000", "10000001", KEY) != account_ref("IN300000", "10000001", b"other")
    with pytest.raises(ValueError, match="key"):
        from_casparser(SEP, b"")


@pytest.mark.ac("AC-F03.7")
def test_no_identifier_survives_the_import() -> None:
    """T-ADP-32: no PAN, name, address, contact or DP/client ID in the result (P6)."""
    s = from_casparser(SEP, KEY)
    text = repr(dataclasses.asdict(s))
    pii = SEP["investor_info"] | SEP["_synthetic_pii"]
    ids = [v for a in SEP["accounts"] for v in (a["dp_id"], a["client_id"])]
    for value in [*pii.values(), *ids]:
        assert str(value) not in text
    assert not contains_pii(text)


def test_a_non_cas_dict_is_refused() -> None:
    """T-ADP-33"""
    with pytest.raises(CasFormatError):
        from_casparser({"folios": []}, KEY)
