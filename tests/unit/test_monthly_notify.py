"""Monthly summary, email and calendar (AC-F11.1, F11.2, F11.7, F11.11, F25.3)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from parakh.notify.monthly import build_monthly_vars, calendar_entries
from parakh.orchestration.analysis import run_monthly
from parakh.orchestration.monthly_notify import notify_monthly
from parakh.orchestration.watch_jobs import WatchDeps
from parakh.watch.state import StateStore
from tests.helpers.notify import FakeMailer, FakeNotifier, bundle
from tests.helpers.pilot import pilot_data

FIX = Path(__file__).parent.parent / "fixtures" / "sources" / "nse"
ASOF = dt.date(2026, 9, 30)


def _result(tmp_path):  # type: ignore[no-untyped-def]
    b = bundle()
    data = pilot_data(b, end=ASOF)
    res = run_monthly(b, data, ASOF, out_root=tmp_path / "out")
    snaps = [s.snapshot.model_dump(mode="json") for s in res.stocks if s.snapshot]
    return b, data, res, snaps


def _deps(b, data, tmp_path, notifier=None, mailer=None):  # type: ignore[no-untyped-def]
    return WatchDeps(
        b,
        data,
        StateStore(tmp_path / "w"),
        notifier or FakeNotifier(),
        mailer,
        logs_root=tmp_path / "logs",
    )


def test_summary_is_one_short_message_without_amounts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b, data, res, snaps = _result(tmp_path)
    n, m = FakeNotifier(), FakeMailer()
    notice = notify_monthly(
        _deps(b, data, tmp_path, n, m),
        snaps,
        {c: r.regime for c, r in res.regimes.items()},
        312.0,
        asof=ASOF,
        review_pending=True,
    )
    assert notice.telegram_ok and len(n.sent) == 1
    text = n.sent[0]["text"]
    assert (
        len(text.splitlines()) <= 10 and "Monthly Analysis" in text and "Review pending" not in text
    )
    assert "₹" not in text and "Rs" not in text


def test_email_has_html_text_and_ics_attachment(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b, data, res, snaps = _result(tmp_path)
    m = FakeMailer()

    class Cal:
        def event_calendar(self, s):  # type: ignore[no-untyped-def]
            return [{"purpose": "Financial Results", "date": "05-Oct-2026", "bm_desc": "Q2"}]

        def board_meetings(self, s):  # type: ignore[no-untyped-def]
            return []

        def corporate_actions(self, s):  # type: ignore[no-untyped-def]
            return [{"exDate": "12-Oct-2026", "subject": "Dividend - Rs 5 Per Share"}]

    notice = notify_monthly(
        _deps(b, data, tmp_path, None, m),
        snaps,
        {},
        10.0,
        asof=ASOF,
        calendar_source=Cal(),
        today=ASOF,
    )
    assert notice.email_ok and notice.calendar_entries == 2 * len(b.universe.pilot)
    sent = m.sent[0]
    assert sent["att"][0][0].endswith(".ics") and b"BEGIN:VEVENT" in sent["att"][0][1]
    assert "Monthly analysis" in sent["html"] and sent["text"]


def test_calendar_window_and_errors() -> None:
    b = bundle()
    secs = b.universe.pilot[:2]
    today = dt.date(2026, 10, 1)

    class Cal:
        def event_calendar(self, s):  # type: ignore[no-untyped-def]
            if s == secs[1].symbol:
                raise TimeoutError("x")
            return [
                {"purpose": "Financial Results", "date": "20-Oct-2026"},
                {"purpose": "Dividend", "date": "20-Dec-2026"},
            ]

        def board_meetings(self, s):  # type: ignore[no-untyped-def]
            return []

        def corporate_actions(self, s):  # type: ignore[no-untyped-def]
            return []

    entries, errs = calendar_entries(Cal(), secs, today)
    assert len(entries) == 1 and entries[0].kind == "results" and secs[1].symbol in errs


def test_vars_classify_upgrades_and_downgrades() -> None:
    b = bundle()
    snap = lambda sym, prev, new, owned: {  # noqa: E731
        "symbol": sym,
        "period": "2026-09",
        "verdict": {
            "changed": True,
            "prev_verdict": prev,
            "verdict": new,
            "owned": owned,
            "prev_action": "HOLD",
            "action": "ADD",
        },
        "checks": [{"state": "FLAGGED", "name": "pledge"}] if sym == "B" else [],
        "data_quality": {},
    }
    v = build_monthly_vars(
        b, [snap("A", "HOLD", "BUY", True), snap("B", "BUY", "AVOID", False)], {}, 5.0
    )
    assert v.upgrades == ["A HOLD→BUY"] and v.downgrades == ["B BUY→AVOID"]
    assert (
        v.owned_attention == ["A HOLD→ADD"]
        and v.red_flags == ["B: pledge"]
        and v.period == "Sep 2026"
    )


def _fake_review_deps(b, data, tmp_path, notifier, mailer, final, dry_run_agents):  # type: ignore[no-untyped-def]
    import dataclasses

    from parakh.mcp.middleware import Gateway
    from tests.fakes.agent_runner import FakeRunner, Trajectory, Turn

    b = bundle(dry_run_agents=dry_run_agents)
    deps = _deps(b, data, tmp_path, notifier, mailer)

    class R(FakeRunner):
        async def run(self, spec, task, ctx):  # type: ignore[no-untyped-def]
            self.trajectories = {
                task.task_id: Trajectory([Turn("mcp__parakh__reports_what_changed")], final)
            }
            return await super().run(spec, task, ctx)

    deps.runner = R(Gateway.for_client("agent:monthly_reviewer"), {})
    return dataclasses.replace(deps, bundle=b)


def test_review_live_sends_second_message_and_email_section(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b, data, res, snaps = _result(tmp_path)
    sym = snaps[0]["symbol"]
    final = {
        "items": [{"symbol": sym, "tag": "watch", "note": "Momentum faded this month"}],
        "narrative": f"{sym} lost momentum.",
    }
    n, m = FakeNotifier(), FakeMailer()
    deps = _fake_review_deps(b, data, tmp_path, n, m, final, dry_run_agents=False)
    notice = notify_monthly(deps, snaps, {}, 5.0, asof=ASOF, allowed_symbols={sym})
    assert notice.review_status == "ok" and len(n.sent) == 2
    assert "Review pending" in n.sent[0]["text"] and "Monthly review" in n.sent[1]["text"]
    assert f"{sym} lost momentum." in m.sent[0]["html"]


def test_review_in_shadow_goes_to_the_log_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b, data, res, snaps = _result(tmp_path)
    sym = snaps[0]["symbol"]
    final = {
        "items": [{"symbol": sym, "tag": "info", "note": "Steady"}],
        "narrative": f"{sym} steady.",
    }
    n, m = FakeNotifier(), FakeMailer()
    deps = _fake_review_deps(b, data, tmp_path, n, m, final, dry_run_agents=True)
    notify_monthly(deps, snaps, {}, 5.0, asof=ASOF, allowed_symbols={sym})
    assert len(n.sent) == 1, "only the summary; the review stays in the shadow log"
    shadow = (tmp_path / "logs" / "agents_shadow.md").read_text(encoding="utf-8")
    assert "monthly_reviewer" in shadow and "noise" in shadow
    assert f"{sym} steady." not in m.sent[0]["html"]


def test_failed_review_leaves_the_summary_and_marks_pending(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b, data, res, snaps = _result(tmp_path)
    sym = snaps[0]["symbol"]
    final = {"items": [{"symbol": "NOTLISTED", "tag": "info", "note": "x"}], "narrative": "x"}
    n, m = FakeNotifier(), FakeMailer()
    deps = _fake_review_deps(b, data, tmp_path, n, m, final, dry_run_agents=False)
    notice = notify_monthly(deps, snaps, {}, 5.0, asof=ASOF, allowed_symbols={sym})
    assert notice.review_status == "pending" and len(n.sent) == 1
    assert "Review pending" in n.sent[0]["text"] and "Review pending" in m.sent[0]["html"]
