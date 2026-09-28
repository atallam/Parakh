"""Append-only, hash-chained audit trail (C4.5). Editing any past line breaks `verify()`."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _digest(record: dict[str, Any]) -> str:
    body = json.dumps(record, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditTrail:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = ""
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        return json.loads(last)["hash"] if last else GENESIS

    def append(self, event: str, **data: Any) -> dict[str, Any]:
        with self._lock:
            record: dict[str, Any] = {
                "ts": dt.datetime.now(dt.UTC).isoformat(),
                "event": event,
                "data": data,
                "prev": self._last_hash(),
            }
            record["hash"] = _digest(record)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
            return record

    def verify(self) -> bool:
        prev = GENESIS
        if not self.path.exists():
            return True
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                record = json.loads(line)
                claimed = record.pop("hash")
                if record["prev"] != prev or _digest(record) != claimed:
                    return False
                prev = claimed
        return True
