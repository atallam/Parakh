"""The per-stock signal and event history (AC-F13.4; plan 03 §6).

Every event the watcher alerts on is appended here, once, with the filing date and the rule that
fired. The Stock Detail page and the report's "what happened since" read this file. Kept to the
most recent `KEEP` rows so the state branch stays small.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from parakh.watch.state import StateStore

NAME = "signal_log"
KEEP = 3000


class SignalLog:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def rows(self, isin: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.store.load(NAME).get("rows", []))
        return [r for r in rows if isin is None or r.get("isin") == isin]

    def append(self, entries: list[dict[str, Any]]) -> int:
        if not entries:
            return 0
        rows = self.rows()
        have = {r["key"] for r in rows}
        new = [e for e in entries if e["key"] not in have]
        if new:
            self.store.save(NAME, {"rows": (rows + new)[-KEEP:]})
        return len(new)


def entry(
    *,
    key: str,
    isin: str | None,
    symbol: str | None,
    code: str,
    headline: str,
    asof: dt.date,
    kind: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "isin": isin,
        "symbol": symbol,
        "code": code,
        "headline": headline,
        "date": asof.isoformat(),
        "kind": kind,
    }
