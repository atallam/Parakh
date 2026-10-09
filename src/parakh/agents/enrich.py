"""Write the qualitative and devil's-advocate results onto a snapshot after the monthly run (F06/F07).

The deterministic snapshot is never recomputed. Enrichment adds two overlays and, at most, moves the
verdict's confidence by one level (AC-F07.2); it never changes the verdict wording, the scores or the
thesis status (D13: the LLM flags, the owner decides).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEVELS = ["Low", "Med", "High"]


def shift_confidence(current: str | None, delta: int) -> str | None:
    """One level at most, clamped to the ends; unknown values stay as they are."""
    if current is None or current.title() not in LEVELS:
        return current
    step = max(-1, min(1, delta))
    return LEVELS[max(0, min(len(LEVELS) - 1, LEVELS.index(current.title()) + step))]


def enrich_snapshot(
    path: Path,
    *,
    qualitative: dict[str, Any] | None = None,
    devils_advocate: dict[str, Any] | None = None,
    confidence_delta: int = 0,
) -> bool:
    """Merge overlays into a snapshot file in place. Returns False when the file is missing."""
    if not path.exists():
        return False
    snap = json.loads(path.read_text(encoding="utf-8"))
    if qualitative is not None:
        snap["qualitative"] = qualitative
    if devils_advocate is not None:
        snap["devils_advocate"] = devils_advocate
    if confidence_delta and "verdict" in snap:
        before = snap["verdict"].get("confidence")
        after = shift_confidence(before, confidence_delta)
        if after != before:
            snap["verdict"]["confidence_before_devils_advocate"] = before
            snap["verdict"]["confidence"] = after
    path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True
