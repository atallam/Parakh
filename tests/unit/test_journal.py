"""Decision journal: capture, review reminders, audit trail (AC-F17.4)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.calibration.journal import JournalError, JournalStore, stats
from parakh.configs import load_all
from parakh.services.journal import JournalService
from parakh.watch.state import StateStore
from tests.helpers.watchlist import TODAY, ctx

BUNDLE = load_all()
SYMBOL = BUNDLE.universe.pilot[0].symbol


def make(tmp_path):  # type: ignore[no-untyped-def]
    c = ctx()
    return JournalService(JournalStore(StateStore(tmp_path)), BUNDLE, c), c


def kinds(c):  # type: ignore[no-untyped-def]
    return [e.event_type for e in get_sink().events_for_run(c.run_id)]


@pytest.mark.ac("AC-F17.4")
def test_an_entry_is_captured_audited_and_due_after_its_review_date(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    e = svc.add(
        SYMBOL, action="buy", reason="order book up", expected="beats index in 6M", today=TODAY
    )
    assert e.review_on > TODAY and e.status == "open"
    assert AUD.JOURNAL_ENTRY in kinds(c)
    assert svc.due(e.review_on - dt.timedelta(days=1)) == []
    assert [d.entry_id for d in svc.due(e.review_on)] == [e.entry_id]


@pytest.mark.ac("AC-F17.4")
def test_reviewing_closes_the_entry_and_it_stops_being_due(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    e = svc.add(
        SYMBOL, action="hold", reason="thesis intact", expected="margins recover", today=TODAY
    )
    done = svc.review(
        e.entry_id, verdict="mixed", note="margins recovered, price did not", today=e.review_on
    )
    assert done.status == "reviewed" and done.verdict == "mixed"
    assert svc.due(e.review_on) == []
    assert AUD.JOURNAL_REVIEWED in kinds(c)
    with pytest.raises(JournalError, match="already reviewed"):
        svc.review(e.entry_id, verdict="right")
    assert svc.stats()["reviewed"] == 1


def test_refusals_are_actionable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    with pytest.raises(JournalError, match="not in the universe"):
        svc.add("NOSUCH", action="buy", reason="r", expected="e", today=TODAY)
    with pytest.raises(JournalError, match="action must be"):
        svc.add(SYMBOL, action="yolo", reason="r", expected="e", today=TODAY)
    with pytest.raises(JournalError, match="empty"):
        svc.add(SYMBOL, action="buy", reason="  ", expected="e", today=TODAY)
    with pytest.raises(JournalError, match="characters"):
        svc.add(SYMBOL, action="buy", reason="x" * 400, expected="e", today=TODAY)
    with pytest.raises(JournalError, match="after today"):
        svc.add(SYMBOL, action="buy", reason="r", expected="e", today=TODAY, review_on=TODAY)


def test_amounts_and_quantities_are_kept_out(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    for bad in ("bought 200 shares at the dip", "put ₹ 50000 in", "added Rs. 2 lakh"):
        with pytest.raises(JournalError, match="amounts"):
            svc.add(SYMBOL, action="buy", reason=bad, expected="up", today=TODAY)


def test_stats_counts_right_rate() -> None:
    assert stats([])["right_pct"] is None


# -- alert feedback service (AC-F17.5) ------------------------------------------------------------
@pytest.mark.ac("AC-F17.5")
def test_feedback_from_streamlit_and_telegram_reach_the_precision_report(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from parakh.calibration.feedback import alert_precision
    from parakh.notify.log import AlertsLog
    from parakh.services.alert_feedback import FeedbackError, record_alert_feedback

    log, c, sink = AlertsLog(tmp_path), ctx(), get_sink()
    for i in range(2):
        log.record(
            {
                "alert_id": f"a{i}",
                "code": "M01",
                "decision": "sent",
                "kind": "signal",
                "isin": "X",
                "asof": "2026-01-01",
            }
        )
    cfg = BUNDLE.calibration.alerts
    record_alert_feedback(log, sink, c, cfg, "a0", useful=True, channel="telegram")
    record_alert_feedback(log, sink, c, cfg, "a1", useful=False, channel="streamlit", tag="late")
    s = alert_precision(log.rows(), cfg)
    assert s.by_channel == {"telegram": 1, "streamlit": 1}
    assert s.signals[0].tags == {"late": 1}
    assert kinds(c).count(AUD.ALERT_FEEDBACK) == 2
    with pytest.raises(FeedbackError, match="reason must be"):
        record_alert_feedback(
            log, sink, c, cfg, "a1", useful=False, channel="streamlit", tag="boring"
        )
    with pytest.raises(FeedbackError, match="no alert"):
        record_alert_feedback(log, sink, c, cfg, "zzz", useful=True, channel="streamlit")
