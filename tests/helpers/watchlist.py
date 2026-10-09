"""Builders for watchlist tests."""

from __future__ import annotations

import datetime as dt
import zlib
from typing import Any

from parakh.audit.context import RunContext
from parakh.configs import load_all
from parakh.watchlist.facts import Facts
from parakh.watchlist.models import Entry, WatchlistState, period_of

TODAY = dt.date(2026, 10, 30)
PERIOD = "2026-10"


def cfg():  # type: ignore[no-untyped-def]
    return load_all().watchlist


def fx(
    symbol: str,
    *,
    cap: str = "mid",
    combined: float = 60.0,
    rank_pct: float = 50.0,
    **kw: Any,
) -> Facts:
    isin = kw.pop("isin", f"INE{zlib.crc32(symbol.encode()) % 10**6:06d}01011")
    return Facts(isin=isin, symbol=symbol, cap=cap, combined=combined, rank_pct=rank_pct, **kw)


def top(symbol: str, *, cap: str = "mid", combined: float = 80.0, **kw: Any) -> Facts:
    """A stock the top-combined source accepts."""
    return fx(symbol, cap=cap, combined=combined, rank_pct=kw.pop("rank_pct", 5.0), **kw)


def entry(
    f: Facts,
    *,
    kind: str = "system",
    added_period: str = "2026-06",
    sources: list[str] | None = None,
    **kw: Any,
) -> Entry:
    y, m = int(added_period[:4]), int(added_period[5:7])
    return Entry(
        entry_id=f"E-{f.symbol}",
        isin=f.isin,
        symbol=f.symbol,
        cap=f.cap,  # type: ignore[arg-type]
        list_kind=kind,  # type: ignore[arg-type]
        added_on=dt.date(y, m, 15),
        added_period=added_period,
        added_by="rule" if kind == "system" else "user",
        sources=sources if sources is not None else ["SRC.top_combined"],
        reason="test",
        last_period=kw.pop("last_period", None),
        **kw,
    )


def state_with(*entries: Entry) -> WatchlistState:
    return WatchlistState(entries={e.entry_id: e for e in entries})


def ctx() -> RunContext:
    return RunContext.create(mode="watchlist", asof=TODAY, actor_type="user", actor_id="test")


__all__ = ["PERIOD", "TODAY", "cfg", "ctx", "entry", "fx", "period_of", "state_with", "top"]
