"""The filings the Event Watcher has seen, kept for `data.get_document` (AC-F24.7).

Keyed by the alert's dedupe key; entries older than the seen-memory are dropped with it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from parakh.watch.state import StateStore

NAME = "events_docs"
KEEP_DAYS = 120


class DocStore:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.store.load(NAME).get(doc_id)

    def put_many(self, docs: dict[str, dict[str, Any]], today: dt.date) -> None:
        if not docs:
            return
        data = self.store.load(NAME)
        data.update(docs)
        cutoff = (today - dt.timedelta(days=KEEP_DAYS)).isoformat()
        data = {k: v for k, v in data.items() if str(v.get("filed") or today.isoformat()) >= cutoff}
        self.store.save(NAME, data)
