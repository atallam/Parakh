"""Number, money and date formatting shared by every surface (plan 12 §3.3; AC-F22.5).

Reports, Telegram, email, Streamlit and MCP all call these, so ₹19.2 L never shows as
₹1,920,000 on one surface and 19.2 lakh on another. Inputs follow the unit suffixes of
plan 04 §3.2: `pct()` takes a `_pct` value (0–100 scale), `ratio_pct()` a `_ratio` (0–1).
Missing values (None or NaN) render as an em dash, never as 0 (UX-05: unknown ≠ clean).
"""

from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MISSING = "—"
MINUS = "−"  # U+2212, typographic minus
LAKH = 100_000
CRORE = 10_000_000


def _missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _group_en_in(integer_digits: str) -> str:
    """Indian digit grouping: last three digits, then pairs (12,34,56,789)."""
    if len(integer_digits) <= 3:
        return integer_digits
    head, tail = integer_digits[:-3], integer_digits[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ",".join([*pairs, tail])


def inr(value: float | None, *, compact: bool = False, decimals: int = 0) -> str:
    """₹19,20,000 (full) or ₹19.2 L / ₹12.4 Cr (compact). Below ₹1 L compact shows in full."""
    if _missing(value):
        return MISSING
    assert value is not None
    sign = MINUS if value < 0 else ""
    amount = abs(value)
    if compact and amount >= LAKH:
        lakhs = round(amount / LAKH, 1)
        if lakhs < 100:
            return f"{sign}₹{lakhs:.1f} L"
        whole, dec = f"{amount / CRORE:.1f}".split(".")
        return f"{sign}₹{_group_en_in(whole)}.{dec} Cr"
    rounded = round(amount, decimals)
    whole = int(rounded)
    frac = f"{rounded:.{decimals}f}".split(".")[1] if decimals else ""
    body = _group_en_in(str(whole)) + (f".{frac}" if frac else "")
    return f"{sign}₹{body}"


def _signed(value: float, decimals: int, suffix: str, signed: bool) -> str:
    text = f"{abs(value):.{decimals}f}"
    if float(text) == 0:
        return f"{text}{suffix}"
    if value < 0:
        return f"{MINUS}{text}{suffix}"
    return f"+{text}{suffix}" if signed else f"{text}{suffix}"


def pct(value_pct: float | None, *, decimals: int = 1, signed: bool = True) -> str:
    """A `_pct` value (0–100 scale): 4.6 → '+4.6%'."""
    if _missing(value_pct):
        return MISSING
    assert value_pct is not None
    return _signed(value_pct, decimals, "%", signed)


def ratio_pct(value_ratio: float | None, *, decimals: int = 1, signed: bool = True) -> str:
    """A `_ratio` value (0–1 scale): 0.046 → '+4.6%'."""
    if _missing(value_ratio):
        return MISSING
    assert value_ratio is not None
    return pct(value_ratio * 100, decimals=decimals, signed=signed)


def pp(value_pp: float | None, *, decimals: int = 1) -> str:
    """Percentage points: 2.1 → '+2.1 pp'."""
    if _missing(value_pp):
        return MISSING
    assert value_pp is not None
    return _signed(value_pp, decimals, " pp", True)


def mult(value_x: float | None, *, decimals: int = 1) -> str:
    """A multiple (`_x`): 24.3 → '24.3×'."""
    if _missing(value_x):
        return MISSING
    assert value_x is not None
    return _signed(value_x, decimals, "×", False)


def date(value: dt.date | None) -> str:
    """24 Sep 2026 (no leading zero: 5 Sep 2026)."""
    if value is None:
        return MISSING
    return f"{value.day} {value.strftime('%b %Y')}"


def time_ist(value: dt.datetime | None) -> str:
    """18:30 IST. Naive datetimes are treated as UTC."""
    if value is None:
        return MISSING
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(IST).strftime("%H:%M IST")


def relative(value: dt.datetime | None, now: dt.datetime | None = None) -> str:
    """'just now', '12m ago', '5h ago', '3d ago'; older than 30 days → the date."""
    if value is None:
        return MISSING
    now = now or dt.datetime.now(dt.UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    seconds = (now - value).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86_400:
        return f"{int(seconds // 3600)}h ago"
    if seconds < 30 * 86_400:
        return f"{int(seconds // 86_400)}d ago"
    return date(value.astimezone(IST).date())
