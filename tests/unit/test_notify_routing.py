"""Ownership-aware routing, cool-downs, mutes and caps (plan 03 §0; AC-F12.3, AC-F12.4)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.calendar import default_calendar
from parakh.configs import load_all
from parakh.notify.model import Severity
from parakh.notify.routing import AlertState, Router
from parakh.watch.state import StateStore
from tests.helpers.notify import INDIGO, MM, alert

TODAY = dt.date(2026, 10, 5)


@pytest.fixture
def router(tmp_path) -> Router:
    return Router(load_all().notify, default_calendar(), AlertState(StateStore(tmp_path)))


@pytest.mark.ac("AC-F12.4")
@pytest.mark.parametrize(
    ("kwargs", "action"),
    [
        # exit/warning on an owned stock: immediately, whatever the severity
        (dict(owned=True, direction="exit", severity=Severity.HIGH), "send_now"),
        (dict(owned=True, direction="warning", severity=Severity.LOW), "send_now"),
        # entry on a stock you don't own: digest, unless High and top decile
        (dict(owned=False, direction="entry", severity=Severity.HIGH), "digest"),
        (dict(owned=False, direction="entry", severity=Severity.HIGH, top_decile=True), "send_now"),
        (dict(owned=False, direction="entry", severity=Severity.MEDIUM, top_decile=True), "digest"),
        # entry on an owned stock: High immediately, otherwise the digest
        (dict(owned=True, direction="entry", severity=Severity.HIGH), "send_now"),
        (dict(owned=True, direction="entry", severity=Severity.MEDIUM), "digest"),
        # exit/warning on a stock you don't own: nothing to act on
        (dict(owned=False, direction="exit", severity=Severity.HIGH), "digest"),
    ],
)
def test_signal_routing_matrix(router, kwargs, action) -> None:
    assert router.decide(alert(**kwargs), TODAY).action == action


def test_events_thesis_and_system_routing(router) -> None:
    assert (
        router.decide(alert("E04", kind="event", severity=Severity.HIGH, owned=False), TODAY).action
        == "send_now"
    )
    assert (
        router.decide(alert("E01", kind="event", severity=Severity.MEDIUM), TODAY).action
        == "digest"
    )
    assert (
        router.decide(alert("THESIS.BROKEN", kind="thesis", owned=True), TODAY).action == "send_now"
    )
    assert (
        router.decide(alert("THESIS.WATCH", kind="thesis", owned=False), TODAY).action == "digest"
    )
    assert router.decide(alert("SYS.X", kind="system"), TODAY).action == "send_now"


@pytest.mark.ac("AC-F12.3")
def test_same_signal_is_suppressed_inside_the_cooldown_and_rearms_on_reversal(router) -> None:
    first = alert("M21", asof=TODAY)
    d = router.decide(first, TODAY)
    router.commit(first, d, TODAY)
    # 10 trading days later is outside the cool-down (5 Oct + 10 sessions, with 20 Oct a holiday)
    inside = TODAY + dt.timedelta(days=7)  # 12 Oct: 5 trading days
    s = router.decide(alert("M21", asof=inside), inside)
    assert s.action == "suppress" and "cool-down" in s.reason
    router.state.rearm(INDIGO, "M21")  # the signal reversed: it may fire again at once
    assert router.decide(alert("M21", asof=inside, group="x"), inside).action == "send_now"
    outside = dt.date(2026, 10, 22)  # 11 trading days after 5 Oct
    router.state.mark_sent(first, TODAY)
    assert router.decide(alert("M21", asof=outside, group="y"), outside).action == "send_now"


def test_other_stocks_have_their_own_cooldown(router) -> None:
    a = alert("M21")
    router.commit(a, router.decide(a, TODAY), TODAY)
    other = alert("M21", isin=MM, symbol="M&M")
    assert router.decide(other, TODAY).action == "send_now"


@pytest.mark.ac("AC-F24.8")
def test_the_same_event_queued_twice_is_a_duplicate(router) -> None:
    ev = alert("E04", kind="event", group="1234", severity=Severity.HIGH)
    router.commit(ev, router.decide(ev, TODAY), TODAY)
    again = router.decide(alert("E04", kind="event", group="1234", severity=Severity.HIGH), TODAY)
    assert again.action == "suppress" and "duplicate" in again.reason
    other = alert("E04", kind="event", group="9999", severity=Severity.HIGH)
    assert router.decide(other, TODAY).action == "send_now"


def test_mute_applies_to_one_signal_on_one_stock_until_it_expires(router) -> None:
    router.state.mute(INDIGO, "M21", TODAY + dt.timedelta(days=10))
    assert router.decide(alert("M21"), TODAY).action == "suppress"
    assert router.decide(alert("M20"), TODAY).action == "send_now"
    assert router.decide(alert("M21", isin=MM, symbol="M&M"), TODAY).action == "send_now"
    later = TODAY + dt.timedelta(days=11)
    assert router.decide(alert("M21"), later).action == "send_now"


def test_agent_daily_cap(router) -> None:
    cap = router.config.routing.agent_daily_cap
    for i in range(cap):
        a = alert(
            "E13", kind="event", source="agent:event_triage", group=str(i), severity=Severity.HIGH
        )
        d = router.decide(a, TODAY)
        assert d.action == "send_now"
        router.commit(a, d, TODAY)
    over = alert(
        "E13", kind="event", source="agent:event_triage", group="over", severity=Severity.HIGH
    )
    s = router.decide(over, TODAY)
    assert s.action == "suppress" and "daily cap" in s.reason
