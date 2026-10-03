"""Dispatcher: shadow mode, suppression audit, Telegram→email fallback, digest (AC-F11, F24)."""

from __future__ import annotations

import datetime as dt

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from tests.helpers.notify import FakeMailer, FakeNotifier, alert, dispatcher


def _events(ctx, kind):  # type: ignore[no-untyped-def]
    return [e for e in get_sink().events_for_run(ctx.run_id) if e.event_type == kind]


def test_live_send_logs_row_and_audit(tmp_path) -> None:  # type: ignore[no-untyped-def]
    d, n, _, log, ctx = dispatcher(tmp_path)
    res = d.submit([alert()])
    assert len(res.sent) == 1 and len(n.sent) == 1
    assert n.sent[0]["buttons"], "action buttons are attached"
    assert [r["decision"] for r in log.rows()] == ["sent"]
    assert len(_events(ctx, AUD.ALERT_SENT)) == 1


def test_shadow_mode_sends_nothing_and_writes_shadow_log(tmp_path) -> None:  # type: ignore[no-untyped-def]
    d, n, _, log, ctx = dispatcher(tmp_path, dry_run_alerts=True)
    res = d.submit([alert()])
    assert n.sent == [] and len(res.shadowed) == 1
    shadow = (tmp_path / "logs" / "alerts_shadow.md").read_text(encoding="utf-8")
    assert "[ ] noise" in shadow and "INDIGO" in shadow
    assert log.rows()[0]["decision"] == "shadow"
    assert _events(ctx, AUD.ALERT_SENT)[0].details["dry_run"] is True


def test_duplicate_is_suppressed_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    d, n, _, log, ctx = dispatcher(tmp_path)
    d.submit([alert()])
    res = d.submit([alert()])
    assert len(res.suppressed) == 1 and len(n.sent) == 1
    assert log.rows()[-1]["decision"] == "suppressed"
    assert len(_events(ctx, AUD.ALERT_SUPPRESSED)) == 1


def test_telegram_failure_falls_back_to_email(tmp_path) -> None:  # type: ignore[no-untyped-def]
    mail = FakeMailer()
    d, n, _, log, ctx = dispatcher(tmp_path, notifier=FakeNotifier(fail=True), mailer=mail)
    res = d.submit([alert()])
    assert len(mail.sent) == 1 and len(res.sent) == 1


def test_total_failure_is_logged_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    d, _, _, log, ctx = dispatcher(tmp_path, notifier=FakeNotifier(fail=True))
    res = d.submit([alert()])
    assert len(res.failed) == 1
    assert log.rows()[0]["decision"] == "failed"
    assert len(_events(ctx, AUD.ALERT_DELIVERY_FAILED)) == 1


def test_batches_of_five(tmp_path) -> None:  # type: ignore[no-untyped-def]
    d, n, *_ = dispatcher(tmp_path)
    alerts = [alert(isin=f"INE00000000{i}", symbol=f"S{i}") for i in range(7)]
    d.submit(alerts)
    assert len(n.sent) == 2


def test_system_message_never_shadowed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from parakh.notify.templates import render_heartbeat

    d, n, *_ = dispatcher(tmp_path, dry_run_alerts=True, dry_run_agents=True)
    d.send_message(render_heartbeat(5, 5, 0, [], dt.date(2026, 10, 5)), code="HEARTBEAT")
    assert len(n.sent) == 1
