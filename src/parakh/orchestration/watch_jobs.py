"""Automation jobs: daily watch, daily events, evening digest, Sunday heartbeat, bot poll (plan 03).

Every job is a deterministic workflow of audited steps inside `run_lifecycle`. A failure sends one
❌ message within seconds (AC-F11.3, NFR-14) and re-raises so the workflow shows red. A holiday
exits quietly before any run starts (AC-F12.5). Shadow mode lives in the dispatcher: with
`alerts.dry_run` the jobs do everything except send (AC-F12.6).

    deps = WatchDeps(bundle, data, store, notifier, mailer, feeds, sink, button_key, logs_root)
    daily_watch(deps, asof)         # 18:30 IST   momentum signals
    daily_events(deps, asof)        # 19:00 IST   filings, insider trades, surveillance, deals
    evening_digest(deps, asof)      # 19:20 IST   one message for the day's queued items
    heartbeat(deps, today)          # Sunday      all jobs healthy, service levels
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.manifest import RunManifest, runs_dir
from parakh.audit.steps import audited_step, run_lifecycle
from parakh.calendar import Calendar
from parakh.configs import ConfigBundle
from parakh.holdings.position import positions_from_lots
from parakh.notify.dispatch import Dispatcher, Mailer, Ntfy
from parakh.notify.log import AlertsLog, ShadowLog
from parakh.notify.routing import AlertState
from parakh.notify.telegram import Notifier
from parakh.notify.templates import render_failure, render_heartbeat
from parakh.orchestration.analysis_data import AnalysisData
from parakh.watch.events import EventResult, EventSource, EventWatcher
from parakh.watch.momentum import Held, MomentumWatcher, WatchResult
from parakh.watch.state import StateStore

log = structlog.get_logger(__name__)
REFRESH_QUEUE = "refresh_queue"
MAX_REFRESH_PER_DAY = 5  # why: AC-F25.4, Event Triage and the rules together stay under five a day


@dataclass
class WatchDeps:
    bundle: ConfigBundle
    data: AnalysisData
    store: StateStore
    notifier: Notifier | None
    mailer: Mailer | None = None
    feeds: EventSource | None = None
    sink: AuditSink | None = None
    button_key: bytes | None = None
    logs_root: Path | None = None
    ntfy: Ntfy | None = None
    calendar: Calendar | None = None
    trigger: str = "cron"
    extra: dict[str, Any] = field(default_factory=dict)

    def cal(self) -> Calendar:
        return self.calendar or Calendar.from_config(self.bundle.holidays)

    def audit(self) -> AuditSink:
        return self.sink or get_sink()


@dataclass
class JobResult:
    job: str
    status: str  # ok | skipped | failed
    reason: str = ""
    run_id: str | None = None
    alerts: int = 0
    sent: int = 0
    shadowed: int = 0
    suppressed: int = 0
    errors: dict[str, str] = field(default_factory=dict)


def _dispatcher(
    deps: WatchDeps, ctx: RunContext, alerts_log: AlertsLog | None = None
) -> Dispatcher:
    root = deps.logs_root
    return Dispatcher(
        deps.bundle,
        ctx,
        deps.audit(),
        AlertState(deps.store),
        alerts_log or AlertsLog(deps.store.root / "alerts"),
        notifier=deps.notifier,
        mailer=deps.mailer,
        ntfy=deps.ntfy,
        button_key=deps.button_key,
        today=ctx.asof,
        alerts_shadow=ShadowLog("alerts_shadow.md", root),
        agents_shadow=ShadowLog("agents_shadow.md", root),
    )


def build_held(deps: WatchDeps, asof: dt.date) -> dict[str, Held]:
    """Weight and P&L per owned ISIN, as percentages only (plan 12 §8)."""
    start = dt.date(asof.year - 1, 1, 1)
    closes: dict[str, float] = {}
    for sec in deps.bundle.universe.pilot:
        f = deps.data.prices(sec.isin, start, asof)
        if f is not None and not f.empty:
            closes[sec.isin] = float(f.sort_values("trade_date")["close"].iloc[-1])
    pos = positions_from_lots(deps.data.open_lots(), closes, asof, deps.bundle.portfolio.tax)
    return {i: Held(p.weight_pct, p.pnl_pct) for i, p in pos.items()}


def _failed_step(ctx: RunContext) -> str:
    for s in reversed(ctx.steps):
        if s.status == "failed":
            return s.name
    return ctx.steps[-1].name if ctx.steps else "start"


def _send_failure(deps: WatchDeps, ctx: RunContext, job: str, exc: BaseException) -> None:
    try:
        d = _dispatcher(deps, ctx)
        d.send_message(
            render_failure(job, _failed_step(ctx), f"{type(exc).__name__}: {exc}", ctx.run_id),
            code="SYS.FAILURE",
        )
    except Exception as inner:  # a broken notifier must not hide the original error
        log.error("failure_alert.not_sent", error=type(inner).__name__)


def _skip_reason(deps: WatchDeps, asof: dt.date) -> str | None:
    cal = deps.cal()
    if not cal.is_trading_day(asof):
        return f"not a trading day ({cal.holiday_name(asof) or 'weekend'})"
    return None


def _tally(res: JobResult, out: Any) -> None:
    res.sent, res.shadowed, res.suppressed = len(out.sent), len(out.shadowed), len(out.suppressed)


# -- daily watch -------------------------------------------------------------------------------
def daily_watch(deps: WatchDeps, asof: dt.date, *, symbols: list[str] | None = None) -> JobResult:
    if (why := _skip_reason(deps, asof)) is not None:
        log.info("watch.skipped", reason=why)
        return JobResult("watch", "skipped", why)
    ctx = RunContext.create(
        mode="watch",
        asof=asof,
        actor_type="scheduler",
        actor_id="daily-watch",
        trigger=deps.trigger,
    )
    res = JobResult("watch", "ok", run_id=ctx.run_id)
    try:
        with run_lifecycle(ctx, deps.audit()) as outcome:
            with audited_step(ctx, "positions") as step:
                held = build_held(deps, asof)
                step.record_output(owned=len(held))
            watcher = MomentumWatcher(deps.bundle, deps.data, deps.store, held)
            secs = [s for s in deps.bundle.universe.pilot if not symbols or s.symbol in symbols]
            with audited_step(ctx, "scan", stocks=len(secs)) as step:
                scan: WatchResult = watcher.scan(asof, secs)
                step.record_output(
                    scanned=scan.scanned,
                    alerts=len(scan.alerts),
                    errors=len(scan.errors),
                    seeded=scan.seeded,
                )
            res.errors = dict(scan.errors)
            with audited_step(ctx, "notify") as step:
                d = _dispatcher(deps, ctx)
                for isin, code in scan.rearm:
                    d.state.rearm(isin, code)
                out = d.submit(scan.alerts)
                _tally(res, out)
                step.record_output(sent=res.sent, shadowed=res.shadowed, suppressed=res.suppressed)
            res.alerts = len(scan.alerts)
            outcome.summary = _summary(scan.scanned, scan.alerts, scan.errors, res)
            if scan.errors and scan.scanned == 0:
                raise RuntimeError(
                    f"no stock could be scanned: {sorted(set(scan.errors.values()))[:2]}"
                )
    except Exception as exc:
        _send_failure(deps, ctx, "Daily momentum watch", exc)
        res.status, res.reason = "failed", f"{type(exc).__name__}: {exc}"
        raise
    return res


def _summary(
    scanned: int, alerts: list[Any], errors: dict[str, str], res: JobResult
) -> dict[str, Any]:
    return {
        "scanned": scanned,
        "alerts": len(alerts),
        "stock_errors": len(errors),
        "sent": res.sent,
        "shadowed": res.shadowed,
        "suppressed": res.suppressed,
    }


# -- daily events ------------------------------------------------------------------------------
def daily_events(deps: WatchDeps, asof: dt.date) -> JobResult:
    if (why := _skip_reason(deps, asof)) is not None:
        return JobResult("events", "skipped", why)
    if deps.feeds is None:
        raise ValueError("daily_events needs an event source")
    ctx = RunContext.create(
        mode="events",
        asof=asof,
        actor_type="scheduler",
        actor_id="daily-events",
        trigger=deps.trigger,
    )
    res = JobResult("events", "ok", run_id=ctx.run_id)
    try:
        with run_lifecycle(ctx, deps.audit()) as outcome:
            with audited_step(ctx, "positions") as step:
                held = build_held(deps, asof)
                step.record_output(owned=len(held))
            watcher = EventWatcher(deps.bundle, deps.store, held, deps.cal())
            with audited_step(ctx, "scan", stocks=len(deps.bundle.universe.pilot)) as step:
                scan: EventResult = watcher.scan(asof, deps.bundle.universe.pilot, deps.feeds)
                step.record_output(
                    alerts=len(scan.alerts),
                    errors=len(scan.errors),
                    refresh=len(scan.refresh_isins),
                )
            res.errors = dict(scan.errors)
            with audited_step(ctx, "queue_refresh") as step:
                queued = queue_refresh(deps, ctx, asof, scan.refresh_isins)
                step.record_output(queued=queued)
            with audited_step(ctx, "notify") as step:
                out = _dispatcher(deps, ctx).submit(scan.alerts, title="Filings and events")
                _tally(res, out)
                step.record_output(sent=res.sent, shadowed=res.shadowed, suppressed=res.suppressed)
            res.alerts = len(scan.alerts)
            outcome.summary = _summary(
                len(deps.bundle.universe.pilot), scan.alerts, scan.errors, res
            )
            if scan.errors and len(scan.errors) >= 2 * len(deps.bundle.universe.pilot):
                raise RuntimeError(f"event sources failing: {sorted(scan.errors)[:3]}")
    except Exception as exc:
        _send_failure(deps, ctx, "Daily event watch", exc)
        res.status, res.reason = "failed", f"{type(exc).__name__}: {exc}"
        raise
    return res


def queue_refresh(deps: WatchDeps, ctx: RunContext, asof: dt.date, isins: list[str]) -> int:
    """A results or transcript filing asks for a one-stock refresh; at most five a day (AC-F25.4).

    Phase 3 records the request in the queue file. Phase 4's `jobs.request_refresh` and the
    `job_requests` table take over the same entries.
    """
    q: dict[str, Any] = deps.store.load(REFRESH_QUEUE)
    today = q.setdefault(asof.isoformat(), [])
    queued = 0
    for isin in isins:
        if isin in today:
            continue
        if len(today) >= MAX_REFRESH_PER_DAY:
            log.warning("refresh.cap_reached", isin=isin)
            break
        today.append(isin)
        queued += 1
        deps.audit().emit(
            ctx,
            AUD.JOB_REFRESH_REQUESTED,
            entity_type="refresh_request",
            entity_id=isin,
            isin=isin,
            details={"requested_by": "event_watcher", "asof": asof.isoformat()},
        )
    deps.store.save(REFRESH_QUEUE, {k: q[k] for k in sorted(q)[-30:]})
    return queued


# -- digest ------------------------------------------------------------------------------------
def evening_digest(deps: WatchDeps, asof: dt.date) -> JobResult:
    if (why := _skip_reason(deps, asof)) is not None:
        return JobResult("digest", "skipped", why)
    ctx = RunContext.create(
        mode="digest",
        asof=asof,
        actor_type="scheduler",
        actor_id="evening-digest",
        trigger=deps.trigger,
    )
    res = JobResult("digest", "ok", run_id=ctx.run_id)
    try:
        with run_lifecycle(ctx, deps.audit()) as outcome:
            with audited_step(ctx, "flush_digest") as step:
                out = _dispatcher(deps, ctx).flush_digest()
                _tally(res, out)
                step.record_output(sent=res.sent, shadowed=res.shadowed)
            outcome.summary = {"sent": res.sent, "shadowed": res.shadowed}
    except Exception as exc:
        _send_failure(deps, ctx, "Evening digest", exc)
        res.status, res.reason = "failed", f"{type(exc).__name__}: {exc}"
        raise
    return res


# -- heartbeat ---------------------------------------------------------------------------------
def week_runs(today: dt.date, root: Path | None = None) -> list[RunManifest]:
    base = root or runs_dir()
    cutoff = today - dt.timedelta(days=7)
    out: list[RunManifest] = []
    if not base.exists():
        return out
    for path in base.glob("*/manifest.json"):
        try:
            m = RunManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            continue
        if cutoff <= m.asof <= today and m.mode in ("watch", "events", "digest", "monthly"):
            out.append(m)
    return out


def service_level_breaches(deps: WatchDeps, runs: list[RunManifest]) -> list[str]:
    """NFR-14: watcher message by 19:30 IST; a run that ended later is flagged (AC-F19.5)."""
    limit = deps.bundle.notify.service_levels.watcher_by_ist
    hh, mm = (int(x) for x in limit.split(":"))
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    late = []
    for m in runs:
        if m.mode not in ("watch", "events"):
            continue
        end = m.finished_at.astimezone(ist)
        if (end.hour, end.minute) > (hh, mm):
            late.append(f"{m.mode} {m.asof:%d %b} finished {end:%H:%M} IST (limit {limit})")
    return late


def heartbeat(deps: WatchDeps, today: dt.date, runs_root: Path | None = None) -> JobResult:
    ctx = RunContext.create(
        mode="heartbeat",
        asof=today,
        actor_type="scheduler",
        actor_id="heartbeat",
        trigger=deps.trigger,
    )
    res = JobResult("heartbeat", "ok", run_id=ctx.run_id)
    try:
        with run_lifecycle(ctx, deps.audit()) as outcome:
            with audited_step(ctx, "collect") as step:
                runs = week_runs(today, runs_root)
                ok = sum(1 for r in runs if r.status.startswith("SUCCESS"))
                alerts = AlertsLog(deps.store.root / "alerts")
                since = dt.datetime.combine(
                    today - dt.timedelta(days=7), dt.time.min, tzinfo=dt.UTC
                )
                signals = alerts.count(since, "sent") + alerts.count(since, "shadow")
                warnings = [
                    f"{m.mode} {m.asof:%d %b} {m.status}"
                    for m in runs
                    if not m.status.startswith("SUCCESS")
                ]
                warnings += [f"⚠️ {b}" for b in service_level_breaches(deps, runs)]
                step.record_output(runs=len(runs), ok=ok)
            with audited_step(ctx, "send") as step:
                d = _dispatcher(deps, ctx)
                delivery = d.send_message(
                    render_heartbeat(ok, len(runs), signals, warnings, today),
                    code="SYS.HEARTBEAT",
                    severity="Low",
                )
                step.record_output(delivered=delivery.ok)
            outcome.summary = {"runs": len(runs), "ok": ok, "breaches": len(warnings)}
    except Exception as exc:
        _send_failure(deps, ctx, "Sunday heartbeat", exc)
        res.status, res.reason = "failed", f"{type(exc).__name__}: {exc}"
        raise
    return res
