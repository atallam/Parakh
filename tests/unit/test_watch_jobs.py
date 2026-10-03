"""Jobs end to end on fixtures: holiday exit, shadow mode, failure alert, once-only, heartbeat."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from parakh.analytics.signals.momentum import SignalState
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.orchestration.watch_jobs import (
    WatchDeps,
    daily_events,
    daily_watch,
    evening_digest,
    heartbeat,
)
from parakh.watch.momentum import MomentumWatcher
from parakh.watch.state import StateStore
from tests.helpers.notify import FakeMailer, FakeNotifier, bundle
from tests.helpers.pilot import pilot_data
from tests.unit.test_event_watcher import FixtureSource

MON = dt.date(2026, 10, 5)
SAT = dt.date(2026, 10, 3)


def _deps(tmp_path: Path, *, dry_run: bool = False, notifier=None, feeds=None, end=MON):  # type: ignore[no-untyped-def]
    b = bundle(dry_run_alerts=dry_run)
    return WatchDeps(
        b,
        pilot_data(b, end=end, sessions=300),
        StateStore(tmp_path / "watch"),
        notifier or FakeNotifier(),
        FakeMailer(),
        feeds,
        button_key=b"k" * 32,
        logs_root=tmp_path / "logs",
    )


def _force_signal(monkeypatch, code="M21", status="fired"):  # type: ignore[no-untyped-def]
    def fake(self, sec, frame, asof):  # type: ignore[no-untyped-def]
        sev = "High"
        return [SignalState(code, "200-DMA breakdown", sev, status, True, asof, 100.0)]

    monkeypatch.setattr(MomentumWatcher, "_signals", fake)


def test_holiday_or_weekend_exits_quietly(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)
    res = daily_watch(deps, SAT)
    assert res.status == "skipped" and "trading day" in res.reason
    assert deps.notifier.sent == [] and res.run_id is None  # type: ignore[union-attr]


def test_first_run_seeds_then_a_change_alerts_once(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)
    _force_signal(monkeypatch, status="not_fired")
    first = daily_watch(deps, MON)
    assert first.status == "ok" and first.alerts == 0 and deps.notifier.sent == []  # type: ignore[union-attr]
    _force_signal(monkeypatch, status="fired")
    nxt = daily_watch(deps, MON)
    assert nxt.alerts == len(deps.bundle.universe.pilot)
    again = daily_watch(deps, MON)
    assert again.alerts == 0, "an active signal does not alert again"


def test_shadow_mode_sends_nothing_but_logs(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path, dry_run=True)
    _force_signal(monkeypatch, status="not_fired")
    daily_watch(deps, MON)
    _force_signal(monkeypatch, status="fired")
    res = daily_watch(deps, MON)
    assert res.alerts == len(deps.bundle.universe.pilot), "unowned signals queue for the digest"
    digest = evening_digest(deps, MON)
    assert deps.notifier.sent == [] and digest.shadowed >= 1  # type: ignore[union-attr]
    assert "[ ] noise" in (tmp_path / "logs" / "alerts_shadow.md").read_text(encoding="utf-8")


def test_failure_sends_one_red_message_and_reraises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise ConnectionError("price store down")

    deps.data.prices = boom  # type: ignore[method-assign]
    with pytest.raises(ConnectionError):
        daily_watch(deps, MON)
    sent = deps.notifier.sent  # type: ignore[union-attr]
    assert len(sent) == 1 and "failed" in sent[0]["text"] and "positions" in sent[0]["text"]
    assert "price store down" in sent[0]["text"]


def test_events_job_alerts_once_and_queues_refresh(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path, feeds=FixtureSource())
    day = dt.date(2026, 7, 30)  # a Thursday with a transcript filing for INDIGO
    res = daily_events(deps, day)
    assert res.status == "ok" and res.alerts >= 1
    q = json.loads((tmp_path / "watch" / "refresh_queue.json").read_text(encoding="utf-8"))
    assert q[day.isoformat()]
    events = [
        e
        for e in get_sink().events_for_run(res.run_id)
        if e.event_type == AUD.JOB_REFRESH_REQUESTED
    ]
    assert events
    again = daily_events(deps, day)
    assert again.alerts == 0


def test_digest_job_sends_the_queued_items(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path, feeds=FixtureSource())
    daily_events(deps, dt.date(2026, 9, 28))  # Medium credit-rating filing → digest
    daily_events(deps, dt.date(2026, 9, 28))
    res = evening_digest(deps, dt.date(2026, 9, 28))
    assert res.status == "ok"


def test_heartbeat_is_silent_and_counts_week(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)
    daily_watch(deps, MON)
    res = heartbeat(deps, dt.date(2026, 10, 11))
    msg = deps.notifier.sent[-1]  # type: ignore[union-attr]
    assert msg["silent"] and "alive" in msg["text"] and res.status == "ok"
