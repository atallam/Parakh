"""Transcript refresh and the refresh-request drain (F06; AC-F06.7, AC-F25.4).

    fetch_transcript(provider, store, isin, symbol)     # one stock: latest valid call into the cache
    drain(deps...)                                      # the daily job: serve queued `jobs.request_refresh` rows

A stock with no valid transcript is recorded with the stage and reason it failed (list_calls, fetch or
validate), so it is never silently skipped. Failures are isolated per stock.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

import structlog

from parakh.adapters.concalls import Transcript
from parakh.agents.enrich import enrich_snapshot
from parakh.agents.qualitative import run_qualitative
from parakh.agents.runtime.base import AgentRunner
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.configs import ConfigBundle
from parakh.services.documents import CachedDoc, FetchStatus, TranscriptStore
from parakh.services.job_requests import JobRequests
from parakh.services.watchlist import default_resolver
from parakh.snapshots.store import periods_for, snapshot_path
from parakh.watch.state import StateStore

log = structlog.get_logger(__name__)


class ConcallProvider(Protocol):
    def latest_valid(
        self, symbol: str, max_candidates: int = 4
    ) -> tuple[Transcript | None, list[str]]: ...


def fetch_transcript(
    provider: ConcallProvider, store: TranscriptStore, *, isin: str, symbol: str, today: dt.date
) -> CachedDoc | None:
    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    try:
        tx, log_lines = provider.latest_valid(symbol)
    except Exception as exc:
        store.record_status(FetchStatus(isin, False, "list_calls", type(exc).__name__, [], stamp))
        return None
    if tx is None:
        store.record_status(
            FetchStatus(isin, False, "validate", "no valid transcript in the newest calls", log_lines, stamp)
        )  # fmt: skip
        return None
    doc = store.put(
        CachedDoc(
            isin=isin,
            symbol=symbol,
            period=tx.period.strftime("%Y-%m"),
            source_url=tx.final_url,
            sha256=tx.sha256,
            fetched_on=today.isoformat(),
            pages=tx.pages,
            text=tx.text,
            notes=list(tx.notes),
        )  # fmt: skip
    )
    store.record_status(FetchStatus(isin, True, "", "", log_lines, stamp))
    return doc


@dataclass
class DrainResult:
    served: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)


def drain(
    provider: ConcallProvider,
    runner: AgentRunner | None,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    *,
    today: dt.date,
    store: StateStore | None = None,
    transcripts: TranscriptStore | None = None,
) -> DrainResult:
    store = store or StateStore()
    transcripts = transcripts or TranscriptStore()
    jobs = JobRequests(store, bundle.flags.jobs.refresh_daily_cap)
    out = DrainResult()
    if jobs.monthly_running():  # leave the queue for after the monthly run
        out.details.append("monthly run in progress; queue left as is")
        return out
    resolve = default_resolver(bundle)
    for req in jobs.queued():
        sec = resolve(req.isin)
        if sec is None or runner is None:
            jobs.finish(
                req.request_id, "skipped", "not in the universe" if sec is None else "agents off"
            )
            out.skipped += 1
            continue
        isin, symbol, cap = sec[0], sec[1], sec[2]
        try:
            doc = fetch_transcript(provider, transcripts, isin=isin, symbol=symbol, today=today)
            res = run_qualitative(
                runner, bundle, ctx, sink, isin=isin, symbol=symbol, doc=doc,
                previous=transcripts.get(isin, previous=True), store=store,
            )  # fmt: skip
            periods = periods_for(cap, symbol)
            if periods and res.overlay:
                enrich_snapshot(snapshot_path(cap, symbol, periods[-1]), qualitative=res.overlay)
            ok = res.status in ("ok", "cached")
            jobs.finish(req.request_id, "done" if ok else "failed", res.status)
            out.served += ok
            out.failed += not ok
        except Exception as exc:
            jobs.finish(req.request_id, "failed", type(exc).__name__)
            out.failed += 1
            log.warning("refresh.failed", isin=isin, error=type(exc).__name__)
    return out
