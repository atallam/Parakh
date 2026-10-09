"""The watchlist service: the one place lists change (ADR-006; plan 06 §5).

Streamlit, the Telegram listener, the CLI and the monthly job all call this module, so a decision made
on a phone and one made at a desk go through the same code and leave the same audit trail
(`AUD.WATCHLIST.*`, with the channel). Agents never call it: they write proposals (AG-03), and
`ingest_proposals` turns the valid ones into pending suggestions.

    svc = WatchlistService(repo, bundle, ctx)
    svc.approve(sugg_id, channel="streamlit", note="…")
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD, Channel
from parakh.audit.ids import new_ulid
from parakh.configs import ConfigBundle
from parakh.watchlist.engine import Act, Engine
from parakh.watchlist.facts import Facts
from parakh.watchlist.models import (
    Action,
    Entry,
    Suggestion,
    WatchEvent,
    WatchlistState,
    months_between,
    period_of,
)
from parakh.watchlist.proposals import LocalProposalStore, Proposal
from parakh.watchlist.repository import WatchlistRepository

SecurityRef = tuple[str, str, str]  # (isin, symbol, cap)
Resolver = Callable[[str], SecurityRef | None]

ACT_AUDIT: dict[str, AUD] = {
    "added": AUD.WATCHLIST_AUTO_ADDED,
    "urgent_add": AUD.WATCHLIST_AUTO_ADDED,
    "removed": AUD.WATCHLIST_AUTO_REMOVED,
    "bumped": AUD.WATCHLIST_AUTO_REMOVED,
    "suggested": AUD.WATCHLIST_SUGGESTED,
    "expired": AUD.WATCHLIST_EXPIRED,
    "flagged": AUD.WATCHLIST_FLAGGED,
}


class WatchlistError(ValueError):
    """A refusal with a reason a person can act on (UX-10)."""


@dataclass
class Decision:
    ok: bool
    message: str
    suggestion: Suggestion | None = None
    entry: Entry | None = None
    needs_thesis: bool = False


def default_resolver(bundle: ConfigBundle) -> Resolver:
    """Look up a symbol or ISIN in the configured universe (pilot now; wider modes extend it)."""

    def resolve(query: str) -> SecurityRef | None:
        q = query.strip().upper()
        for sec in bundle.universe.active:
            if q in (sec.isin.upper(), sec.symbol.upper()):
                return sec.isin, sec.symbol, sec.cap
        return None

    return resolve


class WatchlistService:
    def __init__(
        self,
        repo: WatchlistRepository,
        bundle: ConfigBundle,
        ctx: RunContext,
        *,
        sink: AuditSink | None = None,
        resolver: Resolver | None = None,
        proposals: LocalProposalStore | None = None,
    ) -> None:
        self.repo, self.bundle, self.ctx = repo, bundle, ctx
        self.sink = sink or get_sink()
        self.resolve = resolver or default_resolver(bundle)
        self.proposals = proposals or LocalProposalStore()
        self.engine = Engine(bundle.watchlist)

    # -- audit ----------------------------------------------------------------------------------
    def _emit(
        self,
        event: AUD,
        *,
        entity_type: str,
        entity_id: str,
        isin: str | None,
        channel: Channel | None = None,
        reason: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
        agent: str | None = None,
    ) -> None:
        ctx = (
            dataclasses.replace(self.ctx, actor_type="agent", actor_id=agent) if agent else self.ctx
        )
        self.sink.emit(
            ctx,
            event,
            channel=channel,
            entity_type=entity_type,
            entity_id=entity_id,
            isin=isin,
            reason=reason,
            before=before,
            after=after,
            details=details,
        )

    def _audit_acts(self, acts: list[Act], state: WatchlistState) -> None:
        for a in acts:
            event = ACT_AUDIT.get(a.kind)
            if event is None:
                continue
            origin = (
                state.suggestions[a.sugg_id].origin if a.sugg_id in state.suggestions else "rule"
            )
            self._emit(
                event,
                entity_type="watchlist_suggestion" if a.sugg_id else "watchlist_entry",
                entity_id=a.sugg_id or a.entry_id or a.isin,
                isin=a.isin,
                channel="cli" if self.ctx.actor_type == "user" else None,
                reason=a.rule_id,
                details={
                    "symbol": a.symbol,
                    "cap": a.cap,
                    "kind": a.kind,
                    "origin": origin,
                    **a.detail,
                },
                agent=origin.removeprefix("agent:") if origin.startswith("agent:") else None,
            )

    # -- monthly and daily jobs -----------------------------------------------------------------
    def run_monthly(self, facts: list[Facts], *, period: str, today: dt.date) -> list[Act]:
        """The monthly review: additions, removals, flags, promotions, expiry. One save, one audit each."""
        state = self.repo.load()
        acts = self.engine.monthly(state, facts, period=period, today=today, run_id=self.ctx.run_id)
        acts += self._ingest(state, today)
        self.repo.save(state)
        self._audit_acts(acts, state)
        return acts

    def urgent_add(
        self, f: Facts, fired: set[str], *, today: dt.date, others: list[Facts] | None = None
    ) -> Act | None:
        state = self.repo.load()
        act = self.engine.urgent_add(
            state, f, fired, today=today, run_id=self.ctx.run_id,
            by_isin={x.isin: x for x in others or []},
        )  # fmt: skip
        if act is not None:
            self.repo.save(state)
            self._audit_acts([act], state)
        return act

    # -- agent proposals (plan 06 §3.1b) --------------------------------------------------------
    def ingest_proposals(self, *, today: dt.date) -> list[Act]:
        state = self.repo.load()
        acts = self._ingest(state, today)
        if acts:
            self.repo.save(state)
            self._audit_acts(acts, state)
        return acts

    def _ingest(self, state: WatchlistState, today: dt.date) -> list[Act]:
        """Valid watchlist proposals become pending 🤖 suggestions; the rest are dropped with a reason."""
        acts: list[Act] = []
        rows = self.proposals.all()
        per_agent: dict[str, int] = {}
        changed = False
        for p in rows:
            if p.kind != "watchlist" or p.status != "pending" or p.payload.get("sugg_id"):
                continue
            changed = True
            reason = self._admit(state, p, per_agent, today)
            if reason is not None:
                p.status, p.decided_by, p.decided_at = "rejected", "system", dt.datetime.now(dt.UTC)
                p.payload["dropped"] = reason
                continue
            per_agent[p.client] = per_agent.get(p.client, 0) + 1
            action: Action = p.payload["action"]
            entry = (
                state.entry_for(p.isin or "", "my" if action == "remove_my" else "system")
                if action in ("remove_my", "promote")
                else None
            )
            sec = self.resolve(p.isin or "")
            assert sec is not None  # `_admit` checked it
            f = {"isin": sec[0], "symbol": sec[1], "cap": sec[2]}
            s = self.engine._suggest(  # noqa: SLF001, the engine owns suggestion construction
                state, entry, action, p.reason, sources=list(entry.sources) if entry else [],
                flag=None, origin=p.client, today=today, run_id=p.agent_run_id or self.ctx.run_id,
                evidence={"refs": p.evidence_refs, "proposal_id": p.proposal_id},
                now=dt.datetime.now(dt.UTC), acts=acts, isin=f["isin"], symbol=f["symbol"], cap=f["cap"],
            )  # fmt: skip
            p.payload["sugg_id"] = s.sugg_id
        if changed:
            self.proposals.save(rows)
        return acts

    def _admit(
        self, state: WatchlistState, p: Proposal, per_agent: dict[str, int], today: dt.date
    ) -> str | None:
        cfg = self.bundle.watchlist
        action = p.payload.get("action")
        if action not in ("add_my", "remove_my", "promote"):
            return "unknown action"
        sec = self.resolve(p.isin or "")
        if sec is None:
            return "not in the universe"
        if per_agent.get(p.client, 0) >= cfg.agent_proposals.max_per_run:
            return "agent proposal cap reached for this run"
        if cfg.agent_proposals.dedupe_open and state.open_suggestion(sec[0]) is not None:
            return "an open suggestion already exists for this stock"
        if action == "add_my" and state.entry_for(sec[0], "my") is not None:
            return "already on My Watchlist"
        if action == "remove_my" and state.entry_for(sec[0], "my") is None:
            return "not on My Watchlist"
        if action == "promote":
            e = state.entry_for(sec[0], "system")
            if e is None:
                return "not on the System list"
            months = months_between(e.added_period, period_of(today))
            if months < cfg.promotion.min_months_on_system:
                return "minimum stay on the System list not served"
        return None

    def propose(
        self,
        *,
        action: str,
        query: str,
        reason: str,
        evidence_refs: list[str],
        client: str,
        agent_run_id: str | None = None,
    ) -> Proposal:
        """The `propose_watchlist` tool body: validate shape, write a proposal row, change nothing else."""
        sec = self.resolve(query)
        if sec is None:
            raise WatchlistError(f"{query!r} is not in the universe; use an NSE symbol or an ISIN")
        if action not in ("add_my", "remove_my", "promote"):
            raise WatchlistError("action must be add_my, remove_my or promote")
        if len(reason.strip()) < 15:
            raise WatchlistError("give a reason of at least a sentence (15 characters)")
        p = self.proposals.add(
            Proposal(
                kind="watchlist",
                isin=sec[0],
                payload={"action": action, "symbol": sec[1]},
                reason=reason.strip(),
                evidence_refs=evidence_refs,
                agent_run_id=agent_run_id,
                client=client,
            )  # fmt: skip
        )
        self._emit(
            AUD.AGENT_PROPOSAL, entity_type="proposal", entity_id=p.proposal_id, isin=sec[0],
            channel="mcp", reason=reason[:200], details={"kind": "watchlist", "action": action},
            agent=client.removeprefix("agent:") or None,
        )  # fmt: skip
        return p

    # -- decisions: the same calls for Streamlit, Telegram and the CLI --------------------------
    def _suggestion(self, state: WatchlistState, sugg_id: str) -> Suggestion:
        s = state.suggestions.get(sugg_id)
        if s is None:  # accept a unique prefix, the form the CLI and Telegram show
            hits = [v for k, v in state.suggestions.items() if k.startswith(sugg_id)]
            if len(hits) == 1:
                s = hits[0]
        if s is None:
            raise WatchlistError(f"no suggestion {sugg_id!r}; run `parakh watchlist pending`")
        return s

    def approve(
        self,
        sugg_id: str,
        *,
        channel: Channel,
        note: str | None = None,
        target_entry_inr: float | None = None,
        today: dt.date | None = None,
    ) -> Decision:
        today = today or dt.date.today()
        state = self.repo.load()
        s = self._suggestion(state, sugg_id)
        if s.status not in ("pending", "snoozed"):
            return Decision(False, f"already {s.status}", s)
        entry: Entry | None = None
        if s.action == "add_my":
            if not (note or s.reason).strip():
                raise WatchlistError("adding to My Watchlist needs a reason (AC-F15.2)")
            if state.entry_for(s.isin, "my") is not None:
                s.status, s.decided_on = "rejected", today
                self.repo.save(state)
                return Decision(False, "already on My Watchlist", s)
            system = state.entry_for(s.isin, "system")
            if system is not None:
                system.status, system.removed_on = "archived", today
                system.removal_rule, system.removal_reason = "RM.bumped", "moved to My Watchlist"
            entry = self._new_my_entry(s, today, note, target_entry_inr)
            state.entries[entry.entry_id] = entry
        elif s.action == "promote":
            entry = state.entry_for(s.isin, "system")
            if entry is None:
                s.status, s.decided_on = "expired", today
                self.repo.save(state)
                return Decision(False, "no longer on the System list", s)
            entry.list_kind, entry.added_by = "my", f"promoted:{channel}"
            entry.review_on = today + dt.timedelta(
                days=30 * self.bundle.watchlist.my_watchlist.default_review_months
            )
            entry.thesis_pending = True
            entry.reason = (note or s.reason).strip()
            if target_entry_inr is not None:
                entry.target_entry_inr = target_entry_inr
        else:  # remove_my
            entry = state.entry_for(s.isin, "my")
            if entry is not None:
                entry.status, entry.removed_on = "archived", today
                entry.removal_rule, entry.removal_reason = "manual", (note or s.reason)
        s.status, s.decided_on, s.decided_by = "approved", today, self.ctx.actor
        s.decision_note, s.channel = note, channel
        state.events.append(
            WatchEvent(
                event_id=new_ulid(), entry_id=entry.entry_id if entry else None, isin=s.isin,
                type="promoted" if s.action == "promote" else ("added" if s.action == "add_my" else "removed"),
                rule_id=s.flag, run_id=self.ctx.run_id, at=dt.datetime.now(dt.UTC),
                detail={"sugg_id": s.sugg_id, "channel": channel},
            )
        )  # fmt: skip
        self.repo.save(state)
        self._emit(
            AUD.WATCHLIST_APPROVED, entity_type="watchlist_suggestion", entity_id=s.sugg_id,
            isin=s.isin, channel=channel, reason=note,
            details={"action": s.action, "origin": s.origin, "symbol": s.symbol},
        )  # fmt: skip
        needs = bool(entry and s.action in ("add_my", "promote"))
        return Decision(True, f"{s.action} approved for {s.symbol}", s, entry, needs_thesis=needs)

    def _new_my_entry(
        self, s: Suggestion, today: dt.date, note: str | None, target: float | None
    ) -> Entry:
        return Entry(
            entry_id=new_ulid(), isin=s.isin, symbol=s.symbol, cap=s.cap, list_kind="my",
            added_on=today, added_period=period_of(today), added_by=f"approved:{s.origin}",
            sources=s.sources, reason=(note or s.reason).strip(), target_entry_inr=target,
            review_on=today + dt.timedelta(days=30 * self.bundle.watchlist.my_watchlist.default_review_months),
            thesis_pending=True,
        )  # fmt: skip

    def reject(
        self,
        sugg_id: str,
        *,
        channel: Channel,
        note: str | None = None,
        today: dt.date | None = None,
    ) -> Decision:
        today = today or dt.date.today()
        state = self.repo.load()
        s = self._suggestion(state, sugg_id)
        if s.status not in ("pending", "snoozed"):
            return Decision(False, f"already {s.status}", s)
        s.status, s.decided_on, s.decided_by = "rejected", today, self.ctx.actor
        s.decision_note, s.channel = note, channel
        if (
            s.action == "promote"
        ):  # rejected twice means muted until the sources change (plan 06 §4.3)
            e = state.entry_for(s.isin, "system")
            if e is not None:
                e.promote_rejections += 1
                e.promote_rejected_sources = list(e.sources)
        self.repo.save(state)
        self._emit(
            AUD.WATCHLIST_REJECTED, entity_type="watchlist_suggestion", entity_id=s.sugg_id,
            isin=s.isin, channel=channel, reason=note,
            details={"action": s.action, "origin": s.origin, "symbol": s.symbol},
        )  # fmt: skip
        return Decision(True, f"{s.action} rejected for {s.symbol}", s)

    def snooze(self, sugg_id: str, *, channel: Channel, today: dt.date | None = None) -> Decision:
        today = today or dt.date.today()
        state = self.repo.load()
        s = self._suggestion(state, sugg_id)
        if s.status != "pending":
            return Decision(False, f"already {s.status}", s)
        days = self.bundle.watchlist.suggestions.snooze_days
        s.status, s.snoozed_until = "snoozed", today + dt.timedelta(days=days)
        s.decided_by, s.channel = self.ctx.actor, channel
        self.repo.save(state)
        self._emit(
            AUD.WATCHLIST_SNOOZED, entity_type="watchlist_suggestion", entity_id=s.sugg_id,
            isin=s.isin, channel=channel, details={"until": s.snoozed_until.isoformat(), "symbol": s.symbol},
        )  # fmt: skip
        return Decision(True, f"snoozed until {s.snoozed_until:%d %b}", s)

    # -- direct actions by you (not suggestions) -------------------------------------------------
    def add_my(
        self,
        query: str,
        *,
        reason: str,
        channel: Channel,
        target_entry_inr: float | None = None,
        today: dt.date | None = None,
    ) -> Decision:
        today = today or dt.date.today()
        if not reason.strip():
            raise WatchlistError("adding to My Watchlist needs a reason (AC-F15.2)")
        sec = self.resolve(query)
        if sec is None:
            raise WatchlistError(
                f"{query!r} is not in the universe; try the NSE symbol or the ISIN"
            )
        state = self.repo.load()
        if state.entry_for(sec[0], "my") is not None:
            return Decision(False, f"{sec[1]} is already on My Watchlist")
        system = state.entry_for(sec[0], "system")
        if system is not None:
            system.status, system.removed_on = "archived", today
            system.removal_rule, system.removal_reason = "RM.bumped", "moved to My Watchlist"
        e = Entry(
            entry_id=new_ulid(), isin=sec[0], symbol=sec[1], cap=sec[2],  # type: ignore[arg-type]
            list_kind="my", added_on=today, added_period=period_of(today), added_by="user",
            reason=reason.strip(), target_entry_inr=target_entry_inr, thesis_pending=True,
            review_on=today + dt.timedelta(days=30 * self.bundle.watchlist.my_watchlist.default_review_months),
        )  # fmt: skip
        state.entries[e.entry_id] = e
        self.repo.save(state)
        self._emit(
            AUD.WATCHLIST_MANUAL_ADD, entity_type="watchlist_entry", entity_id=e.entry_id,
            isin=e.isin, channel=channel, reason=reason, details={"symbol": e.symbol, "cap": e.cap},
        )  # fmt: skip
        return Decision(True, f"{e.symbol} added to My Watchlist", entry=e, needs_thesis=True)

    def remove_my(
        self, query: str, *, reason: str, channel: Channel, today: dt.date | None = None
    ) -> Decision:
        """You removing your own entry, with a reason. The pipeline can never do this (AC-F14.1)."""
        today = today or dt.date.today()
        if not reason.strip():
            raise WatchlistError("removing from My Watchlist needs a reason")
        sec = self.resolve(query)
        state = self.repo.load()
        e = state.entry_for(sec[0], "my") if sec else None
        if e is None:
            return Decision(False, f"{query} is not on My Watchlist")
        e.status, e.removed_on, e.removal_rule, e.removal_reason = (
            "archived",
            today,
            "manual",
            reason,
        )
        self.repo.save(state)
        self._emit(
            AUD.WATCHLIST_MANUAL_REMOVE, entity_type="watchlist_entry", entity_id=e.entry_id,
            isin=e.isin, channel=channel, reason=reason, details={"symbol": e.symbol},
        )  # fmt: skip
        return Decision(True, f"{e.symbol} archived", entry=e)

    def mark_thesis_done(self, query: str) -> None:
        sec = self.resolve(query)
        state = self.repo.load()
        for e in state.open_entries():
            if sec and e.isin == sec[0]:
                e.thesis_pending = False
        self.repo.save(state)

    # -- reads ----------------------------------------------------------------------------------
    def pending(self) -> list[Suggestion]:
        return self.repo.load().pending()
