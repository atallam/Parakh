"""The alerts log and the shadow logs (plan 10 §13 `alerts_log`; plan 03 §8).

`AlertsLog` is append-only JSONL under `<state>/alerts/`, one row per alert decision, **including
suppressed ones** (plan 10 §14: silence must be explainable). A mirror callable copies each row to
the Supabase `alerts_log` table when a database is configured; the file stays the source for the
daily integrity check.

`ShadowLog` writes the Markdown you review twice a week during shadow mode: what would have been
sent, with a `[ ] noise` box to tick (UAT-2). `logs/alerts_shadow.md` holds watcher and event alerts,
`logs/agents_shadow.md` holds everything agents produced while `agents.dry_run` is on.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from parakh.audit.emit import canonical_json
from parakh.config import state_dir
from parakh.watch.state import logs_dir

_TAGS = re.compile(r"<[^>]+>")


class AlertsLog:
    def __init__(
        self, root: Path | None = None, mirror: Callable[[dict[str, Any]], None] | None = None
    ) -> None:
        self.root = root or state_dir() / "alerts"
        self.path = self.root / "alerts_log.jsonl"
        self.mirror = mirror
        self._lock = threading.Lock()

    def record(self, row: dict[str, Any]) -> None:
        row = {"ts_utc": dt.datetime.now(dt.UTC).isoformat(), **row}
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(canonical_json(row) + "\n")
        if self.mirror is not None:
            with contextlib.suppress(Exception):  # best effort; the file is the record
                self.mirror(row)

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def find(self, alert_id: str) -> dict[str, Any] | None:
        return next((r for r in self.rows() if r.get("alert_id") == alert_id), None)

    def count(self, since: dt.datetime, decision: str | None = None) -> int:
        n = 0
        for r in self.rows():
            if dt.datetime.fromisoformat(r["ts_utc"]) < since:
                continue
            if decision is None or r.get("decision") == decision:
                n += 1
        return n


def plain(text: str) -> str:
    """Telegram HTML to plain Markdown-safe text for the shadow files."""
    return _TAGS.sub("", text).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


class ShadowLog:
    def __init__(self, name: str = "alerts_shadow.md", root: Path | None = None) -> None:
        self.path = (root or logs_dir()) / name
        self.title = {
            "alerts_shadow.md": "Alerts shadow log: what would have been sent",
            "agents_shadow.md": "Agents shadow log: what the agents produced",
        }.get(name, name)

    def append(
        self, *, when: dt.datetime, heading: str, lines: list[str], alert_ids: list[str]
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with self.path.open("a", encoding="utf-8") as fh:
            if new:
                fh.write(
                    f"# {self.title}\n\nTick `noise` on anything you would not want to receive; "
                    "the review reads these boxes (plan 09 Phase 3 go-live gate).\n"
                )
            fh.write(f"\n## {when:%Y-%m-%d %H:%M} · {heading}\n")
            for line in lines:
                fh.write(f"- {plain(line)}\n")
            ids = " ".join(f"`{a}`" for a in alert_ids)
            fh.write(f"- [ ] noise  {ids}\n")

    def noise_ratio(self) -> tuple[int, int]:
        """(ticked, total) boxes: the go-live gate wants ticked/total at or under 30%."""
        if not self.path.exists():
            return 0, 0
        text = self.path.read_text(encoding="utf-8")
        ticked = len(re.findall(r"^- \[[xX]\] noise", text, re.M))
        total = ticked + len(re.findall(r"^- \[ \] noise", text, re.M))
        return ticked, total
