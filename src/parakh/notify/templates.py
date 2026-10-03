"""Message templates v2 (plan 12 §6, plan 03 §4.5; AC-F11.6, AC-F11.7).

Every message:
- is at most 10 lines, the first line saying what happened and why it matters;
- uses the emoji + word vocabulary of config/ui_tokens.yaml (colour is never alone);
- ends each item with *Open ▸*;
- masks amounts unless `notify.include_amounts` is on: weight % and P&L % only;
- marks agent-written text 🤖 and shows it only after `sanitize_note` accepted it (AG-06, UX-14).

Templates take typed values, never free text from outside the code, except an agent's one-line
note, which is checked and clipped. Telegram HTML is escaped here, once, so a company name like
`M&M` can never break a message.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from parakh.notify.model import Alert, Severity
from parakh.notify.telegram import escape
from parakh.render.format import pct
from parakh.render.tokens import label, status

MAX_LINES = 10
NOTE_MAX = 140
_AMOUNT = re.compile(
    r"(₹|\brs\.?\s*\d|\binr\s*\d|\d[\d,\.]*\s*(lakh|lac|crore|cr\b|mn\b|bn\b|million|billion)"
    r"|\b\d[\d,]{2,}\s*(shares|units|qty|quantity)\b)",
    re.I,
)
_URL = re.compile(r"https?://|www\.", re.I)
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Button:
    text: str
    action: str  # u useful · n noise · m mute · a approve · r reject · s snooze
    alert_id: str


@dataclass(frozen=True)
class Message:
    template_id: str
    lines: list[str]  # plain-text lines, already escaped for Telegram HTML
    silent: bool = False
    buttons: list[list[Button]] = field(default_factory=list)
    alert_ids: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def sanitize_note(note: str | None, *, include_amounts: bool = False) -> str | None:
    """An agent's "why it matters" line, or None when it must not be shown (AG-06, AG-07)."""
    if not note:
        return None
    text = _TAGS.sub("", note)
    text = " ".join(text.split())
    if not text or _URL.search(text):
        return None
    if not include_amounts and _AMOUNT.search(text):
        return None
    return text[: NOTE_MAX - 1] + "…" if len(text) > NOTE_MAX else text


def fit_lines(lines: list[str], limit: int = MAX_LINES, keep_tail: int = 1) -> list[str]:
    """Keep the header and the last `keep_tail` lines; fold the middle into '… +N more'."""
    if len(lines) <= limit:
        return lines
    head = lines[: limit - keep_tail - 1]
    tail = lines[len(lines) - keep_tail :] if keep_tail else []
    dropped = len(lines) - len(head) - len(tail)
    return [*head, f"… +{dropped} more", *tail]


def _sev(severity: Severity) -> str:
    return status("severity", severity.value).icon


def lead_icon(alert: Alert) -> str:
    if alert.direction == "entry" or alert.valence == "positive":
        return "🟢"
    return _sev(alert.severity)


def _position_tag(alert: Alert, include_amounts: bool) -> str:
    if not alert.owned:
        return ""
    bits = ["🟢 OWNED"]
    if alert.weight_pct is not None:
        bits.append(f"wt {alert.weight_pct:.1f}%")
    if alert.pnl_pct is not None:
        bits.append(f"P&amp;L {pct(alert.pnl_pct)}")
    return " ".join(bits)


def open_link(alert_link: str | None) -> str:
    return f"Open ▸ {escape(alert_link)}" if alert_link else "Open ▸"


def alert_line(alert: Alert, include_amounts: bool = False, note_ok: bool = True) -> str:
    who = escape(alert.symbol or "—")
    owned = _position_tag(alert, include_amounts)
    parts = [f"{lead_icon(alert)} <b>{who}</b>"]
    if owned:
        parts.append(owned)
    parts.append(f"{alert.code} {escape(alert.headline)}")
    line = " ".join(parts)
    note = sanitize_note(alert.note, include_amounts=include_amounts) if note_ok else None
    if note:
        line += f"\n🤖 {escape(note)}"
    return f"{line}  {open_link(alert.link)}"


def _buttons(alerts: list[Alert], ids: dict[int, str], limit: int = 5) -> list[list[Button]]:
    rows = []
    for i, a in enumerate(alerts[:limit]):
        who = a.symbol or a.code
        aid = ids[i]
        rows.append(
            [
                Button(f"👍 {who}", "u", aid),
                Button(f"👎 {who}", "n", aid),
                Button(f"🔕 {who} 10d", "m", aid),
            ]
        )
    return rows


def render_alerts(
    alerts: list[Alert],
    alert_ids: list[str],
    *,
    day: dt.date,
    title: str = "Momentum change",
    include_amounts: bool = False,
    note_ok: bool = True,
) -> Message:
    """The message for alerts sent now: one header, one line per item, buttons per item."""
    lines = [f"🔔 <b>{escape(title)}</b> — {day.strftime('%d %b %Y')}"]
    for a in alerts:
        lines.extend(alert_line(a, include_amounts, note_ok).split("\n"))
    ids = dict(enumerate(alert_ids))
    return Message(
        "alerts", fit_lines(lines, keep_tail=0), False, _buttons(alerts, ids), list(alert_ids)
    )


def render_digest(
    rows: list[Alert], alert_ids: list[str], *, day: dt.date, include_amounts: bool = False
) -> Message:
    """The evening digest. ⚪-only digests are sent silently (plan 12 §6)."""
    n = len(rows)
    lines = [
        f"🗞 <b>Evening digest</b> — {day.strftime('%d %b %Y')} ({n} item{'s' if n != 1 else ''})"
    ]
    for a in rows:
        lines.extend(alert_line(a, include_amounts).split("\n"))
    quiet = all(a.severity is Severity.LOW for a in rows)
    ids = dict(enumerate(alert_ids))
    return Message(
        "digest", fit_lines(lines, keep_tail=0), quiet, _buttons(rows, ids), list(alert_ids)
    )


def render_failure(job: str, step: str, error: str, run_id: str | None) -> Message:
    err = escape(" ".join(error.split())[:160])
    lines = [
        f"❌ <b>{escape(job)} failed</b> at step <code>{escape(step)}</code>",
        err,
        "Nothing was sent for this run. The next scheduled run tries again.",
    ]
    if run_id:
        lines.append(f"run {escape(run_id)}")
    return Message("failure", lines)


def render_heartbeat(
    ok_runs: int, total_runs: int, signals: int, warnings: list[str], day: dt.date
) -> Message:
    lines = [
        f"💓 <b>Parakh alive</b> — week to {day.strftime('%d %b %Y')}",
        f"{ok_runs}/{total_runs} job runs OK this week · {signals} alert(s)",
    ]
    lines.extend(f"⚠️ {escape(w)}" for w in warnings[:5])
    return Message("heartbeat", fit_lines(lines, keep_tail=0), silent=True)


@dataclass(frozen=True)
class MonthlySummaryVars:
    period: str  # "Oct 2026"
    stocks: int
    seconds: float
    regimes: dict[str, str]  # cap → regime
    owned_attention: list[str]  # "SYMBOL ⚪ HOLD→🟡 TRIM"
    upgrades: list[str]
    downgrades: list[str]
    red_flags: list[str]
    inbox_items: int
    data_warnings: int
    unknown_checks: int
    governance: str  # "🛡 Integrity ✅ · DQ 96% · …"
    failed_stocks: list[str] = field(default_factory=list)
    review_pending: bool = False
    link: str | None = None


def _list_line(prefix: str, items: list[str], limit: int = 4) -> str | None:
    if not items:
        return None
    shown = ", ".join(escape(x) for x in items[:limit])
    more = f" +{len(items) - limit}" if len(items) > limit else ""
    return f"{prefix} ({len(items)}): {shown}{more}"


def render_monthly_summary(v: MonthlySummaryVars) -> Message:
    """One completion message per run (AC-F11.2)."""
    ok = "✅" if not v.failed_stocks else "⚠️"
    minutes, secs = divmod(int(v.seconds), 60)
    lines = [
        f"📊 <b>Monthly Analysis — {escape(v.period)}</b> {ok} "
        f"({v.stocks} stocks, {minutes}m {secs:02d}s)"
    ]
    if v.regimes:
        lines.append(
            "Regime: " + " · ".join(f"{c.title()} {escape(r)}" for c, r in v.regimes.items())
        )
    if v.owned_attention:
        lines.append(
            f"🟢 OWNED: {len(v.owned_attention)} need attention → "
            + " · ".join(escape(x) for x in v.owned_attention[:3])
        )
    for prefix, items in (
        ("⬆️ Upgrades", v.upgrades),
        ("⬇️ Downgrades", v.downgrades),
        ("🚩 New red flags", v.red_flags),
    ):
        line = _list_line(prefix, items)
        if line:
            lines.append(line)
    if v.failed_stocks:
        lines.append(f"⚠️ No verdict for: {escape(', '.join(v.failed_stocks))}")
    lines.append(f"🗂 Review inbox: {v.inbox_items} items")
    if v.data_warnings or v.unknown_checks:
        lines.append(
            f"⚠️ Data: {v.data_warnings} warning(s) · ❔ {v.unknown_checks} checks couldn't run"
        )
    if v.review_pending:
        lines.append("🤖 Review pending")
    lines.append(v.governance)
    lines.append(open_link(v.link))
    # the governance and link lines are never folded away
    return Message("monthly_summary", fit_lines(lines, keep_tail=2))


@dataclass(frozen=True)
class ReviewItem:
    symbol: str
    tag: str  # act | watch | info
    note: str


TAG_ICON = {"act": "🔴", "watch": "🟡", "info": "⚪"}


def render_monthly_review(
    items: list[ReviewItem], *, period: str, include_amounts: bool = False
) -> Message | None:
    """The Monthly Reviewer's short Telegram message: top things to look at (≤ 10 lines)."""
    shown: list[str] = []
    for it in items[:5]:
        note = sanitize_note(it.note, include_amounts=include_amounts)
        if not note:
            continue
        shown.append(f"{TAG_ICON.get(it.tag, '⚪')} <b>{escape(it.symbol)}</b> {escape(note)}")
    if not shown:
        return None
    lines = [f"🤖 <b>Monthly review — {escape(period)}</b> (top {len(shown)} to look at)", *shown]
    lines.append("Full review in the monthly email. Open ▸")
    return Message("monthly_review", fit_lines(lines, keep_tail=1))


def render_thesis_change(
    symbol: str, old: str, new: str, evidence: str, link: str | None, alert_id: str
) -> Message:
    s_new = label(status("thesis", new))
    s_old = label(status("thesis", old))
    lines = [
        f"{status('thesis', new).icon} <b>{escape(symbol)}</b> thesis {escape(s_old)} → {escape(s_new)}",
        f"Evidence: {escape(evidence)}",
        open_link(link),
    ]
    return Message(
        "thesis_status",
        lines,
        False,
        [[Button("👍 Useful", "u", alert_id), Button("👎 Noise", "n", alert_id)]],
        [alert_id],
    )
