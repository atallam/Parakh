"""ULIDs: time-sortable IDs for runs, events, MCP calls and agent runs (plan 10 §3).

A ULID is 48 bits of milliseconds since the epoch plus 80 random bits, written as 26
Crockford base32 characters. Sorting ULIDs as strings sorts them by creation time, so
searching `01JB6X` finds everything one run touched.
"""

from __future__ import annotations

import os
import re
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid(now_ms: int | None = None) -> str:
    """A new ULID. Within the same millisecond the random part increments (monotonic)."""
    global _last_ms, _last_rand
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    with _lock:
        if ms == _last_ms:
            _last_rand = (_last_rand + 1) & ((1 << 80) - 1)
        else:
            _last_ms = ms
            _last_rand = int.from_bytes(os.urandom(10), "big")
        rand = _last_rand
    return _encode(ms, 10) + _encode(rand, 16)


def is_ulid(value: str) -> bool:
    return bool(ULID_RE.match(value))
