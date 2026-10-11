"""A yfinance-specific error must surface as PriceSourceError so the exchange fallback runs."""

from __future__ import annotations

import datetime as dt
import sys
import types

import pytest

from parakh.adapters.prices import PriceSourceError, fetch_yahoo


class YFTzMissingError(Exception):
    pass


def test_yfinance_error_becomes_price_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Ticker:
        def __init__(self, _symbol: str) -> None: ...

        def history(self, **_kwargs: object) -> None:
            raise YFTzMissingError("$BAGMANE.NS: possibly delisted; no timezone found")

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_Ticker))
    with pytest.raises(PriceSourceError, match="YFTzMissingError"):
        fetch_yahoo("BAGMANE", "INE2OVN25015", dt.date(2025, 1, 1), dt.date(2026, 10, 10))


def test_dividend_subject_with_doubled_dot_typo_does_not_crash() -> None:
    from parakh.adapters.corporate_actions import parse_nse_subject

    assert parse_nse_subject("Interim Dividend - Rs 62..50 Per Share") == [("dividend", 0.0, 62.5)]
    assert parse_nse_subject("Dividend - Rs 7.50 Per Share") == [("dividend", 0.0, 7.5)]
    assert parse_nse_subject("Dividend - Rs ..") == []
