"""Watchlist service: decisions, audit trail, agent proposals, repositories (F14, F15.1, F15.2, F25.5)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.services.watchlist import WatchlistError, WatchlistService, default_resolver
from parakh.watch.state import StateStore
from parakh.watchlist.models import Suggestion, WatchlistState
from parakh.watchlist.proposals import LocalProposalStore
from parakh.watchlist.repository import (
    LocalWatchlistRepository,
    SupabaseWatchlistRepository,
)
from tests.helpers.watchlist import TODAY, ctx, entry, fx, top

BUNDLE = load_all()
PILOT = BUNDLE.universe.pilot[0]
OTHER = BUNDLE.universe.pilot[1]


def make(tmp_path):  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path)
    c = ctx()
    svc = WatchlistService(
        LocalWatchlistRepository(store), BUNDLE, c, resolver=default_resolver(BUNDLE),
        proposals=LocalProposalStore(store),
    )  # fmt: skip
    return svc, c


def types(c):  # type: ignore[no-untyped-def]
    return [e.event_type for e in get_sink().events_for_run(c.run_id)]


def seed_suggestion(svc: WatchlistService, action: str = "add_my", isin: str = PILOT.isin) -> str:
    st = svc.repo.load()
    s = Suggestion(
        sugg_id="01SUGGEST000000000000000A", isin=isin, symbol=PILOT.symbol, cap=PILOT.cap,
        action=action, reason="screen winner", created_on=TODAY,  # type: ignore[arg-type]
        expires_on=TODAY + dt.timedelta(days=30),
    )  # fmt: skip
    st.suggestions[s.sugg_id] = s
    svc.repo.save(st)
    return s.sugg_id


@pytest.mark.ac("AC-F15.1")
def test_approve_reject_snooze_update_the_store_and_the_audit_log(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    sid = seed_suggestion(svc)
    res = svc.approve(sid, channel="streamlit", note="waiting for a dip", today=TODAY)
    assert res.ok and res.needs_thesis and res.entry and res.entry.list_kind == "my"
    assert svc.repo.load().suggestions[sid].status == "approved"
    # a second tap on the same card is refused, not applied twice
    assert svc.approve(sid, channel="telegram", today=TODAY).ok is False

    st = svc.repo.load()
    st.suggestions["R2"] = Suggestion(
        sugg_id="R2", isin=OTHER.isin, symbol=OTHER.symbol, cap=OTHER.cap, action="add_my",
        reason="x", created_on=TODAY, expires_on=TODAY + dt.timedelta(days=30),
    )  # fmt: skip
    st.suggestions["S3"] = st.suggestions["R2"].model_copy(update={"sugg_id": "S3"})
    svc.repo.save(st)
    assert svc.reject("R2", channel="telegram", note="too cyclical", today=TODAY).ok
    snooze = svc.snooze("S3", channel="telegram", today=TODAY)
    assert snooze.ok and svc.repo.load().suggestions["S3"].snoozed_until == TODAY + dt.timedelta(
        days=30
    )
    got = types(c)
    assert (
        AUD.WATCHLIST_APPROVED in got
        and AUD.WATCHLIST_REJECTED in got
        and AUD.WATCHLIST_SNOOZED in got
    )
    ev = [e for e in get_sink().events_for_run(c.run_id) if e.event_type == AUD.WATCHLIST_REJECTED][
        0
    ]
    assert ev.channel == "telegram" and ev.reason == "too cyclical" and ev.isin == OTHER.isin


@pytest.mark.ac("AC-F15.2")
def test_adding_needs_a_reason_and_finds_a_stock_by_symbol_or_isin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    with pytest.raises(WatchlistError, match="reason"):
        svc.add_my(PILOT.symbol, reason="  ", channel="streamlit")
    with pytest.raises(WatchlistError, match="not in the universe"):
        svc.add_my("NOSUCH", reason="because", channel="streamlit")
    by_symbol = svc.add_my(
        PILOT.symbol.lower(), reason="waiting for 5% lower", channel="streamlit", today=TODAY
    )
    assert by_symbol.ok and by_symbol.entry.review_on is not None  # type: ignore[union-attr]
    again = svc.add_my(PILOT.isin, reason="again", channel="cli", today=TODAY)
    assert again.ok is False  # already there
    assert AUD.WATCHLIST_MANUAL_ADD in types(c)


def test_manual_add_moves_a_system_entry_instead_of_duplicating(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    f = top(PILOT.symbol, isin=PILOT.isin, cap=PILOT.cap)
    st = WatchlistState(entries={"E": entry(f)})
    svc.repo.save(st)
    svc.add_my(PILOT.symbol, reason="mine now", channel="cli", today=TODAY)
    loaded = svc.repo.load()
    open_ = loaded.open_entries()
    assert [(e.list_kind) for e in open_] == ["my"]  # one open entry per stock
    assert loaded.entries["E"].status == "archived"


def test_removing_from_my_watchlist_is_yours_and_needs_a_reason(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    svc.add_my(PILOT.symbol, reason="r", channel="cli", today=TODAY)
    with pytest.raises(WatchlistError):
        svc.remove_my(PILOT.symbol, reason="", channel="cli")
    assert svc.remove_my(PILOT.symbol, reason="thesis changed", channel="streamlit", today=TODAY).ok
    assert AUD.WATCHLIST_MANUAL_REMOVE in types(c)
    assert svc.repo.load().open_entries() == []  # archived, still in the file for the scorecard
    assert len(svc.repo.load().entries) == 1


def test_promote_moves_the_entry_and_a_remove_suggestion_archives(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    f = top(PILOT.symbol, isin=PILOT.isin, cap=PILOT.cap)
    st = WatchlistState(entries={"E": entry(f)})
    svc.repo.save(st)
    sid = seed_suggestion(svc, "promote")
    res = svc.approve(sid, channel="telegram", today=TODAY)
    assert res.ok and svc.repo.load().entries["E"].list_kind == "my" and res.needs_thesis
    rid = "01REMOVE00000000000000001"
    st = svc.repo.load()
    st.suggestions[rid] = st.suggestions[sid].model_copy(
        update={"sugg_id": rid, "action": "remove_my", "status": "pending"}
    )
    svc.repo.save(st)
    svc.approve(rid, channel="cli", note="done", today=TODAY)
    assert svc.repo.load().entries["E"].status == "archived"


def test_rejecting_a_promotion_counts_toward_the_mute(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    f = top(PILOT.symbol, isin=PILOT.isin, cap=PILOT.cap)
    svc.repo.save(WatchlistState(entries={"E": entry(f)}))
    sid = seed_suggestion(svc, "promote")
    svc.reject(sid, channel="streamlit", today=TODAY)
    e = svc.repo.load().entries["E"]
    assert e.promote_rejections == 1 and e.promote_rejected_sources == e.sources


def test_a_unique_id_prefix_is_enough_for_the_cli_and_telegram(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    sid = seed_suggestion(svc)
    assert svc.approve(sid[:12], channel="cli", today=TODAY).ok
    with pytest.raises(WatchlistError, match="no suggestion"):
        svc.approve("nope", channel="cli")


# -- agent proposals: propose, ingest, never bypass the rules (AC-F25.5, AG-03) ---------------
@pytest.mark.ac("AC-F25.5")
def test_agent_proposal_becomes_a_pending_agent_suggestion_and_changes_no_list(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    p = svc.propose(
        action="add_my", query=PILOT.symbol, reason="Order book up 30% with margin recovery",
        evidence_refs=["parakh://stock/x/report/2026-10"], client="agent:watchlist_curator",
    )  # fmt: skip
    assert (
        svc.repo.load().entries == {} and svc.repo.load().suggestions == {}
    )  # a row, nothing else
    acts = svc.ingest_proposals(today=TODAY)
    st = svc.repo.load()
    s = next(iter(st.suggestions.values()))
    assert [a.kind for a in acts] == ["suggested"]
    assert s.origin == "agent:watchlist_curator" and s.is_agent and s.status == "pending"
    assert st.entries == {}  # My Watchlist changes only on your approval
    assert LocalProposalStore(StateStore(tmp_path)).all()[0].payload["sugg_id"] == s.sugg_id
    suggested = [
        e for e in get_sink().events_for_run(c.run_id) if e.event_type == AUD.WATCHLIST_SUGGESTED
    ]
    assert suggested[0].actor_type == "agent" and suggested[0].actor_id == "watchlist_curator"
    assert p.proposal_id


def test_ingest_drops_proposals_that_break_the_rules(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    svc.add_my(OTHER.symbol, reason="already mine", channel="cli", today=TODAY)
    reason = "a long enough reason to pass"
    svc.propose(
        action="add_my", query=OTHER.symbol, reason=reason, evidence_refs=[], client="agent:c"
    )
    svc.propose(
        action="promote", query=PILOT.symbol, reason=reason, evidence_refs=[], client="agent:c"
    )
    svc.propose(
        action="remove_my", query=PILOT.symbol, reason=reason, evidence_refs=[], client="agent:c"
    )
    svc.ingest_proposals(today=TODAY)
    rows = LocalProposalStore(StateStore(tmp_path)).all()
    assert [r.payload.get("dropped") for r in rows] == [
        "already on My Watchlist",
        "not on the System list",
        "not on My Watchlist",
    ]
    assert svc.repo.load().suggestions == {}


def test_agent_cap_and_dedupe_and_input_validation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, _ = make(tmp_path)
    cap = BUNDLE.watchlist.agent_proposals.max_per_run
    secs = BUNDLE.universe.pilot[: cap + 1]
    for sec in secs:
        svc.propose(action="add_my", query=sec.symbol, reason="a reason that is long enough",
                    evidence_refs=[], client="agent:c")  # fmt: skip
    svc.ingest_proposals(today=TODAY)
    st = svc.repo.load()
    assert len(st.suggestions) == min(cap, len(secs))
    svc.propose(action="add_my", query=secs[0].symbol, reason="same stock again, a long reason",
                evidence_refs=[], client="agent:c")  # fmt: skip
    svc.ingest_proposals(today=TODAY)
    assert len(svc.repo.load().suggestions) == min(cap, len(secs))  # deduped against the open one
    with pytest.raises(WatchlistError, match="reason"):
        svc.propose(
            action="add_my", query=PILOT.symbol, reason="short", evidence_refs=[], client="agent:c"
        )
    with pytest.raises(WatchlistError, match="action"):
        svc.propose(action="delete", query=PILOT.symbol, reason="a reason that is long enough",
                    evidence_refs=[], client="agent:c")  # fmt: skip


def test_monthly_run_audits_every_act_and_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    svc, c = make(tmp_path)
    facts = [top(PILOT.symbol, isin=PILOT.isin, cap=PILOT.cap), top("ZZZ", cap=PILOT.cap)]
    acts = svc.run_monthly(facts, period="2026-10", today=TODAY)
    assert {a.kind for a in acts} == {"added"}
    assert len(svc.repo.load().open_entries()) == 2
    assert types(c).count(AUD.WATCHLIST_AUTO_ADDED) == 2
    # idempotent: the same month again adds nothing
    assert svc.run_monthly(facts, period="2026-10", today=TODAY) == []


# -- repositories -------------------------------------------------------------------------------------
def test_local_repository_round_trips(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = LocalWatchlistRepository(StateStore(tmp_path))
    assert repo.load() == WatchlistState()
    f = fx("RT")
    st = WatchlistState(entries={"E": entry(f)})
    repo.save(st)
    assert repo.load().entries["E"].symbol == "RT"


class FakeTable:
    def __init__(self, db: dict, name: str) -> None:  # type: ignore[type-arg]
        self.db, self.name, self._range = db, name, None

    def select(self, *_a):  # type: ignore[no-untyped-def]
        return self

    def range(self, a, b):  # type: ignore[no-untyped-def]
        self._range = (a, b)
        return self

    def upsert(self, rows, on_conflict=None, ignore_duplicates=False):  # type: ignore[no-untyped-def]
        rows = rows if isinstance(rows, list) else [rows]
        store = self.db.setdefault(self.name, {})
        for r in rows:
            if ignore_duplicates and r[on_conflict] in store:
                continue
            store[r[on_conflict]] = r
        self.db.setdefault("_upserts", []).append((self.name, len(rows)))
        return self

    def execute(self):  # type: ignore[no-untyped-def]
        class R:
            data: Any = None

        r = R()
        if self._range is not None:
            a, b = self._range
            r.data = list(self.db.get(self.name, {}).values())[a : b + 1]
        return r


class FakeClient:
    def __init__(self) -> None:
        self.db: dict = {}  # type: ignore[type-arg]

    def table(self, name: str) -> FakeTable:
        return FakeTable(self.db, name)


def test_supabase_repository_writes_only_what_changed() -> None:
    client = FakeClient()
    repo = SupabaseWatchlistRepository(client)
    f = fx("SB")
    e = entry(f)
    st = repo.load()
    st.entries[e.entry_id] = e
    repo.save(st)
    assert ("watchlist_entries", 1) in client.db["_upserts"]
    client.db["_upserts"].clear()
    st = repo.load()  # a fresh read sees the row
    assert list(st.entries) == [e.entry_id]
    repo.save(st)
    assert client.db["_upserts"] == []  # nothing changed, nothing written
    st.entries[e.entry_id].reason = "edited"
    repo.save(st)
    assert client.db["_upserts"] == [("watchlist_entries", 1)]
