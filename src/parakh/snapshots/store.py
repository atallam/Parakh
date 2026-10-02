"""Where generated files live and how snapshots are read and written (plan 00 §4).

    <output>/<cap>_cap/<SYMBOL>/snapshots/YYYY-MM.json     canonical
    <output>/<cap>_cap/<SYMBOL>/reports/YYYY-MM.md         rendered
    <output>/<cap>_cap/<SYMBOL>/charts/YYYY-MM-*.png       rendered
    <output>/<cap>_cap/<SYMBOL>/history.csv, HISTORY.md    rendered, rewritten each run
    <output>/<cap>_cap/<SYMBOL>/THESIS.md                  yours; the pipeline never writes it
    <output>/<cap>_cap/_SEGMENT_SUMMARY/YYYY-MM.{md,csv,xlsx,json}

Re-running a month overwrites that month's files, never adds a second copy (AC-F09.2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from parakh.config import output_dir
from parakh.snapshots.models import Snapshot

SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def safe_name(symbol: str) -> str:
    """A symbol as a folder name: `M&M` stays `M&M`, `/` and other path characters become `_`."""
    return SAFE.sub("_", symbol)


def cap_dir(cap: str, root: Path | None = None) -> Path:
    return (root or output_dir()) / f"{cap}_cap"


def stock_dir(cap: str, symbol: str, root: Path | None = None) -> Path:
    return cap_dir(cap, root) / safe_name(symbol)


def snapshot_path(cap: str, symbol: str, period: str, root: Path | None = None) -> Path:
    return stock_dir(cap, symbol, root) / "snapshots" / f"{period}.json"


def write_snapshot(snap: Snapshot, root: Path | None = None) -> Path:
    path = snapshot_path(snap.cap, snap.symbol, snap.period, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snap.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=False)
        + "\n",
        encoding="utf-8",
    )
    return path


def read_snapshot_dict(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def periods_for(cap: str, symbol: str, root: Path | None = None) -> list[str]:
    folder = stock_dir(cap, symbol, root) / "snapshots"
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if PERIOD.match(p.stem))


def previous_period(periods: list[str], period: str) -> str | None:
    earlier = [p for p in periods if p < period]
    return earlier[-1] if earlier else None


def load_previous(cap: str, symbol: str, period: str, root: Path | None = None) -> dict | None:
    """The newest snapshot strictly before `period`, or None for a stock's first month."""
    prev = previous_period(periods_for(cap, symbol, root), period)
    return read_snapshot_dict(snapshot_path(cap, symbol, prev, root)) if prev else None


def all_stock_dirs(cap: str, root: Path | None = None) -> list[Path]:
    base = cap_dir(cap, root)
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_"))
