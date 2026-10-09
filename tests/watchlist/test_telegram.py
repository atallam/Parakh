"""Telegram suggestion cards, the bot's decide hook and the queued-tap applier (F15; AC-F15.1)."""

from __future__ import annotations

import datetime as dt

import pytest

from parakh.audit.events import AUD
from parakh.notify import tokens
from parakh.notify.suggestions import render_suggestion_cards
from parakh.orchestration.bot_providers import ReportProviders
from parakh.services.ui_actions import apply_queued
from tests.watchlist.test_service import TODAY, make, seed_suggestion, types

KEY = tokens.derive_key("123:abc")


class MemStore:
    def __init__(self, rows):  # type: ignore[no-untyped-def]
        self.rows = rows

    def queued(self):  # type: ignore[no-untyped-def]
        return [r for r in self.rows if r.get("status", "queued") == "queued"]

    def mark(self, action_id, status, result):  # type: ignore[no-untyped-def]
        for r in self.rows:
            if r["action_id"] == action_id:
                r["status"], r["result"] = status, result


def row(i: str, token: str) -> dict:
    return {"action_id": i, "kind": "button", "payload": token}


@pytest.mark.ac("AC-F15.1")
def test_cards_have_signed_buttons_that_fit_telegram(tmp_path) -> None:
    svc, _ = make(tmp_path)
    sid = seed_suggestion(svc)
    msg = render_suggestion_cards(svc.pending(), max_cards=5)
    assert msg is not None and "waiting" in msg.text
    assert [b.action for b in msg.buttons[0]] == ["a", "r", "s"]
    for b in msg.buttons[0]:
        assert (
            len(tokens.mint(KEY, b.action, b.alert_id, TODAY + dt.timedelta(days=30)).encode())
            <= 64
        )
    assert msg.alert_ids == [sid]
    assert render_suggestion_cards([], max_cards=5) is None


@pytest.mark.ac("AC-F15.1")
def test_a_tap_on_telegram_decides_once_and_a_second_tap_changes_nothing(tmp_path) -> None:
    svc, c = make(tmp_path)
    sid = seed_suggestion(svc)
    p = ReportProviders(watchlist=svc)
    assert "waiting" in p.pending()
    first = p.decide("r", sid)
    assert "reject" in first.lower() or "dismiss" in first.lower() or first
    assert svc.repo.load().suggestions[sid].status == "rejected"
    assert "already" in p.decide("a", sid).lower()
    assert p.pending() == "🗂 Nothing pending."
    assert AUD.WATCHLIST_REJECTED in types(c)


def test_apply_queued_applies_valid_and_refuses_bad_taps(tmp_path) -> None:
    svc, _ = make(tmp_path)
    sid = seed_suggestion(svc)
    day = dt.date.today()
    good = tokens.mint(KEY, "s", sid, day + dt.timedelta(days=5))
    old = tokens.mint(KEY, "a", sid, day - dt.timedelta(days=1))
    forged = good[:-1] + ("0" if good[-1] != "0" else "1")
    store = MemStore([row("1", forged), row("2", old), row("3", good), row("4", good)])
    out = apply_queued(store, svc, KEY, today=day)
    status = {r["action_id"]: r["status"] for r in store.rows}
    assert status["1"] == "rejected" and status["2"] == "rejected"
    assert (
        status["3"] == "applied" and status["4"] == "rejected"
    )  # the repeat finds it already snoozed
    assert out.applied == 1 and out.rejected == 3
    assert svc.repo.load().suggestions[sid].status == "snoozed"
