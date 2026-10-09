"""Everything that follows the deterministic monthly run (Phase 4): enrichment, curation, watchlist.

    out = post_monthly(bundle, runner, ctx, sink, period="2026-10", today=day, snaps=snaps)
    out.watchlist_line         # for the monthly Telegram summary

Order matters. The monthly lock goes on first so agents cannot queue refreshes mid-run (AC-F25.4). The
overlays (devil's advocate, qualitative) are written onto the snapshots next; thesis flags become
proposals, never status changes (D13). The curator proposes; then the rule-based watchlist review runs
over the enriched snapshots and ingests the proposals under the same rules. The lock is always released.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import structlog

from parakh.agents.curator import curate
from parakh.agents.devils_advocate import run_devils_advocate
from parakh.agents.enrich import enrich_snapshot
from parakh.agents.health import llm_health, render_llm_alert
from parakh.agents.qualitative import run_qualitative, thesis_effect
from parakh.agents.runtime.base import AgentRunner
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.configs import ConfigBundle
from parakh.notify.suggestions import render_suggestion_cards
from parakh.notify.templates import Message
from parakh.services.documents import TranscriptStore
from parakh.services.job_requests import JobRequests
from parakh.services.watchlist import WatchlistService, default_resolver
from parakh.snapshots.store import load_previous, snapshot_path
from parakh.watch.state import StateStore
from parakh.watchlist.proposals import LocalProposalStore, Proposal
from parakh.watchlist.repository import open_repository
from parakh.watchlist.review import monthly_review

log = structlog.get_logger(__name__)


@dataclass
class PostMonthly:
    qualitative: dict[str, int] = field(default_factory=dict)
    advocate: dict[str, int] = field(default_factory=dict)
    thesis_flags: int = 0
    watchlist_line: str = ""
    suggestions: Message | None = None
    llm_alert: Message | None = None
    curator_status: str = "skipped"
    errors: list[str] = field(default_factory=list)


def _bump(d: dict[str, int], key: str) -> None:
    d[key] = d.get(key, 0) + 1


def enrich_stocks(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    snaps: list[dict[str, Any]],
    out: PostMonthly,
    *,
    store: StateStore,
    transcripts: TranscriptStore,
    proposals: LocalProposalStore,
) -> None:
    for s in snaps:
        path = snapshot_path(s["cap"], s["symbol"], s["period"])
        try:
            prev = load_previous(s["cap"], s["symbol"], s["period"])
            da = run_devils_advocate(runner, bundle, ctx, sink, snap=s, previous=prev)
            _bump(out.advocate, da.status)
            q = run_qualitative(
                runner, bundle, ctx, sink, isin=s["isin"], symbol=s["symbol"],
                doc=transcripts.get(s["isin"]), previous=transcripts.get(s["isin"], previous=True),
                store=store,
            )  # fmt: skip
            _bump(out.qualitative, q.status)
            if q.status in ("ok", "cached", "pending", "failed"):
                enrich_snapshot(
                    path,
                    qualitative=q.overlay,
                    devils_advocate=da.overlay or None,
                    confidence_delta=da.confidence_delta,
                )
            elif da.overlay:
                enrich_snapshot(
                    path, devils_advocate=da.overlay, confidence_delta=da.confidence_delta
                )
            if thesis_effect(q.flags) and q.status == "ok":  # cached flags were proposed before
                for f in q.flags:
                    proposals.add(
                        Proposal(
                            kind="thesis_flag",
                            isin=s["isin"],
                            client="agent:qualitative",
                            payload={
                                "condition_id": f.item_id,
                                "status": "WATCH",
                                "symbol": s["symbol"],
                            },
                            reason=f"{f.item_id} {f.verdict.lower()} per the latest concall",
                            evidence_refs=[q.overlay["document_id"]],
                        )  # fmt: skip
                    )
                    out.thesis_flags += 1
        except Exception as exc:  # one stock never stops the run
            log.warning("post_monthly.stock_failed", symbol=s["symbol"], error=type(exc).__name__)
            out.errors.append(f"{s['symbol']}: {type(exc).__name__}")


def post_monthly(
    bundle: ConfigBundle,
    runner: AgentRunner | None,
    ctx: RunContext,
    sink: AuditSink,
    *,
    period: str,
    today: dt.date,
    snaps: list[dict[str, Any]],
    store: StateStore | None = None,
    transcripts: TranscriptStore | None = None,
    event_rows: list[dict[str, Any]] | None = None,
) -> PostMonthly:
    store = store or StateStore()
    out = PostMonthly()
    jobs = JobRequests(store, bundle.flags.jobs.refresh_daily_cap)
    jobs.lock_monthly(True)
    try:
        proposals = LocalProposalStore(store)
        if runner is not None and bundle.flags.qualitative.enabled:
            enrich_stocks(
                runner, bundle, ctx, sink, snaps, out, store=store,
                transcripts=transcripts or TranscriptStore(), proposals=proposals,
            )  # fmt: skip
        svc = WatchlistService(
            open_repository(store), bundle, ctx, sink=sink, resolver=default_resolver(bundle),
            proposals=proposals,
        )  # fmt: skip
        if runner is not None and bundle.flags.watchlist.enabled:
            held = svc.repo.load()
            cap = bundle.watchlist.system_watchlist.capacity
            room = {c: cap[c] - len(held.open_entries(cap=c, kind="system")) for c in cap}
            res = curate(runner, bundle, ctx, sink, svc, period=period, room=room, today=today)
            out.curator_status = res.status
        if bundle.flags.watchlist.enabled:
            review = monthly_review(svc, snaps, period=period, today=today, event_rows=event_rows)
            out.watchlist_line = review.line
            out.suggestions = render_suggestion_cards(
                svc.pending(), max_cards=bundle.watchlist.suggestions.telegram_max_cards
            )
    finally:
        jobs.lock_monthly(False)
    if runner is not None:
        out.llm_alert = render_llm_alert(
            llm_health(sink.events_for_run(ctx.run_id), bundle.agents.alerts)
        )  # type: ignore[attr-defined]
    return out
