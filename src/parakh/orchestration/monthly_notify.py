"""After a monthly run: one Telegram summary, one email with segment summaries and an .ics (F11).

    notify_monthly(deps, snapshots, regimes, seconds, calendar_source=feeds)

The summary never waits on the Monthly Reviewer agent: when the review is not ready it says
"🤖 Review pending" and the agent's own message follows later (AC-F25.3). The email goes by SMTP;
if that fails the Telegram message still stands and the failure is logged, not hidden.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import structlog

from parakh.audit.context import RunContext
from parakh.audit.steps import audited_step, run_lifecycle
from parakh.notify.ics import build_ics
from parakh.notify.monthly import (
    CalendarSource,
    build_monthly_email,
    build_monthly_vars,
    calendar_entries,
)
from parakh.notify.templates import render_monthly_summary
from parakh.orchestration.watch_jobs import WatchDeps, _dispatcher, _send_failure

log = structlog.get_logger(__name__)


@dataclass
class MonthlyNotice:
    telegram_ok: bool = False
    email_ok: bool | None = None  # None: email not configured
    calendar_entries: int = 0
    errors: dict[str, str] = field(default_factory=dict)
    run_id: str | None = None


def governance_line(deps: WatchDeps, snapshots: list[dict[str, Any]]) -> str:
    chain = deps.audit().verify_chain()
    parts = ["🛡 Integrity ✅" if chain.ok else "🛡 Integrity ❌ chain broken"]
    known = [s for s in snapshots if s.get("data_quality", {}).get("confidence")]
    if known:
        high = sum(1 for s in known if str(s["data_quality"]["confidence"]).lower() == "high")
        parts.append(f"DQ {round(100 * high / len(known))}% high-confidence")
    return " · ".join(parts)


def notify_monthly(
    deps: WatchDeps,
    snapshots: list[dict[str, Any]],
    regimes: dict[str, str],
    seconds: float,
    *,
    asof: dt.date,
    failed: list[str] | None = None,
    inbox_items: int = 0,
    review_pending: bool = False,
    review_html: str | None = None,
    calendar_source: CalendarSource | None = None,
    today: dt.date | None = None,
) -> MonthlyNotice:
    ctx = RunContext.create(
        mode="monthly-notify",
        asof=asof,
        actor_type="scheduler",
        actor_id="monthly-notify",
        trigger=deps.trigger,
    )
    notice = MonthlyNotice(run_id=ctx.run_id)
    link = f"{deps.bundle.notify.links.report_base}"
    try:
        with run_lifecycle(ctx, deps.audit()) as outcome:
            with audited_step(ctx, "summary") as step:
                v = build_monthly_vars(
                    deps.bundle,
                    snapshots,
                    regimes,
                    seconds,
                    failed=failed,
                    inbox_items=inbox_items,
                    governance=governance_line(deps, snapshots),
                    review_pending=review_pending,
                    link=link,
                )
                d = _dispatcher(deps, ctx)
                delivery = d.send_message(
                    render_monthly_summary(v), code="MONTHLY.SUMMARY", severity="Medium"
                )
                notice.telegram_ok = delivery.ok
                step.record_output(
                    delivered=delivery.ok, upgrades=len(v.upgrades), downgrades=len(v.downgrades)
                )
            if deps.mailer is not None and deps.bundle.notify.channels.email.enabled:
                with audited_step(ctx, "email") as step:
                    attachments: list[tuple[str, bytes, str]] = []
                    if calendar_source is not None:
                        secs = [s for s in deps.bundle.universe.pilot]
                        entries, errs = calendar_entries(calendar_source, secs, today or asof)
                        notice.errors.update({f"calendar:{k}": e for k, e in errs.items()})
                        notice.calendar_entries = len(entries)
                        attachments.append(
                            ("parakh-next-30-days.ics", build_ics(entries), "text/calendar")
                        )
                    subject, html, text = build_monthly_email(
                        deps.bundle, snapshots, v, link, review_html
                    )
                    mail = deps.mailer.send_html(subject, html, text, attachments)
                    notice.email_ok = mail.ok
                    if not mail.ok:
                        notice.errors["email"] = mail.error or "failed"
                    step.record_output(delivered=mail.ok, ics_entries=notice.calendar_entries)
            outcome.summary = {
                "telegram": notice.telegram_ok,
                "email": notice.email_ok,
                "ics": notice.calendar_entries,
            }
    except Exception as exc:
        _send_failure(deps, ctx, "Monthly notification", exc)
        raise
    return notice
