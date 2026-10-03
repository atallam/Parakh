"""Signed, expiring button payloads for Telegram callbacks (plan 03 §4.3; AC-F11.9).

    token = mint(key, "m", alert_id, today + 30 days)      # "m.01JB….FS8.a1b2c3d4"
    action, alert_id = verify(key, token, today)           # raises TokenError

A tap on an old or edited button is rejected, not applied. The key is derived from the bot
token, so there is no extra secret to keep.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac

EPOCH = dt.date(1970, 1, 1)
ACTIONS = frozenset("unmars")  # u useful · n noise · m mute · a approve · r reject · s snooze


class TokenError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason  # malformed | tampered | expired


def derive_key(bot_token: str) -> bytes:
    return hashlib.sha256(b"parakh-button|" + bot_token.encode("utf-8")).digest()


def _b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out or "0"


def _mac(key: bytes, action: str, alert_id: str, exp: str) -> str:
    return hmac.new(key, f"{action}.{alert_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:8]


def mint(key: bytes, action: str, alert_id: str, expires: dt.date) -> str:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    exp = _b36((expires - EPOCH).days)
    token = f"{action}.{alert_id}.{exp}.{_mac(key, action, alert_id, exp)}"
    if len(token.encode()) > 64:  # Telegram's callback_data limit
        raise ValueError("token longer than 64 bytes")
    return token


def verify(key: bytes, token: str, today: dt.date) -> tuple[str, str]:
    parts = token.split(".")
    if len(parts) != 4 or parts[0] not in ACTIONS:
        raise TokenError("malformed")
    action, alert_id, exp, mac = parts
    if not hmac.compare_digest(mac, _mac(key, action, alert_id, exp)):
        raise TokenError("tampered")
    try:
        expires = EPOCH + dt.timedelta(days=int(exp, 36))
    except ValueError as exc:
        raise TokenError("malformed") from exc
    if today > expires:
        raise TokenError("expired")
    return action, alert_id
