"""T-VAL-01…: intrinsic-value maths (plan 01 §2.6)."""

from __future__ import annotations

import pytest

from parakh.analytics import intrinsic as iv

ARGS = dict(coe=0.125, terminal_g=0.05, explicit_years=5, fade_years=5)


def test_dcf_matches_a_hand_computation() -> None:
    """T-VAL-01: zero growth and zero fade is a perpetuity: cf × (1+tg) / (coe − tg), discounted."""
    v = iv.dcf_value(10.0, 0.05, 0.12, 0.05, 5, 5)
    # with g == terminal_g every year grows 5%: a growing perpetuity starting next year
    assert v == pytest.approx(10 * 1.05 / (0.12 - 0.05), rel=1e-9)


def test_reverse_dcf_round_trips() -> None:
    """T-VAL-02: pricing the stock at DCF(g) recovers g."""
    price = iv.dcf_value(50.0, 0.18, **ARGS)  # type: ignore[arg-type]
    assert price is not None
    g = iv.implied_growth(price, 50.0, max_g=0.4, **ARGS)  # type: ignore[arg-type]
    assert g == pytest.approx(0.18, abs=1e-6)


def test_reverse_dcf_returns_none_when_price_is_out_of_range() -> None:
    """T-VAL-03"""
    assert iv.implied_growth(1e9, 50.0, max_g=0.4, **ARGS) is None  # type: ignore[arg-type]
    assert iv.implied_growth(10.0, -5.0, max_g=0.4, **ARGS) is None  # type: ignore[arg-type]


def test_graham_and_cagr_and_irr() -> None:
    """T-VAL-04"""
    assert iv.graham_number(10, 100, 22.5) == pytest.approx((22.5 * 1000) ** 0.5)
    assert iv.graham_number(-1, 100, 22.5) is None
    assert iv.cagr(100, 200, 5) == pytest.approx(2 ** (1 / 5) - 1)
    assert iv.cagr(-1, 200, 5) is None
    # price 100, EPS 5, no growth, exit at 20x, 3 years, no dividend: value 100 → 0% return
    assert iv.expected_irr(100, 5, 0.0, 20, 3, 0.0) == pytest.approx(0.0)
    assert iv.expected_irr(100, 5, 0.1, 20, 3, 0.01) == pytest.approx(1.1 - 1 + 0.01, abs=1e-9)
