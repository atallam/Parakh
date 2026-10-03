"""Phase 3 acceptance: manual re-run, replay, event history, run summary, log search, SLOs, docs."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from parakh.audit.manifest import read_manifest
from parakh.calendar import default_calendar
from parakh.notify.log import AlertsLog
from parakh.orchestration.watch_jobs import (
    daily_events,
    daily_watch,
    evening_digest,
    heartbeat,
    service_level_breaches,
)
from parakh.snapshots.store import stock_dir
from parakh.watch.history import SignalLog
from parakh.watch.replay import render_replay, replay_alerts
from tests.helpers.notify import bundle
from tests.unit.test_event_watcher import FixtureSource
from tests.unit.test_momentum_watcher import D1, D2, D3, _script, _sig, _watcher
from tests.unit.test_watch_jobs import MON, _deps, _force_signal

ROOT = Path(__file__).resolve().parents[2]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@pytest.mark.ac("AC-F11.4")
def test_manual_rerun_for_the_same_date_gives_the_same_messages(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    texts = []
    for name in ("a", "b"):
        deps = _deps(tmp_path / name)
        _force_signal(monkeypatch, status="not_fired")
        daily_watch(deps, MON)
        _force_signal(monkeypatch, status="fired")
        daily_watch(deps, MON)
        evening_digest(deps, MON)
        texts.append([m["text"] for m in deps.notifier.sent])  # type: ignore[union-attr]
    assert texts[0] == texts[1] and texts[0]


@pytest.mark.ac("AC-F11.5")
def test_reports_land_in_the_cap_folders_of_the_repo_tree(tmp_path) -> None:  # type: ignore[no-untyped-def]
    sec = bundle().universe.pilot[0]
    path = stock_dir(sec.cap, sec.symbol, tmp_path)
    assert path.parent.name == f"{sec.cap}_cap" and path.parent.parent == tmp_path


@pytest.mark.ac("AC-F12.7")
def test_replay_lists_dated_alerts_and_sends_nothing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w, _sec = _watcher(tmp_path)
    cal = default_calendar()
    days = {
        d: [_sig("M21", "fired" if d >= D2 else "not_fired")]
        for d in cal.trading_days(D1 - dt.timedelta(days=5), D3)
    }
    _script(w, monkeypatch, days)
    rows = replay_alerts(w, cal, bundle(), D1, D3)
    md = render_replay(rows, D1, D3)
    assert rows and rows[0].day == D2 and "05 Oct 2026" in md and "M21" in md


@pytest.mark.ac("AC-F13.4")
def test_events_are_appended_once_to_the_signal_log(tmp_path) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path, feeds=FixtureSource())
    day = dt.date(2026, 9, 28)
    daily_events(deps, day)
    first = SignalLog(deps.store).rows()
    assert first and all(r["code"] and r["date"] and r["isin"] for r in first)
    daily_events(deps, day)
    assert len(SignalLog(deps.store).rows()) == len(first)


@pytest.mark.ac("AC-F19.1")
def test_run_manifest_carries_timings_counts_and_tokens(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)
    _force_signal(monkeypatch, status="not_fired")
    daily_watch(deps, MON)
    _force_signal(monkeypatch, status="fired")
    daily_watch(deps, MON)
    res = evening_digest(deps, MON)
    m = read_manifest(res.run_id or "")
    assert m is not None and m.status.startswith("SUCCESS")
    assert m.steps and all(s.duration_ms is not None for s in m.steps)
    assert m.alerts_sent >= 1 and m.llm_tokens >= 0 and m.failed_steps == 0


@pytest.mark.ac("AC-F19.3")
def test_search_by_rule_code_returns_run_and_isin(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    deps = _deps(tmp_path)
    _force_signal(monkeypatch, code="M21", status="not_fired")
    daily_watch(deps, MON)
    _force_signal(monkeypatch, code="M21", status="fired")
    daily_watch(deps, MON)
    rows = AlertsLog(deps.store.root / "alerts").search("m21")
    assert rows and all(r["run_id"] and r["isin"] and r["code"] == "M21" for r in rows)
    assert AlertsLog(deps.store.root / "alerts").search("M99") == []


def _late(m, finished_ist: dt.datetime, mode: str):  # type: ignore[no-untyped-def]
    return m.model_copy(update={"mode": mode, "finished_at": finished_ist.astimezone(dt.UTC)})


@pytest.mark.ac("AC-F19.5")
def test_service_level_breaches_are_measured_and_reported_in_the_heartbeat(  # type: ignore[no-untyped-def]
    tmp_path, monkeypatch
) -> None:
    deps = _deps(tmp_path)
    _force_signal(monkeypatch, status="not_fired")
    res = daily_watch(deps, MON)
    base = read_manifest(res.run_id or "")
    assert base is not None
    at = lambda h, mi: dt.datetime(2026, 10, 5, h, mi, tzinfo=IST)  # noqa: E731
    ok = [_late(base, at(19, 20), "watch"), _late(base, at(11, 55), "monthly")]
    bad = [_late(base, at(19, 45), "watch"), _late(base, at(12, 30), "monthly-notify")]
    assert service_level_breaches(deps, ok) == []
    assert len(service_level_breaches(deps, bad)) == 2
    runs_root = tmp_path / "runs"
    (runs_root / "x").mkdir(parents=True)
    (runs_root / "x" / "manifest.json").write_text(bad[0].model_dump_json(), encoding="utf-8")
    heartbeat(deps, dt.date(2026, 10, 11), runs_root)
    assert "⚠️" in deps.notifier.sent[-1]["text"]  # type: ignore[union-attr]


@pytest.mark.ac("AC-F19.7")
def test_failure_modes_entries_are_complete() -> None:
    text = (ROOT / "docs" / "FAILURE_MODES.md").read_text(encoding="utf-8")
    header = next(line for line in text.splitlines() if line.startswith("| #"))
    cols = [c.strip().lower() for c in header.strip("|").split("|")]
    for need in ("detection", "impact", "automatic response", "what you do"):
        assert need in cols
    rows = [line for line in text.splitlines() if re.match(r"\| F\d+ ", line)]
    assert len(rows) >= 15
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        assert len(cells) == len(cols) and all(cells), r


@pytest.mark.ac("AC-F25.7")
def test_every_shipped_agent_has_a_card_and_an_inventory_row() -> None:
    b = bundle()
    models = (ROOT / "docs" / "MODELS.md").read_text(encoding="utf-8")
    shipped = [k for k, a in b.agents.agents.items() if a.enabled and a.first_phase <= 3]
    assert len(shipped) == 2
    for key in shipped:
        name = key.removeprefix("AGENT.")
        card = ROOT / "docs" / "agents" / f"{name}.md"
        assert card.exists() and "Guardrails" in card.read_text(encoding="utf-8")
        assert f"`{key}`" in models


@pytest.mark.ac("AC-F21.1")
def test_every_alert_decision_has_a_log_row_and_an_audit_event(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Audit completeness (plan 09 Phase 3): sent, shadowed, suppressed and failed alerts all leave both."""
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD

    deps = _deps(tmp_path, feeds=FixtureSource())
    _force_signal(monkeypatch, status="not_fired")
    daily_watch(deps, MON)
    _force_signal(monkeypatch, status="fired")
    run_ids = {daily_watch(deps, MON).run_id, daily_events(deps, dt.date(2026, 9, 28)).run_id}
    run_ids.add(evening_digest(deps, MON).run_id)
    daily_events(deps, dt.date(2026, 9, 28))  # a repeat: nothing new, nothing lost
    rows = [r for r in AlertsLog(deps.store.root / "alerts").rows() if r["run_id"] in run_ids]
    events = [e for rid in run_ids for e in get_sink().events_for_run(rid or "")]
    want = {
        "sent": AUD.ALERT_SENT,
        "shadow": AUD.ALERT_SENT,
        "digest_sent": AUD.ALERT_SENT,
        "suppressed": AUD.ALERT_SUPPRESSED,
        "failed": AUD.ALERT_DELIVERY_FAILED,
        "digest_failed": AUD.ALERT_DELIVERY_FAILED,
    }
    decided = [r for r in rows if r["decision"] in want]
    assert len(decided) == sum(1 for e in events if e.event_type in set(want.values())), (
        "every audit alert event has its log row, and the other way round"
    )
