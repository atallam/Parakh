"""The Home inbox: items that wait for the owner until they are seen (plan 12 §4; AC-F23.4).

Phase 3 writes them to `inbox.json` beside the other watch state, one per thesis status change on an
owned stock; the Streamlit Home page of Phase 4 reads the same file. An item is never deleted by a
job, only marked `seen` by the owner.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from parakh.audit.ids import new_ulid
from parakh.watch.state import StateStore

NAME = "inbox"
KEEP = 300


class Inbox:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def items(self) -> list[dict[str, Any]]:
        return list(self.store.load(NAME).get("items", []))

    def add(
        self,
        *,
        kind: str,
        isin: str | None,
        symbol: str | None,
        title: str,
        detail: str,
        key: str,
        asof: dt.date,
    ) -> bool:
        """Add one item; the same `key` is never added twice. Returns whether it was added."""
        items = self.items()
        if any(i["key"] == key for i in items):
            return False
        items.append(
            {
                "id": new_ulid(),
                "key": key,
                "kind": kind,
                "isin": isin,
                "symbol": symbol,
                "title": title,
                "detail": detail,
                "asof": asof.isoformat(),
                "seen": False,
            }
        )
        self.store.save(NAME, {"items": items[-KEEP:]})
        return True

    def unseen(self) -> list[dict[str, Any]]:
        return [i for i in self.items() if not i["seen"]]
