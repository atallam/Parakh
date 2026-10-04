"""Persistent watcher state: plain JSON files, written atomically (plan 03 §5, §7).

    store = StateStore(root)
    mom = store.load("momentum_state")      # {} when the file does not exist yet
    store.save("momentum_state", mom)

Files (all under `<root>/`, which GitHub Actions keeps on the `parakh-data` branch):
- `momentum_state.json`  per-ISIN indicator state, active and pending signals
- `events_seen.json`     every filing already alerted, so each alerts exactly once (AC-F13.1)
- `alert_state.json`     last-sent dates for cool-downs, mutes, digest queue, bot offset, counters

State is small, human-readable and diffable in git, which is the point: a wrong alert can be
explained by reading the file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from parakh.config import state_dir

WATCH_STATE_ENV = "PARAKH_WATCH_STATE_DIR"


def watch_state_dir() -> Path:
    override = os.environ.get(WATCH_STATE_ENV)
    return Path(override) if override else state_dir() / "watch"


def logs_dir() -> Path:
    """Shadow logs live beside the state so one branch carries both (plan 03 §8)."""
    override = os.environ.get("PARAKH_LOGS_DIR")
    return Path(override) if override else watch_state_dir().parent / "logs"


class StateStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or watch_state_dir()

    def path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def load(self, name: str) -> dict[str, Any]:
        path = self.path(name)
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def save(self, name: str, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
