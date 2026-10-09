"""Concall transcripts for the qualitative agent: cached text, never a fetch at call time (AG-06).

    store = TranscriptStore(root)
    store.put(Transcript(...))                  # the daily or monthly job, through the adapter
    doc = store.get(isin)                       # the MCP tool; text goes out only as untrusted content

One current transcript per stock (plus the previous one for the tone diff), each a text file named by
its SHA-256 so the qualitative cache can key on the document hash (AC-F06.3).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from parakh.config import state_dir

KEEP_PER_STOCK = 2


@dataclass
class CachedDoc:
    isin: str
    symbol: str
    period: str  # YYYY-MM of the call
    source_url: str
    sha256: str
    fetched_on: str
    pages: int
    text: str = ""
    notes: list[str] = field(default_factory=list)

    def is_stale(self, today: dt.date, max_age_days: int) -> bool:
        y, m = int(self.period[:4]), int(self.period[5:7])
        return (today - dt.date(y, m, 1)).days > max_age_days


@dataclass
class FetchStatus:
    """Why a stock has no transcript, so it is never silently skipped (AC-F06.7)."""

    isin: str
    ok: bool
    stage: str = ""  # list_calls | fetch | validate
    reason: str = ""
    log: list[str] = field(default_factory=list)
    at: str = ""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class TranscriptStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or state_dir() / "docs" / "transcripts"

    def _index(self, isin: str) -> Path:
        return self.root / isin / "index.json"

    def _rows(self, isin: str) -> list[dict]:  # type: ignore[type-arg]
        p = self._index(isin)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def put(self, doc: CachedDoc) -> CachedDoc:
        folder = self.root / doc.isin
        folder.mkdir(parents=True, exist_ok=True)
        rows = [r for r in self._rows(doc.isin) if r["sha256"] != doc.sha256]
        (folder / f"{doc.sha256.removeprefix('sha256:')[:16]}.txt").write_text(
            doc.text, encoding="utf-8"
        )
        meta = {k: v for k, v in doc.__dict__.items() if k != "text"}
        rows.append(meta)
        rows.sort(key=lambda r: r["period"])
        for old in rows[:-KEEP_PER_STOCK]:
            (folder / f"{old['sha256'].removeprefix('sha256:')[:16]}.txt").unlink(missing_ok=True)
        self._index(doc.isin).write_text(
            json.dumps(rows[-KEEP_PER_STOCK:], indent=1), encoding="utf-8"
        )
        return doc

    def get(self, isin: str, *, previous: bool = False) -> CachedDoc | None:
        rows = self._rows(isin)
        if len(rows) < (2 if previous else 1):
            return None
        row = rows[-2] if previous else rows[-1]
        path = self.root / isin / f"{row['sha256'].removeprefix('sha256:')[:16]}.txt"
        if not path.exists():
            return None
        return CachedDoc(**row, text=path.read_text(encoding="utf-8"))

    def record_status(self, status: FetchStatus) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / "status.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data[status.isin] = status.__dict__
        p.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def status(self, isin: str) -> FetchStatus | None:
        p = self.root / "status.json"
        if not p.exists():
            return None
        row = json.loads(p.read_text(encoding="utf-8")).get(isin)
        return FetchStatus(**row) if row else None
