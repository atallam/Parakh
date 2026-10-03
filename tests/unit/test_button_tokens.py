"""Signed, expiring button payloads (AC-F11.9)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.audit.ids import new_ulid
from parakh.notify.tokens import TokenError, derive_key, mint, verify

KEY = derive_key("123456:ABC")
TODAY = dt.date(2026, 10, 5)


def test_round_trip_and_telegram_size_limit() -> None:
    aid = new_ulid()
    token = mint(KEY, "m", aid, TODAY + dt.timedelta(days=30))
    assert len(token.encode()) <= 64
    assert verify(KEY, token, TODAY) == ("m", aid)


@pytest.mark.ac("AC-F11.9")
def test_expired_tampered_and_malformed_tokens_are_rejected() -> None:
    aid = new_ulid()
    token = mint(KEY, "u", aid, TODAY + dt.timedelta(days=30))
    with pytest.raises(TokenError) as e:
        verify(KEY, token, TODAY + dt.timedelta(days=31))
    assert e.value.reason == "expired"
    action, rest = token.split(".", 1)
    swapped = "n." + rest  # a different action with the old signature
    with pytest.raises(TokenError) as e2:
        verify(KEY, swapped, TODAY)
    assert e2.value.reason == "tampered" and action == "u"
    with pytest.raises(TokenError) as e3:
        verify(KEY, "garbage", TODAY)
    assert e3.value.reason == "malformed"
    with pytest.raises(TokenError):
        verify(derive_key("999:other"), token, TODAY)  # another bot's key
