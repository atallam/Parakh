"""The watchlist rule engine (F14; plan 06 §3–§4). Pure rules over `Facts`; no I/O.

    engine = Engine(cfg.watchlist)
    actions = engine.monthly(state, facts, period="2026-10", today=day, run_id=ctx.run_id)

`monthly` mutates the in-memory `WatchlistState` and returns every change as an `Act`, so the
service layer can persist it and write one audit event per action. Invariants (tested):

- My Watchlist entries are never removed here, only flagged and suggested (AC-F14.1).
- A System list never holds more than its capacity (AC-F14.2).
- A System entry stays at least `min_stay_cycles` months, except for a veto, a cap migration or a
  corporate event (AC-F14.3).
- A candidate enters a full list only if it beats the weakest eligible entry by `bump_margin_points`
  (AC-F14.4); at most `max_per_cap_per_week` urgent adds per cap (AC-F14.5).
- Pending suggestions expire after `expire_after_days` (AC-F14.6); removed entries stay in the
  archive for the scorecard (AC-F14.7).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from parakh.audit.ids import new_ulid
from parakh.configs.watchlist_models import WatchlistConfig
from parakh.watchlist.facts import Facts
from parakh.watchlist.models import (
    FLAG_STALE,
    FLAG_TARGET,
    FLAG_THESIS,
    FLAG_VETO,
    FLAG_WEAK,
    IMMEDIATE_RM,
    RM_BUMPED,
    RM_CAP_MIGRATION,
    RM_CORPORATE,
    RM_FADE,
    RM_SETUP_FAILED,
    RM_VALUE_CLOSED,
    RM_VETO,
    SRC_MOMENTUM,
    SRC_SMART,
    SRC_TOP,
    SRC_VALUE,
    Entry,
    Suggestion,
    WatchEvent,
    WatchlistState,
    months_between,
    period_of,
)

ActKind = str  # added | urgent_add | removed | bumped | flagged | suggested | expired | unsnoozed | owned | missed


@dataclass
class Act:
    """One change the engine made, for the audit trail, the event log and the monthly message."""

    kind: ActKind
    isin: str
    symbol: str
    cap: str
    rule_id: str | None = None
    entry_id: str | None = None
    sugg_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class Engine:
    def __init__(self, cfg: WatchlistConfig) -> None:
        self.cfg = cfg

    # -- sources (plan 06 §3.1) -----------------------------------------------------------------
    def sources_for(self, f: Facts) -> list[str]:
        """The sources that fire for a stock; a vetoed stock has none."""
        if f.vetoes or f.corporate_status:
            return []
        s = self.cfg.sources
        out: list[str] = []
        liquid = f.liquidity_ok or not self.cfg.liquidity_floor_ok_required
        if f.rank_pct <= s.top_combined.top_pct and liquid:
            out.append(SRC_TOP)
        m = s.momentum_setup
        if (
            f.signals & set(m.signals)
            and not f.signals & set(m.blocked_by_signals)
            and f.regime not in m.blocked_regimes
        ):
            out.append(SRC_MOMENTUM)
        v = s.value_zone
        trap = any(t in flag for flag in f.value_flags for t in v.trap_flag_text)
        if (
            f.value_view in v.views
            and (f.quality_subscore or 0) >= v.min_quality_subscore
            and not trap
        ):
            out.append(SRC_VALUE)
        if f.signals & set(s.smart_money.signals) or f.smart_money_hits > 0:
            out.append(SRC_SMART)
        return out

    @staticmethod
    def priority(f: Facts, sources: list[str]) -> tuple[float, float, str]:
        """More agreeing sources first, then the combined score (plan 06 §3.2); symbol breaks ties."""
        return (-len(sources), -f.combined, f.symbol)

    # -- helpers --------------------------------------------------------------------------------
    def capacity(self, cap: str) -> int:
        return self.cfg.system_watchlist.capacity[cap]  # type: ignore[index]

    def _served_min_stay(self, e: Entry, period: str) -> bool:
        return months_between(e.added_period, period) >= self.cfg.system_watchlist.min_stay_cycles

    def _log(
        self,
        state: WatchlistState,
        etype: str,
        isin: str,
        *,
        entry_id: str | None,
        rule_id: str | None,
        run_id: str | None,
        detail: dict[str, Any],
        now: dt.datetime,
    ) -> None:
        state.events.append(
            WatchEvent(
                event_id=new_ulid(),
                entry_id=entry_id,
                isin=isin,
                type=etype,  # type: ignore[arg-type]
                rule_id=rule_id,
                run_id=run_id,
                at=now,
                detail=detail,
            )
        )

    def _archive(self, e: Entry, rule: str, reason: str, today: dt.date) -> None:
        e.status = "archived"
        e.removed_on = today
        e.removal_rule = rule
        e.removal_reason = reason

    def _new_system_entry(
        self, f: Facts, sources: list[str], period: str, today: dt.date, by: str
    ) -> Entry:
        return Entry(
            entry_id=new_ulid(),
            isin=f.isin,
            symbol=f.symbol,
            cap=f.cap,  # type: ignore[arg-type]
            list_kind="system",
            added_on=today,
            added_period=period,
            added_by=by,
            sources=sources,
            reason=", ".join(s.removeprefix("SRC.") for s in sources),
            last_period=period,
            close_at_add=f.close,
        )

    def _make_room(
        self,
        state: WatchlistState,
        f: Facts,
        facts: dict[str, Facts],
        period: str,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> bool:
        """True when the cap's System list has a free slot for `f`, bumping the weakest if allowed."""
        current = [e for e in state.open_entries(cap=f.cap, kind="system") if e.status == "active"]
        if len(current) < self.capacity(f.cap):
            return True
        eligible = [e for e in current if self._served_min_stay(e, period)]
        if not eligible:
            return False

        def score(e: Entry) -> float:
            ef = facts.get(e.isin)
            return ef.combined if ef else -1.0

        weakest = min(eligible, key=lambda e: (score(e), e.symbol))
        if f.combined < score(weakest) + self.cfg.system_watchlist.bump_margin_points:
            return False
        self._archive(weakest, RM_BUMPED, f"displaced by {f.symbol}", today)
        self._log(
            state, "removed", weakest.isin, entry_id=weakest.entry_id, rule_id=RM_BUMPED,
            run_id=run_id, detail={"replaced_by": f.symbol}, now=now,
        )  # fmt: skip
        acts.append(
            Act("bumped", weakest.isin, weakest.symbol, weakest.cap, RM_BUMPED, weakest.entry_id,
                detail={"replaced_by": f.symbol}),
        )  # fmt: skip
        return True

    # -- the monthly review (plan 06 §3.3) ------------------------------------------------------
    def monthly(
        self,
        state: WatchlistState,
        facts: list[Facts],
        *,
        period: str,
        today: dt.date,
        run_id: str | None = None,
        now: dt.datetime | None = None,
    ) -> list[Act]:
        now = now or dt.datetime.now(dt.UTC)
        by_isin = {f.isin: f for f in facts}
        acts: list[Act] = []
        self._expire(state, today, run_id, now, acts)
        self._advance_counters(state, by_isin, period)
        self._ownership(state, by_isin, today, run_id, now, acts)
        self._system_removals(state, by_isin, period, today, run_id, now, acts)
        self._my_flags(state, by_isin, period, today, run_id, now, acts)
        self._additions(state, facts, by_isin, period, today, run_id, now, acts)
        self._promotions(state, by_isin, period, today, run_id, now, acts)
        return acts

    def _expire(
        self,
        state: WatchlistState,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        for s in state.suggestions.values():
            if s.status == "snoozed" and s.snoozed_until and s.snoozed_until <= today:
                s.status, s.snoozed_until = "pending", None
                s.expires_on = today + dt.timedelta(days=self.cfg.suggestions.expire_after_days)
                acts.append(Act("unsnoozed", s.isin, s.symbol, s.cap, sugg_id=s.sugg_id))
            elif s.status == "pending" and s.expires_on < today:
                s.status, s.decided_on = "expired", today
                self._log(state, "expired", s.isin, entry_id=None, rule_id=s.flag, run_id=run_id,
                          detail={"sugg_id": s.sugg_id, "action": s.action}, now=now)  # fmt: skip
                acts.append(Act("expired", s.isin, s.symbol, s.cap, s.flag, sugg_id=s.sugg_id,
                                detail={"action": s.action}))  # fmt: skip

    def _advance_counters(
        self, state: WatchlistState, by_isin: dict[str, Facts], period: str
    ) -> None:
        fade, weak = self.cfg.system_watchlist.fade_rule, self.cfg.my_watchlist.weak_flag
        stay = self.cfg.promotion.stay_top_pct
        for e in state.open_entries():
            f = by_isin.get(e.isin)
            if f is None or e.last_period == period:
                continue  # no data this month, or already counted: counters never double-count
            e.fade_runs = e.fade_runs + 1 if f.rank_pct > fade.outside_top_pct else 0
            e.top_runs = e.top_runs + 1 if f.rank_pct <= stay else 0
            e.weak_runs = e.weak_runs + 1 if f.rank_pct > 100 - weak.bottom_pct else 0
            e.last_period = period

    def _ownership(
        self,
        state: WatchlistState,
        by_isin: dict[str, Facts],
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        for e in state.open_entries():
            f = by_isin.get(e.isin)
            if f is None:
                continue
            if f.owned and e.status == "active":
                e.status = "owned"
                acts.append(Act("owned", e.isin, e.symbol, e.cap, entry_id=e.entry_id))
            elif not f.owned and e.status == "owned":
                e.status = "active"
                if e.list_kind == "my" and not state.open_suggestion(e.isin, "remove_my"):
                    self._suggest(
                        state, e, "remove_my", f"You sold {e.symbol}: keep it on My Watchlist or archive it?",
                        sources=e.sources, flag=None, origin="rule", today=today, run_id=run_id,
                        evidence=self._evidence(f), now=now, acts=acts,
                    )  # fmt: skip

    def _system_removals(
        self,
        state: WatchlistState,
        by_isin: dict[str, Facts],
        period: str,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        fade = self.cfg.system_watchlist.fade_rule
        for e in state.open_entries(kind="system"):
            f = by_isin.get(e.isin)
            if f is None or e.status != "active":
                continue
            rule = self._removal_rule(e, f, fade.consecutive_runs)
            if rule is None:
                continue
            if rule not in IMMEDIATE_RM and not self._served_min_stay(e, period):
                continue  # AC-F14.3: minimum stay, except vetoes and corporate events
            reason = self._removal_reason(rule, f)
            self._archive(e, rule, reason, today)
            etype = "missed" if rule == RM_VALUE_CLOSED else "removed"
            self._log(state, etype, e.isin, entry_id=e.entry_id, rule_id=rule, run_id=run_id,
                      detail={"reason": reason}, now=now)  # fmt: skip
            acts.append(Act("removed", e.isin, e.symbol, e.cap, rule, e.entry_id, detail={"reason": reason}))  # fmt: skip

    def _removal_rule(self, e: Entry, f: Facts, fade_runs: int) -> str | None:
        if f.corporate_status:
            return RM_CORPORATE
        if f.cap != e.cap:
            return RM_CAP_MIGRATION
        if f.vetoes:
            return RM_VETO
        if SRC_MOMENTUM in e.sources and "M21" in f.signals:
            return RM_SETUP_FAILED
        if SRC_VALUE in e.sources and f.value_view == "OVERVALUED":
            return RM_VALUE_CLOSED
        if e.fade_runs >= fade_runs:
            return RM_FADE
        return None

    @staticmethod
    def _removal_reason(rule: str, f: Facts) -> str:
        return {
            RM_CORPORATE: f"corporate event: {f.corporate_status}",
            RM_CAP_MIGRATION: f"moved to the {f.cap} cap",
            RM_VETO: "red-flag veto: " + ", ".join(f.vetoes),
            RM_SETUP_FAILED: "momentum setup failed (200 DMA breakdown, M21)",
            RM_VALUE_CLOSED: "price rose above fair value before you acted",
            RM_FADE: "outside the top of its cap for consecutive runs",
        }.get(rule, rule)

    @staticmethod
    def _evidence(f: Facts) -> dict[str, Any]:
        return {
            "combined": f.combined,
            "value": f.value_score,
            "momentum": f.momentum_score,
            "rank_pct": f.rank_pct,
            "signals": sorted(f.signals),
            "regime": f.regime,
            "vetoes": list(f.vetoes),
            "thesis": f.thesis_status,
        }

    def _suggest(
        self,
        state: WatchlistState,
        e: Entry | None,
        action: str,
        reason: str,
        *,
        sources: list[str],
        flag: str | None,
        origin: str,
        today: dt.date,
        run_id: str | None,
        evidence: dict[str, Any],
        now: dt.datetime,
        acts: list[Act],
        isin: str | None = None,
        symbol: str | None = None,
        cap: str | None = None,
    ) -> Suggestion:
        s = Suggestion(
            sugg_id=new_ulid(),
            isin=e.isin if e else str(isin),
            symbol=e.symbol if e else str(symbol),
            cap=e.cap if e else cap,  # type: ignore[arg-type]
            action=action,  # type: ignore[arg-type]
            sources=sources,
            origin=origin,
            reason=reason,
            evidence=evidence,
            run_id=run_id,
            created_on=today,
            expires_on=today + dt.timedelta(days=self.cfg.suggestions.expire_after_days),
            flag=flag,
        )
        state.suggestions[s.sugg_id] = s
        self._log(state, "suggested", s.isin, entry_id=e.entry_id if e else None, rule_id=flag,
                  run_id=run_id, detail={"sugg_id": s.sugg_id, "action": action, "origin": origin},
                  now=now)  # fmt: skip
        acts.append(Act("suggested", s.isin, s.symbol, s.cap, flag, e.entry_id if e else None,
                        s.sugg_id, {"action": action, "origin": origin}))  # fmt: skip
        return s

    def _my_flags(
        self,
        state: WatchlistState,
        by_isin: dict[str, Facts],
        period: str,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        """Flags only, never a removal: you decide (AC-F14.1)."""
        weak = self.cfg.my_watchlist.weak_flag
        for e in state.open_entries(kind="my"):
            if e.status != "active":
                continue
            f = by_isin.get(e.isin)
            raised: list[tuple[str, str]] = []
            if e.review_on and e.review_on <= today:
                raised.append((FLAG_STALE, f"review date {e.review_on:%d %b %Y} has passed"))
            if f is not None:
                if e.weak_runs >= weak.months and not self._progress(e, f):
                    raised.append((FLAG_WEAK, f"bottom {weak.bottom_pct:g}% of its cap for {weak.months} months"))  # fmt: skip
                if f.vetoes:
                    raised.append((FLAG_VETO, "red-flag veto: " + ", ".join(f.vetoes)))
                if f.thesis_status == "BROKEN":
                    raised.append((FLAG_THESIS, "an exit condition in your thesis was met"))
                if self._target_hit(e, f):
                    raised.append((FLAG_TARGET, "price reached your target entry or the value zone"))  # fmt: skip
            e.flags = [flag for flag, _ in raised]
            for flag, why in raised:
                self._log(state, "flagged", e.isin, entry_id=e.entry_id, rule_id=flag,
                          run_id=run_id, detail={"reason": why}, now=now)  # fmt: skip
                acts.append(Act("flagged", e.isin, e.symbol, e.cap, flag, e.entry_id, detail={"reason": why}))  # fmt: skip
                if flag == FLAG_TARGET:
                    continue  # goes out through the daily watcher, not the monthly review
                if not state.open_suggestion(e.isin, "remove_my"):
                    self._suggest(
                        state, e, "remove_my", why, sources=e.sources, flag=flag, origin="rule",
                        today=today, run_id=run_id,
                        evidence=self._evidence(f) if f else {}, now=now, acts=acts,
                    )  # fmt: skip

    @staticmethod
    def _target_hit(e: Entry, f: Facts) -> bool:
        """Price at or below your target entry, or (with no target set) the value BUY zone."""
        if e.target_entry_inr is not None:
            return f.close is not None and f.close <= e.target_entry_inr
        return f.value_view == "UNDERVALUED"

    @staticmethod
    def _progress(e: Entry, f: Facts) -> bool:
        """Progress toward the target entry price: it is within 10% of it, or there is no target."""
        if e.target_entry_inr is None or f.close is None:
            return False
        return f.close <= e.target_entry_inr * 1.10

    def _additions(
        self,
        state: WatchlistState,
        facts: list[Facts],
        by_isin: dict[str, Facts],
        period: str,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        cands: list[tuple[Facts, list[str]]] = []
        for f in facts:
            if f.owned or state.entry_for(f.isin) is not None:
                continue
            sources = self.sources_for(f)
            if sources:
                cands.append((f, sources))
        cands.sort(key=lambda c: self.priority(c[0], c[1]))
        for f, sources in cands:
            if not self._make_room(state, f, by_isin, period, today, run_id, now, acts):
                continue
            e = self._new_system_entry(f, sources, period, today, "rule")
            state.entries[e.entry_id] = e
            self._log(state, "added", e.isin, entry_id=e.entry_id, rule_id=sources[0], run_id=run_id,
                      detail={"sources": sources, "combined": f.combined}, now=now)  # fmt: skip
            acts.append(Act("added", e.isin, e.symbol, e.cap, sources[0], e.entry_id, detail={"sources": sources}))  # fmt: skip

    def _promotions(
        self,
        state: WatchlistState,
        by_isin: dict[str, Facts],
        period: str,
        today: dt.date,
        run_id: str | None,
        now: dt.datetime,
        acts: list[Act],
    ) -> None:
        p = self.cfg.promotion
        for e in state.open_entries(kind="system"):
            f = by_isin.get(e.isin)
            if f is None or e.status != "active" or state.open_suggestion(e.isin, "promote"):
                continue
            if months_between(e.added_period, period) < p.min_months_on_system:
                continue
            if e.top_runs < p.min_months_on_system:
                continue
            muted = e.promote_rejections >= p.max_rejections_before_mute and set(e.sources) == set(
                e.promote_rejected_sources
            )
            if muted:
                continue
            self._suggest(
                state, e, "promote", f"on the System list {months_between(e.added_period, period)} months, still top {p.stay_top_pct:g}% of its cap",
                sources=e.sources, flag=None, origin="rule", today=today, run_id=run_id,
                evidence=self._evidence(f), now=now, acts=acts,
            )  # fmt: skip

    # -- urgent adds (plan 06 §3.3) -------------------------------------------------------------
    def urgent_add(
        self,
        state: WatchlistState,
        f: Facts,
        fired: set[str],
        *,
        today: dt.date,
        run_id: str | None = None,
        now: dt.datetime | None = None,
        by_isin: dict[str, Facts] | None = None,
    ) -> Act | None:
        """A High-severity setup that fired today goes straight onto the System list (capped weekly)."""
        u = self.cfg.system_watchlist.urgent_adds
        now = now or dt.datetime.now(dt.UTC)
        m = self.cfg.sources.momentum_setup
        hit = fired & set(u.signals)
        if not u.enabled or not hit or f.owned or f.vetoes or f.corporate_status:
            return None
        if f.signals & set(m.blocked_by_signals) or f.regime in m.blocked_regimes:
            return None
        if state.entry_for(f.isin) is not None:
            return None
        week_ago = now - dt.timedelta(days=7)
        used = sum(
            1
            for ev in state.events
            if ev.type == "urgent_add" and ev.at >= week_ago and ev.detail.get("cap") == f.cap
        )
        if used >= u.max_per_cap_per_week:
            return None
        period = period_of(today)
        acts: list[Act] = []
        facts = dict(by_isin or {})
        facts.setdefault(f.isin, f)
        if not self._make_room(state, f, facts, period, today, run_id, now, acts):
            return None
        e = self._new_system_entry(f, [SRC_MOMENTUM], period, today, "rule")
        e.reason = "urgent add: " + ", ".join(sorted(hit))
        state.entries[e.entry_id] = e
        self._log(state, "urgent_add", e.isin, entry_id=e.entry_id, rule_id=sorted(hit)[0],
                  run_id=run_id, detail={"signals": sorted(hit), "cap": f.cap}, now=now)  # fmt: skip
        return Act("urgent_add", e.isin, e.symbol, e.cap, sorted(hit)[0], e.entry_id, detail={"signals": sorted(hit), "bumped": [a.symbol for a in acts]})  # fmt: skip
