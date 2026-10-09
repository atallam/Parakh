"""post_monthly (lock, enrich, curate, review) and the refresh drain (F06, F14, F25; AC-F06.7, AC-F25.4)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.adapters.concalls import Transcript, Validation
from parakh.audit.context import RunContext
from parakh.audit.emit import get_sink
from parakh.configs import load_all
from parakh.orchestration import post_monthly as pm
from parakh.orchestration.refresh import drain, fetch_transcript
from parakh.registry import discover
from parakh.services.documents import TranscriptStore
from parakh.services.job_requests import JobRequests
from parakh.watch.state import StateStore
from tests.watchlist.test_service import PILOT

TODAY = dt.date(2026, 10, 30)
TEXT = "We expect revenue growth of 18 to 20 percent in FY27 and a steady order book."


class FakeProvider:
    def __init__(self, tx: Transcript | None = None, boom: bool = False) -> None:
        self.tx, self.boom = tx, boom

    def latest_valid(self, symbol: str, max_candidates: int = 4):  # type: ignore[no-untyped-def]
        if self.boom:
            raise RuntimeError("503")
        return self.tx, ["tried newest call"]


def transcript() -> Transcript:
    return Transcript(
        symbol=PILOT.symbol, period=dt.date(2026, 9, 1), source_url="https://s", final_url="https://bse/x.pdf",
        sha256="sha256:abc123", pages=4, text=TEXT, validation=Validation(True),
    )  # fmt: skip


def ctx() -> RunContext:
    return RunContext.create(mode="refresh", actor_type="scheduler", actor_id="t")


@pytest.mark.ac("AC-F06.7")
def test_a_failed_fetch_is_recorded_with_its_stage(tmp_path) -> None:
    ts = TranscriptStore(tmp_path)
    assert (
        fetch_transcript(
            FakeProvider(boom=True), ts, isin=PILOT.isin, symbol=PILOT.symbol, today=TODAY
        )
        is None
    )
    st = ts.status(PILOT.isin)
    assert st and not st.ok and st.stage == "list_calls"
    assert (
        fetch_transcript(FakeProvider(None), ts, isin=PILOT.isin, symbol=PILOT.symbol, today=TODAY)
        is None
    )
    assert ts.status(PILOT.isin).stage == "validate"  # type: ignore[union-attr]
    doc = fetch_transcript(
        FakeProvider(transcript()), ts, isin=PILOT.isin, symbol=PILOT.symbol, today=TODAY
    )
    assert doc and doc.period == "2026-09" and ts.status(PILOT.isin).ok  # type: ignore[union-attr]


@pytest.mark.ac("AC-F25.4")
def test_the_drain_serves_the_queue_and_waits_out_a_monthly_run(tmp_path) -> None:
    discover()
    store, ts = StateStore(tmp_path), TranscriptStore(tmp_path / "docs")
    bundle = load_all()
    jobs = JobRequests(store, 5)
    jobs.request(PILOT.isin, "new_transcript", "agent:event_triage")
    jobs.lock_monthly(True)
    held = drain(
        FakeProvider(transcript()),
        None,
        bundle,
        ctx(),
        get_sink(),
        today=TODAY,
        store=store,
        transcripts=ts,
    )
    assert held.served == 0 and len(jobs.queued()) == 1  # left for after the monthly run
    jobs.lock_monthly(False)
    res = drain(
        FakeProvider(transcript()),
        None,
        bundle,
        ctx(),
        get_sink(),
        today=TODAY,
        store=store,
        transcripts=ts,
    )
    assert res.skipped == 1 and not jobs.queued()  # no agents wired: skipped, not stuck forever


@pytest.mark.ac("AC-F25.4")
def test_the_monthly_lock_is_held_during_the_review_and_always_released(
    tmp_path, monkeypatch
) -> None:
    store = StateStore(tmp_path)
    seen: list[bool] = []

    def fake_review(svc, snaps, **kw):  # type: ignore[no-untyped-def]
        seen.append(JobRequests(store, 5).monthly_running())
        raise RuntimeError("boom")

    monkeypatch.setattr(pm, "monthly_review", fake_review)
    with pytest.raises(RuntimeError):
        pm.post_monthly(
            load_all(),
            None,
            ctx(),
            get_sink(),
            period="2026-10",
            today=TODAY,
            snaps=[],
            store=store,
        )
    assert seen == [True] and not JobRequests(store, 5).monthly_running()


def test_without_a_runner_only_the_rule_based_review_runs(tmp_path) -> None:
    out = pm.post_monthly(
        load_all(), None, ctx(), get_sink(), period="2026-10", today=TODAY, snaps=[], store=StateStore(tmp_path)
    )  # fmt: skip
    assert out.curator_status == "skipped" and out.watchlist_line.startswith("🗂 Watchlist review")
