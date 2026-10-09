"""The monthly completion message, email and calendar (plan 03 §4; AC-F11.1, F11.2, F11.7, F11.11).

    vars = build_monthly_vars(bundle, snapshots, regimes, seconds, link, governance)
    msg = render_monthly_summary(vars)                       # one Telegram message, ≤ 10 lines
    subject, html, text = build_monthly_email(bundle, snapshots, vars, report_link)
    entries = calendar_entries(source, securities, today)   # next 30 days → ics.build_ics

Inputs are snapshot dicts (`Snapshot.model_dump(mode="json")`), so this module imports no analytics
or lens code. Amounts never appear: positions come in as weight and P&L percentages.
"""

from __future__ import annotations

import datetime as dt
import html
from typing import Any, Protocol

from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.notify.ics import CalEntry
from parakh.notify.model import Alert, Severity
from parakh.notify.templates import MonthlySummaryVars
from parakh.watch.events import parse_nse_date

HORIZON_DAYS = 30  # why: AC-F11.11, the next 30 days


class CalendarSource(Protocol):
    def event_calendar(self, symbol: str) -> list[dict[str, Any]]: ...
    def board_meetings(self, symbol: str) -> list[dict[str, Any]]: ...
    def corporate_actions(self, symbol: str) -> list[dict[str, Any]]: ...


def _period_label(period: str) -> str:
    y, m = period.split("-")
    return dt.date(int(y), int(m), 1).strftime("%b %Y")


def build_monthly_vars(
    bundle: ConfigBundle,
    snapshots: list[dict[str, Any]],
    regimes: dict[str, str],
    seconds: float,
    *,
    failed: list[str] | None = None,
    inbox_items: int = 0,
    governance: str = "🛡 Integrity ✅",
    review_pending: bool = False,
    link: str | None = None,
    watchlist_line: str | None = None,
) -> MonthlySummaryVars:
    order = bundle.verdict_policy.verdict_order
    rank = {v: i for i, v in enumerate(order)}
    up: list[str] = []
    down: list[str] = []
    owned_attention: list[str] = []
    red_flags: list[str] = []
    dq_warn = unknown = 0
    for s in snapshots:
        v = s["verdict"]
        sym = s["symbol"]
        if v.get("changed") and v.get("prev_verdict") in rank and v["verdict"] in rank:
            label = f"{sym} {v['prev_verdict']}→{v['verdict']}"
            (up if rank[v["verdict"]] < rank[v["prev_verdict"]] else down).append(label)
            if v.get("owned"):
                owned_attention.append(f"{sym} {v.get('prev_action')}→{v.get('action')}")
        elif v.get("owned") and v.get("action") in ("TRIM", "EXIT"):
            owned_attention.append(f"{sym} {v.get('action')}")
        for c in s.get("checks", []):
            if c.get("state") == "FLAGGED":
                red_flags.append(f"{sym}: {c['name']}")
            elif c.get("state") == "UNKNOWN":
                unknown += 1
        dq_warn += sum(
            1
            for c in (s.get("data_quality", {}).get("checks") or [])
            if c.get("severity") in ("warn", "WARN")
        )
    period = snapshots[0]["period"] if snapshots else "—"
    return MonthlySummaryVars(
        period=_period_label(period) if period != "—" else period,
        stocks=len(snapshots),
        seconds=seconds,
        regimes=regimes,
        owned_attention=owned_attention,
        upgrades=up,
        downgrades=down,
        red_flags=red_flags,
        inbox_items=inbox_items,
        data_warnings=dq_warn,
        unknown_checks=unknown,
        governance=governance,
        failed_stocks=failed or [],
        review_pending=review_pending,
        link=link,
        watchlist_line=watchlist_line,
    )


def _chip(snapshot: dict[str, Any]) -> str:
    v = snapshot["verdict"]
    return f"{v['verdict']}" + (f" ({v['qualifier']})" if v.get("qualifier") else "")


def build_monthly_email(
    bundle: ConfigBundle,
    snapshots: list[dict[str, Any]],
    v: MonthlySummaryVars,
    report_link: str,
    review_html: str | None = None,
) -> tuple[str, str, str]:
    """(subject, html, text): segment summaries and links; amounts only if the config allows."""
    esc = html.escape
    subject = f"Parakh · {v.period} monthly analysis · {v.stocks} stocks"
    by_cap: dict[str, list[dict[str, Any]]] = {}
    for s in snapshots:
        by_cap.setdefault(s["cap"], []).append(s)
    parts = [f"<h2>Monthly analysis, {esc(v.period)}</h2>"]
    text = [f"Monthly analysis, {v.period}", ""]
    for cap in sorted(by_cap):
        rows = by_cap[cap]
        regime = v.regimes.get(cap, "—")
        parts.append(
            f"<h3>{esc(cap.title())} cap · {esc(regime)}</h3><table border='1' cellpadding='4' cellspacing='0'>"
        )
        parts.append(
            "<tr><th>Stock</th><th>Verdict</th><th>Value</th><th>Momentum</th><th>Held</th></tr>"
        )
        text.append(f"{cap.title()} cap · {regime}")
        for s in sorted(rows, key=lambda r: r["symbol"]):
            val, mom = s["value"].get("score"), s["momentum"].get("score")
            pos = s.get("position") or {}
            held = (
                f"{pos['weight_pct']:.1f}% · P&L {pos['pnl_pct']:+.1f}%"
                if pos.get("weight_pct") is not None and pos.get("pnl_pct") is not None
                else ("owned" if s["verdict"].get("owned") else "")
            )
            fmt = lambda x: "N/A" if x is None else f"{x:.0f}"  # noqa: E731
            parts.append(
                f"<tr><td><b>{esc(s['symbol'])}</b></td><td>{esc(_chip(s))}</td><td>{fmt(val)}</td><td>{fmt(mom)}</td><td>{esc(held)}</td></tr>"
            )
            text.append(
                f"  {s['symbol']:12} {_chip(s):28} value {fmt(val):>4} momentum {fmt(mom):>4} {held}"
            )
        parts.append("</table>")
        text.append("")
    for title, items in (
        ("Upgrades", v.upgrades),
        ("Downgrades", v.downgrades),
        ("New red flags", v.red_flags),
    ):
        if items:
            parts.append(f"<p><b>{title}:</b> {esc('; '.join(items))}</p>")
            text.append(f"{title}: {'; '.join(items)}")
    if review_html:
        parts.append(f"<h3>Monthly review (agent-written)</h3>{review_html}")
    elif v.review_pending:
        parts.append("<p>🤖 Review pending.</p>")
    parts.append(
        f"<p>Reports: {esc(report_link)}</p><p>The attached calendar file lists results dates, board meetings and ex-dates for the next {HORIZON_DAYS} days.</p>"
    )
    parts.append(f"<p><small>{esc(v.governance)}</small></p>")
    text.append(f"Reports: {report_link}")
    return subject, "".join(parts), "\n".join(text)


def calendar_entries(
    source: CalendarSource,
    securities: list[Security],
    today: dt.date,
    *,
    horizon_days: int = HORIZON_DAYS,
) -> tuple[list[CalEntry], dict[str, str]]:
    """Results dates, board meetings and ex-dates in the next `horizon_days`; errors by symbol."""
    end = today + dt.timedelta(days=horizon_days)
    out: dict[tuple[dt.date, str, str], CalEntry] = {}
    errors: dict[str, str] = {}

    def add(day: dt.date | None, symbol: str, kind: str, title: str, detail: str = "") -> None:
        if day is not None and today <= day <= end:
            out[(day, symbol, kind)] = CalEntry(day, f"{symbol}: {title}", kind, detail)

    for sec in securities:
        try:
            for r in source.event_calendar(sec.symbol):
                purpose = str(r.get("purpose") or "")
                kind = "results" if "result" in purpose.lower() else "board"
                add(
                    parse_nse_date(r.get("date")),
                    sec.symbol,
                    kind,
                    purpose or "board meeting",
                    str(r.get("bm_desc") or ""),
                )
            for r in source.board_meetings(sec.symbol):
                add(
                    parse_nse_date(r.get("bm_date")),
                    sec.symbol,
                    "board",
                    str(r.get("bm_purpose") or "board meeting"),
                    str(r.get("bm_desc") or "")[:300],
                )
            for r in source.corporate_actions(sec.symbol):
                add(
                    parse_nse_date(r.get("exDate")),
                    sec.symbol,
                    "exdate",
                    f"ex-date, {r.get('subject')}",
                )
        except Exception as exc:
            errors[sec.symbol] = f"{type(exc).__name__}: {exc}"
    return sorted(out.values(), key=lambda e: (e.day, e.title)), errors


def thesis_alerts(snapshots: list[dict[str, Any]], asof: dt.date) -> list[Alert]:
    """One alert per thesis status change to WATCH or BROKEN (AC-F23.4)."""
    out: list[Alert] = []
    for s in snapshots:
        th = s.get("thesis") or {}
        old, new = th.get("changed_from"), th.get("status")
        if not old or new not in ("WATCH", "BROKEN"):
            continue
        pos = s.get("position") or {}
        evidence = str(th.get("status_source") or "see the report's Thesis check")
        out.append(
            Alert(
                kind="thesis",
                code=f"THESIS.{new}",
                severity=Severity.HIGH if new == "BROKEN" else Severity.MEDIUM,
                headline=f"thesis {old} to {new}: {evidence}"[:140],
                asof=asof,
                isin=s["isin"],
                symbol=s["symbol"],
                direction="warning",
                valence="negative",
                owned=bool(s["verdict"].get("owned")),
                weight_pct=pos.get("weight_pct"),
                pnl_pct=pos.get("pnl_pct"),
                group=f"{s['period']}-{new}",
                source="monthly",
                extra={"old": old, "new": new, "evidence": evidence},
            )
        )
    return out
