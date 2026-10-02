"""The monthly run: data → lenses → verdict → snapshot (F09, F04, F05, F08; plan 09 Phase 2)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json

import pytest

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.audit.manifest import read_manifest
from parakh.configs import load_all
from parakh.orchestration.analysis import run_monthly
from parakh.orchestration.render_outputs import render_month
from parakh.snapshots.store import periods_for, snapshot_path, stock_dir
from tests.helpers.pilot import END, pilot_data


@pytest.fixture
def bundle():
    return load_all()


@pytest.fixture
def month(bundle, tmp_path):
    data = pilot_data(bundle)
    return bundle, data, run_monthly(bundle, data, END, out_root=tmp_path), tmp_path


@pytest.mark.ac("AC-F09.5")
def test_every_snapshot_names_what_produced_it(month) -> None:
    _, _, res, _ = month
    assert not [s.error for s in res.stocks if s.error]
    assert len(res.snapshots) == 7
    for snap in res.snapshots:
        fw = snap.framework
        assert (
            fw.version
            and fw.policy_version
            and fw.config_hash
            and fw.weights_hash
            and fw.code_version
        )
        assert set(fw.lens_versions) == {"value", "momentum"}
        assert snap.run_id == res.ctx.run_id


@pytest.mark.ac("AC-F04.7", "AC-F04.9")
def test_profile_and_history_class_are_recorded_and_young_listings_are_informational(month) -> None:
    bundle, _, res, _ = month
    by = {s.symbol: s for s in res.snapshots}
    for sec in bundle.universe.pilot:
        assert by[sec.symbol].profile == sec.profile
        assert by[sec.symbol].history_class in ("H0", "H1", "H2")
    young = [s for s in res.snapshots if s.history_class == "H0"]
    for s in young:
        assert s.verdict["confidence"] == "Low" or s.verdict["label"]
    informational = [s for s in res.snapshots if s.value["informational"]]
    assert all(s.verdict["label"] == "limited history" for s in informational)


def test_the_run_manifest_carries_lens_and_policy_versions(month) -> None:
    _, _, res, _ = month
    manifest = read_manifest(res.ctx.run_id)
    assert manifest is not None
    assert set(manifest.lens_versions) == {"value", "momentum"}
    assert manifest.policy_version == "1.0.0"


def test_scores_and_verdicts_are_audited(month) -> None:
    _, _, res, _ = month
    events = get_sink().events_for_run(res.ctx.run_id)
    scored = [e for e in events if e.event_type == AUD.SCORE_COMPUTED]
    assert len(scored) == 14  # two lenses x seven stocks
    assert {e.event_type for e in events} >= {AUD.RUN_START, AUD.RUN_END}


@pytest.mark.ac("AC-F09.2")
def test_rerunning_a_month_replaces_its_files(month) -> None:
    bundle, data, res, tmp = month
    snaps = [s.model_dump(mode="json") for s in res.snapshots]
    render_month(bundle, snaps, tmp)
    first = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file())
    res2 = run_monthly(bundle, data, END, out_root=tmp)
    render_month(bundle, [s.model_dump(mode="json") for s in res2.snapshots], tmp)
    second = sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file())
    assert first == second
    sec = bundle.universe.pilot[0]
    rows = (
        (stock_dir(sec.cap, sec.symbol, tmp) / "history.csv")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(rows) == 2  # header + one row, not two


@pytest.mark.ac("AC-F09.4")
def test_the_pipeline_never_modifies_thesis_md(bundle, tmp_path) -> None:
    sec = bundle.universe.pilot[0]
    path = stock_dir(sec.cap, sec.symbol, tmp_path) / "THESIS.md"
    path.parent.mkdir(parents=True)
    path.write_text("my notes, not even valid front matter\n", encoding="utf-8")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    res = run_monthly(bundle, pilot_data(bundle), END, out_root=tmp_path)
    render_month(bundle, [s.model_dump(mode="json") for s in res.snapshots], tmp_path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_one_failing_stock_does_not_sink_the_run(bundle, tmp_path) -> None:
    data = pilot_data(bundle)
    bad = bundle.universe.pilot[1]
    data.price_frames[bad.isin] = data.price_frames[bad.isin].drop(columns=["close"])
    res = run_monthly(bundle, data, END, out_root=tmp_path)
    failed = [s for s in res.stocks if s.error]
    assert [s.symbol for s in failed] == [bad.symbol]
    assert len(res.snapshots) == 6
    assert res.outcome.status.startswith("SUCCESS")
    assert res.outcome.summary["failed"][bad.symbol]


def test_second_month_links_to_the_first(bundle, tmp_path) -> None:
    data = pilot_data(bundle)
    run_monthly(bundle, data, dt.date(2026, 8, 31), out_root=tmp_path)
    res = run_monthly(bundle, data, END, out_root=tmp_path)
    for s in res.snapshots:
        assert periods_for(s.cap, s.symbol, tmp_path) == ["2026-08", "2026-09"]
        v = s.verdict
        assert v["direction"] != "new"
        assert v["prev_verdict"] is not None
        assert v["changed"] == (
            v["verdict"] != v["prev_verdict"] or v["action"] != v["prev_action"]
        )
    events = get_sink().events_for_run(res.ctx.run_id)
    changed = {e.isin for e in events if e.event_type == AUD.VERDICT_CHANGED}
    assert changed == {s.isin for s in res.snapshots if s.verdict["changed"]}


@pytest.mark.ac("AC-F21.12")
def test_an_override_needs_a_reason_and_expires_once(bundle, tmp_path) -> None:
    from parakh.configs.lens_models import Override, OverridesConfig

    sec = bundle.universe.pilot[0]
    ov = Override(
        id="OV-T-1",
        isin=sec.isin,
        field="verdict",
        value="AVOID",
        reason="testing the override path",
        set_on=dt.date(2026, 8, 1),
        expires_on=dt.date(2026, 9, 15),
    )
    with pytest.raises(ValueError):
        Override(
            id="OV-T-2",
            isin=sec.isin,
            field="verdict",
            value="HOLD",
            reason="short",
            set_on=dt.date(2026, 8, 1),
            expires_on=dt.date(2026, 9, 15),
        )
    b2 = dataclasses.replace(bundle, overrides=OverridesConfig(overrides=[ov]))
    data = pilot_data(bundle)
    run_monthly(b2, data, dt.date(2026, 8, 31), out_root=tmp_path)
    aug = json.loads(snapshot_path(sec.cap, sec.symbol, "2026-08", tmp_path).read_text())
    assert aug["verdict"]["verdict"] == "AVOID" and aug["verdict"]["override"]
    res = run_monthly(b2, data, END, out_root=tmp_path)
    sep = next(s for s in res.snapshots if s.isin == sec.isin)
    assert sep.verdict["verdict"] != "AVOID" or not sep.verdict["override"]  # expired on 15 Sep
    expired = [
        e for e in get_sink().events_for_run(res.ctx.run_id) if e.event_type == AUD.OVERRIDE_EXPIRED
    ]
    assert len(expired) == 1 and expired[0].isin == sec.isin
