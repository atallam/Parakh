"""Audit core: ULIDs, hash chain, run lifecycle, manifest (plan 10; T-AUD-01…)."""

from __future__ import annotations

import json

import pytest

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditEvent, get_sink
from parakh.audit.events import AUD
from parakh.audit.ids import is_ulid, new_ulid
from parakh.audit.manifest import read_manifest
from parakh.audit.steps import audited_step, run_lifecycle
from parakh.orchestration.jobs import run_dummy


def test_ulids_are_unique_sortable_and_well_formed() -> None:
    """T-AUD-01"""
    ids = [new_ulid() for _ in range(500)]
    assert len(set(ids)) == 500
    assert ids == sorted(ids)
    assert all(is_ulid(i) for i in ids)
    assert new_ulid(now_ms=0).startswith("0000000000")


@pytest.mark.ac("AC-F21.1")
def test_successful_run_has_one_start_and_one_end() -> None:
    """T-AUD-02"""
    ctx, outcome = run_dummy()
    types = [e.event_type for e in get_sink().events_for_run(ctx.run_id)]
    assert types == [AUD.RUN_START, AUD.RUN_END]
    assert outcome.status == "SUCCESS_AUDIT_PENDING"  # no Supabase syncer before Phase 1
    assert [s.status for s in ctx.steps] == ["ok", "ok", "ok"]


@pytest.mark.ac("AC-F21.1")
def test_failed_run_has_one_start_and_one_abort_and_still_writes_a_manifest() -> None:
    """T-AUD-03"""
    ctx = RunContext.create(mode="dummy")
    with pytest.raises(RuntimeError), run_lifecycle(ctx), audited_step(ctx, "boom"):
        raise RuntimeError("source down")
    types = [e.event_type for e in get_sink().events_for_run(ctx.run_id)]
    assert types == [AUD.RUN_START, AUD.RUN_ABORT]
    manifest = read_manifest(ctx.run_id)
    assert manifest is not None
    assert manifest.status == "FAILED"
    assert manifest.steps[0].status == "failed"
    assert "source down" in (manifest.steps[0].error or "")


def test_run_is_success_once_every_event_is_synced() -> None:
    """T-AUD-04: AC-F21.5's rule, with a syncer that accepts everything."""

    class AllSynced:
        name = "test"

        def flush(self, events: list[AuditEvent]) -> int:
            return len(events)

    sink = get_sink()
    sink.syncer = AllSynced()
    _, outcome = run_dummy(sink=sink)
    assert outcome.status == "SUCCESS"


def test_manifest_records_provenance() -> None:
    """T-AUD-05"""
    ctx, _ = run_dummy()
    manifest = read_manifest(ctx.run_id)
    assert manifest is not None
    assert manifest.config_hash.startswith("sha256:")
    assert manifest.audit_events == 2
    assert manifest.audit_chain_head == get_sink().head()
    assert manifest.steps[1].outputs["rows"] == 7
    assert all(s.step_id.startswith(ctx.run_id + ".") for s in manifest.steps)


@pytest.mark.ac("AC-F21.4")
def test_chain_detects_tampering_with_any_record() -> None:
    """T-AUD-06"""
    run_dummy()
    run_dummy()
    sink = get_sink()
    assert sink.verify_chain().ok
    path = next(sink.outbox.glob("*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["reason"] = "edited later"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    check = sink.verify_chain()
    assert not check.ok
    assert check.first_bad_event == record["event_id"]


@pytest.mark.ac("AC-F21.4")
def test_chain_detects_a_deleted_record() -> None:
    """T-AUD-07"""
    run_dummy()
    sink = get_sink()
    path = next(sink.outbox.glob("*.jsonl"))
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    assert not sink.verify_chain().ok
