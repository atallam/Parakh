"""T-DOC-01…: document-sourced value inputs: verified only, point in time, filings win."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.analytics.document_inputs import document_inputs_for
from parakh.configs import load_all
from parakh.configs.models import DocumentInputsConfig, DocumentValue

ISIN = "INE249Z01020"
ASOF = dt.date(2026, 10, 30)


def _cfg(verified: bool, as_of: dt.date = dt.date(2026, 6, 30)) -> DocumentInputsConfig:
    item = DocumentValue(
        value=18218, as_of=as_of, tier="T2", source="Q1 FY27 presentation", verified=verified
    )
    return DocumentInputsConfig(inputs={ISIN: {"order_book_cr": item, "unlisted_book_cr": None}})


def test_shipped_file_only_ever_uses_verified_values() -> None:
    """Whatever the owner has verified is used with lineage; everything else is withheld with a reason."""
    bundle = load_all()
    for isin, items in bundle.document_inputs.inputs.items():
        values, reasons, lineage = document_inputs_for(bundle.document_inputs, isin, ASOF)
        for key, item in items.items():
            if item is not None and item.verified and item.as_of <= ASOF:
                assert key in values and key in lineage
            else:
                assert key not in values and reasons[key]


def test_verified_value_is_used_with_lineage() -> None:
    values, reasons, lineage = document_inputs_for(_cfg(True), ISIN, ASOF)
    assert values == {"order_book_cr": 18218}
    assert (
        lineage["order_book_cr"]["tier"] == "T2"
        and lineage["order_book_cr"]["as_of"] == "2026-06-30"
    )
    assert "open" in reasons["unlisted_book_cr"]


def test_unverified_value_is_withheld_with_a_reason() -> None:
    values, reasons, _ = document_inputs_for(_cfg(False), ISIN, ASOF)
    assert "order_book_cr" not in values and "awaiting your check" in reasons["order_book_cr"]


def test_value_is_not_visible_before_its_as_of_date() -> None:
    """A source dated after the run's as-of date must not leak backwards into a replay."""
    values, reasons, _ = document_inputs_for(_cfg(True, dt.date(2026, 11, 15)), ISIN, ASOF)
    assert values == {} and "after the as-of date" in reasons["order_book_cr"]


def test_t3_source_and_unknown_key_are_refused() -> None:
    with pytest.raises(ValueError):
        DocumentValue(value=1, as_of=ASOF, tier="T3", source="a convenience site")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        DocumentInputsConfig(inputs={ISIN: {"made_up_cr": None}})
