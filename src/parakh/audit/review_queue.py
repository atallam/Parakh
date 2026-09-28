"""Human review queue (C4.5, C7.3): high-stakes or low-confidence outputs wait here."""

from __future__ import annotations

import datetime as dt
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["pending", "approved", "rejected"]


class ReviewItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
    kind: str
    reason: str
    payload: dict[str, Any]
    status: Status = "pending"
    decided_by: str | None = None


class ReviewQueue:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> list[ReviewItem]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [ReviewItem.model_validate(item) for item in raw]

    def _save(self, items: list[ReviewItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [item.model_dump() for item in items]
        self.path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def add(self, *, kind: str, payload: dict[str, Any], reason: str) -> ReviewItem:
        with self._lock:
            items = self._load()
            item = ReviewItem(kind=kind, payload=payload, reason=reason)
            items.append(item)
            self._save(items)
            return item

    def pending(self) -> list[ReviewItem]:
        return [item for item in self._load() if item.status == "pending"]

    def decide(self, item_id: str, *, approved: bool, by: str) -> ReviewItem:
        with self._lock:
            items = self._load()
            for item in items:
                if item.id == item_id:
                    item.status = "approved" if approved else "rejected"
                    item.decided_by = by
                    self._save(items)
                    return item
        raise KeyError(item_id)


def default_queue() -> ReviewQueue:
    return ReviewQueue(Path("state") / "review_queue.json")
