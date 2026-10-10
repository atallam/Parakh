"""What the Streamlit app calls: view models built from snapshots, state and the services (ADR-006).

`app/` imports this module and `render/`, never `analytics/`, `lenses/` or `adapters/` (AC-F15.5). Nothing here
fetches data or calls a model, so a page renders from the files on disk alone (AC-F15.11). Quantities, costs and
rupee values reach a view model only when the caller passes `detail=True`; the privacy toggle passes False.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from parakh import __version__
from parakh.audit.context import RunContext
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.notify.inbox import Inbox
from parakh.services import portfolio_service, report_service
from parakh.services.view_models import ChangeItem, PositionsOut
from parakh.services.watchlist import WatchlistService, default_resolver
from parakh.snapshots.store import (
    all_stock_dirs,
    periods_for,
    read_snapshot_dict,
    snapshot_path,
    stock_dir,
)
from parakh.thesis.editor import SaveResult, ThesisDraft, save_thesis
from parakh.thesis.model import read_thesis
from parakh.watch.state import StateStore
from parakh.watchlist.models import WatchlistState
from parakh.watchlist.repository import open_repository

MARKS = "review_marks"


# -- the Home inbox (plan 12 §5.1; AC-F15.8) -----------------------------------------------------
class InboxItem(BaseModel):
    key: str
    symbol: str | None = None
    owned: bool = False
    kind: str  # verdict | thesis | signal | red_flag | regime | approval | review_due
    title: str
    detail: str = ""
    priority: int = 5
    seen: bool = False


class InboxView(BaseModel):
    items: list[InboxItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    reviewed: int = 0
    total: int = 0
    theses_missing: int = 0
    pending_approvals: int = 0
    period: str | None = None
    governance: str = ""


def _priority(owned: bool, kind: str, text: str) -> int:
    bad = kind in ("thesis", "red_flag") or any(
        w in text for w in ("SELL", "EXIT", "TRIM", "REDUCE", "BROKEN")
    )
    if owned and bad:
        return 0
    if owned:
        return 1
    if kind == "approval":
        return 2
    if kind == "verdict":
        return 3
    return 4


def _marks(store: StateStore) -> dict[str, Any]:
    return store.load(MARKS) or {"reviewed": {}, "window_started": None}


def watch_store() -> StateStore:
    return StateStore()


def inbox(root: Path | None = None, store: StateStore | None = None) -> InboxView:
    store = store or watch_store()
    marks = _marks(store)
    reviewed = marks.get("reviewed", {})
    items: list[InboxItem] = []
    wc = report_service.what_changed(root=root)
    period = wc.period if wc.found else None
    for c in wc.items:
        c = ChangeItem.model_validate(c)
        key = f"{period}:{c.symbol}:{c.kind}:{c.text[:40]}"
        items.append(
            InboxItem(key=key, symbol=c.symbol, owned=c.owned, kind=c.kind, title=f"{c.symbol} · {c.kind.replace('_', ' ')}",
                      detail=c.text, priority=_priority(c.owned, c.kind, c.text), seen=key in reviewed)
        )  # fmt: skip
    for i in Inbox(store).items():
        key = f"inbox:{i['key']}"
        items.append(
            InboxItem(key=key, symbol=i.get("symbol"), owned=True, kind=i.get("kind", "thesis"), title=i["title"],
                      detail=i.get("detail", ""), priority=0, seen=bool(i.get("seen")) or key in reviewed)
        )  # fmt: skip
    pend = portfolio_service.pending_approvals(open_repository(store))
    for p in pend.items:
        key = f"approval:{p.id}"
        items.append(
            InboxItem(key=key, symbol=p.symbol, kind="approval", title=f"{p.symbol or ''} · {p.action}".strip(" ·"),
                      detail=p.reason, priority=2, seen=key in reviewed)
        )  # fmt: skip
    positions = portfolio_service.positions(detail=False, root=root)
    missing = sum(1 for r in positions.rows if r.thesis_status == "NOT_SET")
    for r in positions.rows:
        th = portfolio_service.get_thesis(r.isin, root)
        if th.review_due:
            key = f"review_due:{r.isin}:{period}"
            items.append(
                InboxItem(key=key, symbol=r.symbol, owned=True, kind="review_due", title=f"{r.symbol} · thesis review due",
                          detail=f"review by {th.review_by}", priority=1, seen=key in reviewed)
            )  # fmt: skip
    items.sort(key=lambda i: (i.seen, i.priority, i.symbol or ""))
    counts: dict[str, int] = {}
    for i in items:
        if not i.seen:
            counts[i.kind] = counts.get(i.kind, 0) + 1
    chain = get_sink().verify_chain()
    return InboxView(
        items=items, counts=counts, reviewed=sum(1 for i in items if i.seen), total=len(items),
        theses_missing=missing, pending_approvals=len(pend.items), period=period,
        governance="🛡 Integrity ✅" if chain.ok else "🛡 Integrity ❌ chain broken",
    )  # fmt: skip


def mark_reviewed(
    keys: list[str], *, store: StateStore | None = None, now: dt.datetime | None = None
) -> int:
    """Mark items reviewed (never deletes them). One audit event per call; minutes since the window opened."""
    store = store or watch_store()
    now = now or dt.datetime.now(dt.UTC)
    marks = _marks(store)
    started = marks.get("window_started") or now.isoformat()
    for k in keys:
        marks["reviewed"][k] = now.isoformat()
    marks["reviewed"] = dict(list(marks["reviewed"].items())[-2000:])
    minutes = round((now - dt.datetime.fromisoformat(started)).total_seconds() / 60, 1)
    marks["window_started"] = None
    store.save(MARKS, marks)
    get_sink().emit(
        RunContext.create(mode="review", actor_type="user", actor_id="owner"), AUD.REVIEW_MARKED,
        entity_type="inbox", entity_id="home", details={"count": len(keys), "minutes": minutes},
    )  # fmt: skip
    return len(keys)


def open_review_window(store: StateStore | None = None, now: dt.datetime | None = None) -> None:
    """Start the review clock at the first open since the last 'mark all reviewed'."""
    store = store or watch_store()
    marks = _marks(store)
    if not marks.get("window_started"):
        marks["window_started"] = (now or dt.datetime.now(dt.UTC)).isoformat()
        store.save(MARKS, marks)


# -- watchlist (plan 06 §5) ---------------------------------------------------------------------
@dataclass
class WatchView:
    state: WatchlistState
    capacity: dict[str, int]
    used: dict[str, int] = field(default_factory=dict)
    expired_soon: int = 0


def watch_service(store: StateStore | None = None) -> WatchlistService:
    bundle = load_all()
    ctx = RunContext.create(mode="streamlit", actor_type="user", actor_id="owner")
    return WatchlistService(
        open_repository(store or watch_store()), bundle, ctx, resolver=default_resolver(bundle)
    )


def watchlist(store: StateStore | None = None) -> WatchView:
    bundle = load_all()
    state = open_repository(store or watch_store()).load()
    cap: dict[str, int] = {str(k): v for k, v in bundle.watchlist.system_watchlist.capacity.items()}
    used = {c: len(state.open_entries(cap=c, kind="system")) for c in cap}  # type: ignore[arg-type]
    return WatchView(state, cap, used)


# -- holdings and thesis (plan 12 §5.3) ---------------------------------------------------------
def holdings(detail: bool, root: Path | None = None) -> PositionsOut:
    return portfolio_service.positions(detail=detail, root=root)


def thesis_path(symbol: str, root: Path | None = None) -> Path | None:
    sec = report_service.resolve(symbol, root)
    return None if sec is None else stock_dir(sec.cap, sec.symbol, root) / "THESIS.md"


def thesis_draft(symbol: str, root: Path | None = None) -> dict[str, Any]:
    """Defaults for the form: empty for a new thesis, the working thesis for an edit; `locked` = original fixed."""
    path = thesis_path(symbol, root)
    parsed = read_thesis(path) if path else None
    if parsed is None or parsed.front is None:
        return {
            "locked": False,
            "statement": "",
            "key_metrics": [],
            "breakers": [],
            "sizing": "",
            "version": 0,
        }
    f = parsed.front
    return {
        "locked": True, "statement": f.original.statement, "written_on": f.original.written_on,
        "key_metrics": [k.text for k in f.key_metrics],
        "breakers": [{"text": b.text, "check": b.check, "rule": b.rule or ""} for b in f.breakers],
        "sizing": f.sizing_rationale or "", "version": f.thesis_version,
    }  # fmt: skip


def save_thesis_form(
    symbol: str, draft: ThesisDraft, root: Path | None = None, today: dt.date | None = None
) -> SaveResult:
    sec = report_service.resolve(symbol, root)
    path = thesis_path(symbol, root)
    if sec is None or path is None:
        return SaveResult(False, errors=[f"{symbol} is not in the universe"])
    from parakh.thesis.known_vars import known_variables

    res = save_thesis(
        path, symbol=sec.symbol, isin=sec.isin, draft=draft, today=today or dt.date.today(),
        known_variables=known_variables(),
    )  # fmt: skip
    if res.ok:
        watch_service().mark_thesis_done(sec.symbol)  # the Home banner stops counting it
    return res


# -- stock detail (plan 12 §5.2) ----------------------------------------------------------------
class StockDetail(BaseModel):
    found: bool
    message: str = ""
    symbol: str | None = None
    name: str | None = None
    cap: str | None = None
    period: str | None = None
    view: dict[str, Any] = Field(default_factory=dict)
    verdict_now: str | None = None
    prev_verdict: str | None = None
    owned: bool = False
    thesis: dict[str, Any] = Field(default_factory=dict)
    qualitative: dict[str, Any] = Field(default_factory=dict)
    devils_advocate: dict[str, Any] | None = None
    chart: dict[str, Any] = Field(default_factory=dict)
    events: dict[str, Any] = Field(default_factory=dict)
    history_rows: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    report_path: str | None = None


def stock_detail(query: str, period: str | None = None, root: Path | None = None) -> StockDetail:
    look = report_service.get_stock(query, period, root)
    if not look.found or look.view is None:
        return StockDetail(found=False, message=look.message)
    sec = report_service.resolve(query, root)
    assert sec is not None
    snap = read_snapshot_dict(snapshot_path(sec.cap, sec.symbol, look.period or "", root)) or {}
    hist = report_service.get_history(query, root=root)
    timeline = [
        {"period": r.get("period"), "text": r.get("verdict") or r.get("chip") or ""}
        for r in hist.rows
    ]
    th = snap.get("thesis", {})
    return StockDetail(
        found=True, symbol=sec.symbol, name=sec.name, cap=sec.cap, period=look.period, view=look.view,
        verdict_now=look.view["verdict"]["verdict"], prev_verdict=look.view["verdict"].get("prev_verdict"),
        owned=bool(snap.get("verdict", {}).get("owned")),
        thesis={**th, "front": thesis_draft(sec.symbol, root)},
        qualitative=snap.get("qualitative", {}), devils_advocate=snap.get("devils_advocate"),
        chart=snap.get("chart", {}), events=snap.get("events", {}), history_rows=hist.rows, timeline=timeline,
        report_path=look.view.get("report_path"),
    )  # fmt: skip


def universe_options(root: Path | None = None) -> list[str]:
    bundle = load_all()
    have = {
        s.symbol
        for c in ("large", "mid", "small")
        for d in all_stock_dirs(c, root)
        for s in bundle.universe.active
        if s.symbol == d.name
    }
    return sorted(have or {s.symbol for s in bundle.universe.active})


def latest_period(symbol: str, root: Path | None = None) -> str | None:
    sec = report_service.resolve(symbol, root)
    ps = periods_for(sec.cap, sec.symbol, root) if sec else []
    return ps[-1] if ps else None


# -- audit and governance (plan 10) ------------------------------------------------------------
class AuditView(BaseModel):
    chain_ok: bool
    events: int
    head: str
    recent: list[dict[str, Any]] = Field(default_factory=list)
    overrides_expiring: list[dict[str, Any]] = Field(default_factory=list)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    version: str = __version__


def audit(limit: int = 40, asof: dt.date | None = None) -> AuditView:
    from parakh.policy.overrides import nearing_expiry

    sink = get_sink()
    chain = sink.verify_chain()
    events = sink.events()
    bundle = load_all()
    recent = [
        {"at": e.ts_utc.isoformat(timespec="seconds"), "type": e.event_type.value,
         "entity": e.entity_id or "", "actor": f"{e.actor_type}:{e.actor_id}"}
        for e in events[-limit:][::-1]
    ]  # fmt: skip
    return AuditView(
        chain_ok=chain.ok, events=chain.events, head=sink.head()[:16],
        recent=recent,
        overrides_expiring=[o.model_dump(mode="json") for o in nearing_expiry(bundle.overrides, asof or dt.date.today())],
        agents=[
            {"agent": aid, "enabled": a.enabled, "dry_run": bundle.agents.dry_run, "tools": len(a.allowed_tools),
             "prompt": a.prompt_id or "-"}
            for aid, a in bundle.agents.agents.items()
        ],
    )  # fmt: skip


# -- segment dashboard extras ------------------------------------------------------------------
def score_matrix(
    cap: str, lens: str = "value", months: int = 6, root: Path | None = None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Stocks × months scores for the heatmap, newest months only; verdict changes are marked."""
    rows: list[dict[str, Any]] = []
    all_periods: set[str] = set()
    for d in all_stock_dirs(cap, root):
        cells: dict[str, float | None] = {}
        changed: dict[str, bool] = {}
        for p in periods_for(cap, d.name, root)[-months:]:
            s = read_snapshot_dict(snapshot_path(cap, d.name, p, root))
            if not s:
                continue
            cells[p] = s[lens].get("score")
            changed[p] = bool(s["verdict"].get("changed"))
            all_periods.add(p)
        if cells:
            rows.append({"symbol": d.name, "cells": cells, "changed": changed})
    cols = sorted(all_periods)[-months:]
    rows.sort(key=lambda r: -(r["cells"].get(cols[-1]) or 0) if cols else 0)
    return rows, cols


def lot_writer() -> Any | None:
    """The holdings lot writer when Supabase is configured; None otherwise (the editor then explains why)."""
    from parakh.config import get_settings

    s = get_settings()
    if not getattr(s, "supabase_url", None):
        return None
    from parakh.db import get_supabase
    from parakh.services.holdings_editor import SupabaseLotWriter

    return SupabaseLotWriter(get_supabase())


def segment_full(
    cap: str, period: str | None = None, root: Path | None = None
) -> dict[str, Any] | None:
    """The whole segment view written by the monthly run (percentages only), for the dashboard tables."""
    import json

    from parakh.snapshots.store import cap_dir

    folder = cap_dir(cap, root) / "_SEGMENT_SUMMARY"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    path = folder / f"{period}.json" if period else (files[-1] if files else None)
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# -- calibration page (F17; plan 12) --------------------------------------------------------------
@dataclass
class CalibrationView:
    due: list[Any] = field(default_factory=list)
    entries: list[Any] = field(default_factory=list)
    journal_stats: dict[str, Any] = field(default_factory=dict)
    alerts_to_rate: list[dict[str, Any]] = field(default_factory=list)
    precision: dict[str, Any] = field(default_factory=dict)
    report_quarter: str | None = None
    report_markdown: str = ""
    tags: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def journal_service(store: StateStore | None = None) -> Any:
    from parakh.calibration.journal import JournalStore
    from parakh.services.journal import JournalService

    ctx = RunContext.create(mode="streamlit", actor_type="user", actor_id="owner")
    return JournalService(JournalStore(store or watch_store()), load_all(), ctx)


def latest_calibration_report(root: Path | None = None) -> tuple[str | None, str]:
    from parakh.config import REPO_ROOT

    folder = (root or REPO_ROOT) / "docs" / "calibration"
    files = sorted(folder.glob("*.md")) if folder.exists() else []
    return (files[-1].stem, files[-1].read_text(encoding="utf-8")) if files else (None, "")


def calibration_view(store: StateStore | None = None, root: Path | None = None) -> CalibrationView:
    from parakh.calibration.feedback import alert_precision, latest_feedback
    from parakh.notify.log import AlertsLog

    store = store or watch_store()
    bundle = load_all()
    svc = journal_service(store)
    log = AlertsLog(store.root / "alerts")
    rows = log.rows()
    rated = set(latest_feedback(rows))
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("alert_id") and r.get("decision") in ("sent", "shadow", "digest_sent"):
            seen.setdefault(r["alert_id"], r)
    quarter, md = latest_calibration_report(root)
    return CalibrationView(
        due=svc.due(),
        entries=svc.entries(),
        journal_stats=svc.stats(),
        alerts_to_rate=[r for k, r in list(seen.items())[::-1] if k not in rated][:10],
        precision=alert_precision(rows, bundle.calibration.alerts).as_dict(),
        report_quarter=quarter,
        report_markdown=md,
        tags=list(bundle.calibration.alerts.feedback_tags),
        actions=list(bundle.calibration.journal.actions),
    )


def rate_alert(
    alert_id: str, useful: bool, tag: str | None = None, store: StateStore | None = None
) -> None:
    from parakh.notify.log import AlertsLog
    from parakh.services.alert_feedback import record_alert_feedback

    store = store or watch_store()
    ctx = RunContext.create(mode="streamlit", actor_type="user", actor_id="owner")
    record_alert_feedback(
        AlertsLog(store.root / "alerts"), get_sink(), ctx, load_all().calibration.alerts,
        alert_id, useful=useful, channel="streamlit", tag=tag,
    )  # fmt: skip
