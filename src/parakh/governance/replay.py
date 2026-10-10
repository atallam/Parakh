"""Replay determinism: re-run a past month and compare with what was stored (plan 10 §5; NFR-14).

    diffs = compare(stored_snapshot, fresh_snapshot, cfg.replay)
    report = replay_month(bundle, data, asof, stored_root)

The monthly job is meant to be a pure function of its inputs. A replay re-runs one stored month into a
scratch folder with the same code and compares each stock's snapshot: the fields in `replay.fields` must
match exactly, the two scores within `score_tolerance`. A stored close that has moved since the run is
reported as a *data change* (a price revision), not as non-determinism, so a split adjustment cannot
fail the check for the wrong reason. LLM text is never compared; it is replayed from cache.
"""

from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from parakh.configs.calibration_models import ReplayConfig

MATCH, DIVERGED, DATA_CHANGED = "match", "diverged", "data changed"


@dataclass
class StockDiff:
    symbol: str
    status: str
    differences: list[str] = field(default_factory=list)


@dataclass
class ReplayReport:
    period: str
    stocks: int
    matched: int
    diffs: list[StockDiff] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(d.status == DIVERGED for d in self.diffs):
            return "fail"
        return "pass" if self.stocks else "nothing to replay"

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status}


def _get(snap: dict[str, Any], name: str) -> Any:
    if name in ("verdict", "rule_id", "confidence"):
        return (snap.get("verdict") or {}).get(name)
    return snap.get(name)


def compare(stored: dict[str, Any], fresh: dict[str, Any], cfg: ReplayConfig) -> StockDiff:
    d = StockDiff(stored.get("symbol", "?"), MATCH)
    old, new = (stored.get("price") or {}).get("close"), (fresh.get("price") or {}).get("close")
    if old and new and abs(new / old - 1) * 100 > cfg.price_tolerance_pct:
        d.status = DATA_CHANGED
        d.differences.append(f"close {old} → {new}")
        return d
    for f in cfg.fields:
        a, b = _get(stored, f), _get(fresh, f)
        if a != b:
            d.differences.append(f"{f}: {a} → {b}")
    for lens in ("value", "momentum"):
        a, b = (stored.get(lens) or {}).get("score"), (fresh.get(lens) or {}).get("score")
        if (a is None) != (b is None) or (a is not None and abs(a - b) > cfg.score_tolerance):
            d.differences.append(f"{lens} score: {a} → {b}")
    if d.differences:
        d.status = DIVERGED
    return d


def compare_roots(
    stored_root: Path, replay_root: Path, period: str, cfg: ReplayConfig
) -> ReplayReport:
    """Compare every snapshot of `period` under the two roots."""
    from parakh.snapshots.store import read_snapshot_dict

    rep = ReplayReport(period, 0, 0)
    for path in sorted(stored_root.glob(f"**/snapshots/{period}.json")):
        stored = read_snapshot_dict(path)
        twin = replay_root / path.relative_to(stored_root)
        fresh = read_snapshot_dict(twin) if twin.exists() else None
        if stored is None:
            continue
        rep.stocks += 1
        if fresh is None:
            rep.missing.append(stored.get("symbol", path.parent.name))
            rep.diffs.append(
                StockDiff(stored.get("symbol", "?"), DIVERGED, ["no snapshot on replay"])
            )
            continue
        diff = compare(stored, fresh, cfg)
        rep.matched += diff.status == MATCH
        if diff.status != MATCH:
            rep.diffs.append(diff)
    return rep


def replay_month(bundle: Any, data: Any, asof: dt.date, stored_root: Path) -> ReplayReport:
    """Re-run the monthly job for `asof` into a scratch folder and compare with `stored_root`."""
    from parakh.orchestration.analysis import run_monthly
    from parakh.snapshots.models import period_of

    scratch = Path(tempfile.mkdtemp(prefix="parakh-replay-"))
    try:
        run_monthly(bundle, data, asof, out_root=scratch, trigger="replay")
        return compare_roots(stored_root, scratch, period_of(asof), bundle.calibration.replay)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
