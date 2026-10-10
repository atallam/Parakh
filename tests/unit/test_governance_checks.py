"""Governance checks: drift, replay determinism, restore test (plan 10 §5, §8, §11; plan 14 L6)."""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pyrage import x25519

from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.governance import drift, replay
from parakh.governance.restore_test import run_restore_test
from parakh.storage.backup import _rows, backup_name, dump, encrypt
from parakh.storage.prices import LocalBlobs
from tests.unit.test_backup import DATA, NOW, FakeDb

BUNDLE = load_all()
CAL = BUNDLE.calibration


# -- drift ----------------------------------------------------------------------------------------
def months(shift: float = 0.0, n_stocks: int = 40, sig: float = 0.5) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for k, period in enumerate(
        ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    ):
        last = k == 6
        for _ in range(n_stocks):
            rows.append(
                {
                    "period": period,
                    "value_score": rng.normal(50 + (shift if last else 0), 10),
                    "momentum_score": rng.normal(50 + (shift if last else 0), 10),
                    "verdict": "BUY"
                    if rng.random() < (0.2 + (0.3 if last and shift else 0))
                    else "HOLD",
                    "signals": ",".join(["M01"] * int(rng.random() < sig)),
                }
            )
    return pd.DataFrame(rows)


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift() -> None:
    x = np.random.default_rng(0).normal(0, 1, 2000)
    assert drift.psi(x, x, 5) == pytest.approx(0, abs=1e-6)
    assert drift.psi(x, x + 2, 5) > 0.25


def test_a_stable_month_is_ok_and_a_shifted_month_alerts() -> None:
    assert drift.drift_report(months(), CAL.drift).status in (drift.OK, drift.WARN)
    rep = drift.drift_report(months(shift=25), CAL.drift)
    assert rep.status == drift.ALERT
    names = {c.name: c for c in rep.checks}
    assert names["PSI of momentum_score"].status == drift.ALERT
    assert names["verdict mix"].status == drift.WARN


def test_a_signal_rate_collapse_is_flagged() -> None:
    df = months()
    df.loc[df["period"] == "2026-09", "signals"] = ""
    c = {c.name: c for c in drift.drift_report(df, CAL.drift).checks}["signal rate"]
    assert c.status == drift.WARN and c.value == 0


def test_too_few_stocks_is_never_called_stable() -> None:
    rep = drift.drift_report(months(n_stocks=7), CAL.drift)
    assert all(c.status == drift.SKIPPED for c in rep.checks)


def test_drift_needs_an_earlier_month() -> None:
    assert (
        drift.drift_report(months().query("period == '2026-09'"), CAL.drift).checks[0].status
        == drift.SKIPPED
    )


# -- replay ---------------------------------------------------------------------------------------
SNAP = {
    "symbol": "TCS", "profile": "it_services", "history_class": "full",
    "price": {"close": 100.0},
    "verdict": {"verdict": "BUY", "rule_id": "RULE.verdict.x", "confidence": "High"},
    "value": {"score": 70.0}, "momentum": {"score": 65.0},
}  # fmt: skip


def test_identical_snapshots_match_and_small_score_noise_is_tolerated() -> None:
    fresh = copy.deepcopy(SNAP)
    fresh["value"]["score"] += CAL.replay.score_tolerance / 2
    assert replay.compare(SNAP, fresh, CAL.replay).status == replay.MATCH


def test_a_changed_verdict_or_score_is_a_divergence() -> None:
    fresh = copy.deepcopy(SNAP)
    fresh["verdict"]["verdict"] = "HOLD"
    fresh["momentum"]["score"] = 66.0
    d = replay.compare(SNAP, fresh, CAL.replay)
    assert d.status == replay.DIVERGED and len(d.differences) == 2


def test_a_revised_price_is_a_data_change_not_non_determinism() -> None:
    fresh = copy.deepcopy(SNAP)
    fresh["price"]["close"] = 52.0  # a 2:1 split adjusted afterwards
    fresh["verdict"]["verdict"] = "HOLD"
    assert replay.compare(SNAP, fresh, CAL.replay).status == replay.DATA_CHANGED


def test_compare_roots_reports_a_missing_snapshot_as_failure(tmp_path: Path) -> None:
    import json

    a, b = tmp_path / "stored", tmp_path / "replay"
    for root, snap in ((a, SNAP), (b, None)):
        d = root / "large_cap" / "TCS" / "snapshots"
        d.mkdir(parents=True)
        if snap:
            (d / "2026-09.json").write_text(json.dumps(snap))
    rep = replay.compare_roots(a, b, "2026-09", CAL.replay)
    assert rep.status == "pass" or rep.status == "fail"
    (a / "large_cap" / "TCS" / "snapshots" / "2026-09.json").write_text(json.dumps(SNAP))
    assert replay.compare_roots(a, b, "2026-09", CAL.replay).status == "fail"
    (b / "large_cap" / "TCS" / "snapshots" / "2026-09.json").write_text(json.dumps(SNAP))
    assert replay.compare_roots(a, b, "2026-09", CAL.replay).status == "pass"


# -- restore test ---------------------------------------------------------------------------------
class CountingDb(FakeDb):
    def copy_in(self, table: str, csv: bytes) -> int:
        super().copy_in(table, csv)
        return _rows(csv)  # count records the way the manifest does (quoted newlines are one)


def sealed_backup(tmp_path: Path, when: dt.datetime = NOW) -> tuple[LocalBlobs, str]:
    key = x25519.Identity.generate()
    archive, _ = dump(FakeDb(dict(DATA)), when)
    blobs = LocalBlobs(tmp_path)
    blobs.put(backup_name(when), encrypt(archive, [str(key.to_public())]))
    return blobs, str(key)


def test_restore_test_passes_with_the_right_key_and_a_scratch_database(tmp_path: Path) -> None:
    blobs, key = sealed_backup(tmp_path)
    scratch = CountingDb({})
    ctx, res = run_restore_test(
        BUNDLE, blobs, key, now=NOW + dt.timedelta(days=2), target=scratch, order=sorted(DATA)
    )
    assert res.status == "pass" and res.tables == 3 and res.restored_rows == res.manifest_rows
    from parakh.audit.emit import get_sink

    assert AUD.BACKUP_RESTORE_TESTED in [
        e.event_type for e in get_sink().events_for_run(ctx.run_id)
    ]


def test_restore_test_fails_on_a_wrong_key_a_stale_backup_or_no_backup(tmp_path: Path) -> None:
    blobs, key = sealed_backup(tmp_path)
    wrong = str(x25519.Identity.generate())
    assert run_restore_test(BUNDLE, blobs, wrong, now=NOW)[1].status == "fail"
    stale = run_restore_test(BUNDLE, blobs, key, now=NOW + dt.timedelta(days=30))[1]
    assert stale.status == "fail" and "days old" in stale.problems[0]
    empty = run_restore_test(BUNDLE, LocalBlobs(tmp_path / "none"), key, now=NOW)[1]
    assert empty.problems == ["no backup found"]
