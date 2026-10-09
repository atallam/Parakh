"""Watchlist rule engine: sources, capacity, minimum stay, bumping, removals, flags (F14; AC-F14.1–7)."""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

import pytest

from parakh.watchlist.engine import Engine
from parakh.watchlist.facts import Facts
from parakh.watchlist.models import (
    FLAG_STALE,
    FLAG_THESIS,
    FLAG_VETO,
    RM_BUMPED,
    RM_FADE,
    RM_SETUP_FAILED,
    RM_VALUE_CLOSED,
    RM_VETO,
    SRC_MOMENTUM,
    SRC_SMART,
    SRC_TOP,
    SRC_VALUE,
    Suggestion,
    WatchlistState,
)
from tests.helpers.watchlist import PERIOD, TODAY, cfg, entry, fx, state_with, top


def engine() -> Engine:
    return Engine(cfg())


def run(state: WatchlistState, facts: list[Facts], period: str = PERIOD, today: dt.date = TODAY):
    return engine().monthly(state, facts, period=period, today=today, run_id="R1")


# -- sources (plan 06 §3.1) --------------------------------------------------------------------
def test_top_combined_needs_top_ten_percent_no_veto_and_liquidity() -> None:
    e = engine()
    assert e.sources_for(top("A")) == [SRC_TOP]
    assert e.sources_for(fx("B", rank_pct=11.0)) == []
    assert e.sources_for(top("C", vetoes=("RULE.value.negative_cfo",))) == []
    assert e.sources_for(top("D", liquidity_ok=False)) == []


def test_momentum_setup_guards() -> None:
    e = engine()
    base: dict[str, Any] = {"rank_pct": 50.0}
    assert e.sources_for(fx("A", signals=frozenset({"M03"}), **base)) == [SRC_MOMENTUM]
    assert e.sources_for(fx("B", signals=frozenset({"M03", "M24"}), **base)) == []  # over-extended
    assert e.sources_for(fx("C", signals=frozenset({"M03", "M27"}), **base)) == []  # circuit trap
    assert e.sources_for(fx("D", signals=frozenset({"M03"}), regime="Risk-Off", **base)) == []
    assert e.sources_for(fx("E", signals=frozenset({"M21"}), **base)) == []  # not a setup signal


def test_value_zone_needs_quality_and_no_trap_flag() -> None:
    e = engine()
    ok = fx("A", value_view="UNDERVALUED", quality_subscore=0.7)
    assert e.sources_for(ok) == [SRC_VALUE]
    assert e.sources_for(fx("B", value_view="UNDERVALUED", quality_subscore=0.5)) == []
    trap = fx(
        "C", value_view="UNDERVALUED", quality_subscore=0.8, value_flags=("possible value trap",)
    )
    assert e.sources_for(trap) == []
    assert e.sources_for(fx("D", value_view="FAIR", quality_subscore=0.9)) == []


def test_smart_money_from_signal_or_event_history() -> None:
    e = engine()
    assert e.sources_for(fx("A", signals=frozenset({"M29"}))) == [SRC_SMART]
    assert e.sources_for(fx("B", smart_money_hits=1)) == [SRC_SMART]


def test_agreeing_sources_outrank_a_higher_score() -> None:
    e = engine()
    two = fx("TWO", combined=70.0, rank_pct=5.0, value_view="UNDERVALUED", quality_subscore=0.8)
    one = top("ONE", combined=90.0)
    a, b = e.sources_for(two), e.sources_for(one)
    assert len(a) == 2 and len(b) == 1
    assert e.priority(two, a) < e.priority(one, b)  # sorted ascending: TWO first


# -- additions, capacity, one-in-one-out ---------------------------------------------------------
@pytest.mark.ac("AC-F14.2")
def test_system_list_never_exceeds_capacity() -> None:
    cap = cfg().system_watchlist.capacity["large"]
    facts = [top(f"S{i}", cap="large", combined=95 - i) for i in range(cap + 6)]
    state = WatchlistState()
    run(state, facts)
    assert len(state.open_entries(cap="large", kind="system")) == cap
    names = {e.symbol for e in state.open_entries(cap="large")}
    assert names == {f"S{i}" for i in range(cap)}  # best first


@pytest.mark.ac("AC-F14.4")
def test_newcomer_must_beat_the_weakest_by_the_margin() -> None:
    cap = "large"
    n = cfg().system_watchlist.capacity[cap]
    margin = cfg().system_watchlist.bump_margin_points
    have = [top(f"H{i}", cap=cap, combined=70.0 + i) for i in range(n)]
    state = state_with(*[entry(f, added_period="2026-06") for f in have])
    weakest = 70.0
    close = top("NEW", cap=cap, combined=weakest + margin - 0.5)
    run(state, have + [close])
    assert state.entry_for(close.isin) is None  # not enough
    better = top("NEW2", cap=cap, combined=weakest + margin)
    acts = run(state, have + [better])
    assert state.entry_for(better.isin) is not None
    assert [a.rule_id for a in acts if a.kind == "bumped"] == [RM_BUMPED]
    assert state.entry_for(have[0].isin) is None  # the weakest left
    archived = [e for e in state.entries.values() if e.status == "archived"]
    assert archived and archived[0].removal_rule == RM_BUMPED  # AC-F14.7: kept in the archive


@pytest.mark.ac("AC-F14.3")
def test_minimum_stay_blocks_a_bump_and_a_fade() -> None:
    cap = "large"
    n = cfg().system_watchlist.capacity[cap]
    fresh = [top(f"H{i}", cap=cap, combined=60.0) for i in range(n)]
    state = state_with(*[entry(f, added_period=PERIOD) for f in fresh])  # added this month
    run(state, fresh + [top("NEW", cap=cap, combined=99.0)])
    assert state.entry_for(top("NEW", cap=cap).isin) is None  # nobody has served the stay
    # a fading entry inside its stay stays too
    f = fx("FADER", rank_pct=90.0)
    st = state_with(entry(f, added_period=PERIOD, fade_runs=5, last_period=PERIOD))
    run(st, [f])
    assert st.entry_for(f.isin) is not None


@pytest.mark.ac("AC-F14.3")
def test_veto_removes_at_once_even_inside_the_stay() -> None:
    f = top("V", vetoes=("RULE.value.negative_cfo",))
    st = state_with(entry(f, added_period=PERIOD))
    acts = run(st, [f])
    assert st.entry_for(f.isin) is None
    assert [(a.kind, a.rule_id) for a in acts if a.kind == "removed"] == [("removed", RM_VETO)]


def test_fade_after_three_runs_outside_the_top_twenty() -> None:
    f = fx("FADE", rank_pct=40.0)
    st = state_with(entry(f, added_period="2026-06"))
    for period in ("2026-08", "2026-09"):
        run(st, [f], period=period)
        assert st.entry_for(f.isin) is not None
    acts = run(st, [f], period="2026-10")
    assert any(a.rule_id == RM_FADE for a in acts)
    assert st.entry_for(f.isin) is None


def test_counters_do_not_double_count_within_a_period() -> None:
    f = fx("ONCE", rank_pct=40.0)
    e = entry(f, added_period="2026-06")
    st = state_with(e)
    run(st, [f])
    run(st, [f])  # a re-run of the same month
    assert e.fade_runs == 1


def test_setup_failed_and_value_closed() -> None:
    m = fx("MOM", rank_pct=5.0, signals=frozenset({"M21"}))
    v = fx("VAL", rank_pct=5.0, value_view="OVERVALUED")
    st = state_with(
        entry(m, sources=[SRC_MOMENTUM]), entry(v, sources=[SRC_VALUE]),
    )  # fmt: skip
    acts = run(st, [m, v])
    rules = {a.symbol: a.rule_id for a in acts if a.kind == "removed"}
    assert rules == {"MOM": RM_SETUP_FAILED, "VAL": RM_VALUE_CLOSED}
    assert any(ev.type == "missed" for ev in st.events)  # a missed opportunity is recorded


# -- My Watchlist: flags only (AC-F14.1) -------------------------------------------------------
@pytest.mark.ac("AC-F14.1")
def test_my_watchlist_is_flagged_never_removed() -> None:
    f = fx("MINE", rank_pct=95.0, vetoes=("RULE.value.negative_cfo",), thesis_status="BROKEN")
    e = entry(f, kind="my", review_on=dt.date(2026, 1, 1), weak_runs=9, last_period="2026-10")
    st = state_with(e)
    acts = run(st, [f])
    assert e.status == "active"
    assert set(e.flags) >= {FLAG_STALE, FLAG_VETO, FLAG_THESIS}
    sugg = st.pending()
    assert len(sugg) == 1 and sugg[0].action == "remove_my"  # one suggestion, not three
    assert not any(a.kind == "removed" for a in acts)


@pytest.mark.ac("AC-F14.1")
def test_invariant_holds_over_random_months() -> None:
    rng = random.Random(14)
    names = [f"R{i}" for i in range(30)]
    mine = [fx(n, cap="mid", rank_pct=50.0) for n in names[:8]]
    st = state_with(*[entry(f, kind="my", added_period="2026-01") for f in mine])
    ids = {e.entry_id for e in st.entries.values()}
    for month in range(1, 10):
        facts = [
            fx(
                n, cap=rng.choice(["large", "mid", "small"]), combined=rng.uniform(0, 100),
                rank_pct=rng.uniform(1, 100),
                vetoes=("V",) if rng.random() < 0.2 else (),
                signals=frozenset(rng.sample(["M01", "M02", "M03", "M21", "M24"], 2)),
                thesis_status=rng.choice(["INTACT", "BROKEN"]),
                corporate_status=rng.choice([None, None, None, "delisted"]),
                owned=rng.random() < 0.1,
            )
            for n in names
        ]  # fmt: skip
        period = f"2026-{month + 1:02d}"
        engine().monthly(st, facts, period=period, today=dt.date(2026, month + 1, 28))
        for eid in ids:
            e = st.entries[eid]
            assert e.status != "archived" and e.list_kind == "my"
        for cap in ("large", "mid", "small"):
            assert (
                len([x for x in st.open_entries(cap=cap, kind="system") if x.status == "active"])
                <= cfg().system_watchlist.capacity[cap]
            )  # AC-F14.2 under churn


def test_target_hit_is_a_flag_not_a_suggestion() -> None:
    f = fx("TGT", close=95.0)
    e = entry(f, kind="my", target_entry_inr=100.0, review_on=dt.date(2027, 3, 1))
    st = state_with(e)
    run(st, [f])
    assert "FLAG.target_hit" in e.flags
    assert st.pending() == []  # it goes out through the daily watcher


# -- promotion (plan 06 §4.3) ----------------------------------------------------------------------
def test_promotion_after_three_months_in_the_top_twenty_and_mute_after_two_rejections() -> None:
    f = top("PROMO", rank_pct=8.0)
    e = entry(f, added_period="2026-07", top_runs=3, last_period="2026-09")
    st = state_with(e)
    run(st, [f])
    s = st.pending()
    assert len(s) == 1 and s[0].action == "promote"
    s[0].status = "rejected"
    e.promote_rejections = 2
    e.promote_rejected_sources = list(e.sources)
    run(st, [f], period="2026-11", today=dt.date(2026, 11, 28))
    assert st.pending() == []  # muted until the sources change
    e.sources = [SRC_TOP, SRC_VALUE]
    run(st, [f], period="2026-12", today=dt.date(2026, 12, 28))
    assert len(st.pending()) == 1


# -- expiry and snooze (AC-F14.6) --------------------------------------------------------------------
@pytest.mark.ac("AC-F14.6")
def test_pending_suggestions_expire_after_thirty_days_and_snooze_returns() -> None:
    created = dt.date(2026, 9, 1)

    def sugg(sid: str, **kw: object) -> Suggestion:
        return Suggestion(
            sugg_id=sid, isin="INE000000001", symbol=sid, cap="mid", action="add_my", reason="r",
            created_on=created, expires_on=created + dt.timedelta(days=30), **kw,  # type: ignore[arg-type]
        )  # fmt: skip

    st = WatchlistState()
    st.suggestions = {
        "old": sugg("old"),
        "snz": sugg("snz", status="snoozed", snoozed_until=dt.date(2026, 10, 20)),
    }
    acts = run(st, [], today=TODAY)
    assert st.suggestions["old"].status == "expired"
    assert st.suggestions["snz"].status == "pending"
    assert st.suggestions["snz"].expires_on > TODAY
    assert {a.kind for a in acts} == {"expired", "unsnoozed"}


# -- urgent adds (AC-F14.5) ----------------------------------------------------------------------------
@pytest.mark.ac("AC-F14.5")
def test_urgent_adds_are_capped_per_cap_per_week() -> None:
    st = WatchlistState()
    e = engine()
    now = dt.datetime(2026, 10, 27, 12, tzinfo=dt.UTC)
    added = []
    for i in range(5):
        f = fx(f"U{i}", cap="small", rank_pct=30.0, signals=frozenset({"M03"}))
        act = e.urgent_add(st, f, {"M03"}, today=dt.date(2026, 10, 27), now=now)
        added.append(act is not None)
    assert added == [True, True, True, False, False]
    # another cap is unaffected, and a week later the allowance is back
    other = fx("OTHER", cap="mid", signals=frozenset({"M03"}))
    assert e.urgent_add(st, other, {"M03"}, today=dt.date(2026, 10, 27), now=now) is not None
    later = fx("LATER", cap="small", signals=frozenset({"M03"}))
    assert (
        e.urgent_add(st, later, {"M03"}, today=dt.date(2026, 11, 4), now=now + dt.timedelta(days=8))
        is not None
    )


def test_urgent_add_respects_guards_and_signal_list() -> None:
    st = WatchlistState()
    e = engine()
    f = fx("G", signals=frozenset({"M03", "M24"}))
    assert e.urgent_add(st, f, {"M03"}, today=TODAY) is None  # over-extended
    assert e.urgent_add(st, fx("H"), {"M21"}, today=TODAY) is None  # not an urgent signal
    assert e.urgent_add(st, fx("I", owned=True), {"M03"}, today=TODAY) is None  # owned


def test_owned_status_and_sell_back_prompt() -> None:
    f = fx("OWN", owned=True)
    e = entry(f, kind="my", review_on=dt.date(2027, 5, 1))
    st = state_with(e)
    run(st, [f])
    assert e.status == "owned"
    sold = fx("OWN", owned=False, isin=f.isin)
    run(st, [sold], period="2026-11", today=dt.date(2026, 11, 28))
    assert e.status == "active"
    assert [s.action for s in st.pending()] == ["remove_my"]  # keep on My Watchlist or archive?
