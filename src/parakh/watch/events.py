"""Event Watcher: exchange filings, insider trades, surveillance, deals, lock-ins (plan 03 §5b; F13).

    watcher = EventWatcher(bundle, store, positions)
    result = watcher.scan(asof, securities, source)   # alerts once per filing; state saved

Rules live in `config/events.yaml` and the first matching rule wins (AC-F13.2). A rule decides
whether a filing matters and its highest severity; text it cannot read fails loud (an alert, never
silence). Each filing alerts exactly once because every alert's dedupe key goes into
`events_seen.json` (AC-F13.1). A source that fails is reported and the filing stays unseen, so the
next run retries it (AC-F13.4). Filings that call for a fresh analysis come back in
`refresh_isins`; the job turns those into `job_requests` (AC-F13.3, F25.5).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from parakh.calendar import Calendar
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.configs.notify_models import EventRule
from parakh.notify.model import Alert, Severity
from parakh.watch.docs import DocStore
from parakh.watch.history import SignalLog
from parakh.watch.history import entry as history_entry
from parakh.watch.momentum import Held
from parakh.watch.state import StateStore

log = structlog.get_logger(__name__)
STATE = "events_seen"
SEEN_KEEP_DAYS = (
    120  # why: the API window is days; four months of memory covers any re-published row
)


class EventSource(Protocol):
    def announcements(self, symbol: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]: ...
    def insider(self, symbol: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]: ...
    def asm(self) -> list[dict[str, Any]]: ...
    def gsm(self) -> list[dict[str, Any]]: ...
    def deals(self, day: dt.date) -> list[dict[str, Any]]: ...


@dataclass
class EventResult:
    asof: dt.date
    alerts: list[Alert] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # source/symbol → reason
    refresh_isins: list[str] = field(default_factory=list)
    seen_new: int = 0


def parse_nse_date(text: str | None) -> dt.date | None:
    if not text or text.strip() in ("-", ""):
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return dt.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _matches(patterns: list[str], text: str) -> list[bool]:
    return [re.search(p, text) is not None for p in patterns]


class Matched:
    def __init__(self, rule: EventRule, severity: Severity, valence: str, group: str) -> None:
        self.rule, self.severity, self.valence, self.group = rule, severity, valence, group


def match_announcement(rules: list[EventRule], row: dict[str, Any]) -> Matched | None:
    desc = str(row.get("desc") or "").strip().lower()
    text = str(row.get("attchmntText") or "")
    for rule in rules:
        if rule.source != "announcement":
            continue
        if rule.desc_any and desc not in rule.desc_any:
            continue
        if rule.text_any and not any(_matches(rule.text_any, text)):
            continue
        if rule.text_all and not all(_matches(rule.text_all, text)):
            continue
        if rule.text_none and any(_matches(rule.text_none, text)):
            continue
        sev = Severity(rule.severity)
        valence: str = rule.valence
        if rule.escalate_if and any(_matches(rule.escalate_if, text)):
            sev = Severity(rule.max_severity)
        if rule.relax_if and any(_matches(rule.relax_if, text)):
            sev, valence = Severity.MEDIUM.capped(Severity(rule.max_severity)), "positive"
        group = str(row.get("seq_id") or row.get("an_dt") or text[:40])
        if rule.group_regex:
            m = re.search(rule.group_regex, text)
            if m:
                group = re.sub(r"\W+", "", m.group(1)).lower()
        return Matched(rule, sev, valence, group)
    return None


def match_insider(rules: list[EventRule], row: dict[str, Any]) -> Matched | None:
    category = str(row.get("personCategory") or "").lower()
    mode = str(row.get("acqMode") or "").lower()
    text = f"{row.get('acqMode') or ''} {row.get('remarks') or ''} {row.get('tdpTransactionType') or ''}"
    for rule in rules:
        if rule.source != "insider":
            continue
        if rule.person_categories and not any(
            c.lower() in category for c in rule.person_categories
        ):
            continue
        if rule.acq_modes and not any(m.lower() in mode for m in rule.acq_modes):
            continue
        sev, valence = Severity(rule.severity), str(rule.valence)
        if rule.relax_if and any(_matches(rule.relax_if, text)):
            sev, valence = Severity.MEDIUM.capped(Severity(rule.max_severity)), "positive"
        elif rule.id == "E03":  # direction of a promoter trade decides the colour
            tx = str(row.get("tdpTransactionType") or "").lower()
            valence = (
                "positive"
                if "buy" in tx or "acqui" in tx
                else ("negative" if "sell" in tx else "neutral")
            )
        group = str(row.get("did") or row.get("pid") or row.get("xbrl") or text)
        return Matched(rule, sev, valence, group)
    return None


class EventWatcher:
    def __init__(
        self,
        bundle: ConfigBundle,
        store: StateStore,
        positions: dict[str, Held] | None = None,
        calendar: Calendar | None = None,
    ) -> None:
        self.bundle, self.store = bundle, store
        self.positions = positions or {}
        self.calendar = calendar or Calendar.from_config(bundle.holidays)
        self.rules = bundle.events.rules

    def _rule(self, rule_id: str) -> EventRule:
        return self.bundle.events.rule(rule_id)

    def _alert(
        self,
        sec: Security,
        m: Matched,
        asof: dt.date,
        headline: str,
        extra: dict[str, Any],
    ) -> Alert:
        held = self.positions.get(sec.isin)
        return Alert(
            kind="event",
            code=m.rule.id,
            severity=m.severity,
            headline=headline,
            asof=asof,
            isin=sec.isin,
            symbol=sec.symbol,
            direction="info",
            valence=m.valence,  # type: ignore[arg-type]
            owned=held is not None,
            weight_pct=held.weight_pct if held else None,
            pnl_pct=held.pnl_pct if held else None,
            group=m.group,
            source="events",
            extra={
                "rule": m.rule.id,
                "max_severity": m.rule.max_severity,
                "refresh": m.rule.refresh,
                **extra,
            },
        )

    # -- scan --------------------------------------------------------------------------------
    def scan(
        self,
        asof: dt.date,
        securities: list[Security],
        source: EventSource,
        *,
        persist: bool = True,
    ) -> EventResult:
        seen: dict[str, str] = self.store.load(STATE)
        out = EventResult(asof=asof)
        start = asof - dt.timedelta(days=self.bundle.events.lookback_days)
        by_symbol = {s.symbol: s for s in securities}
        candidates: list[Alert] = []

        for sec in securities:
            self._announcements(sec, start, asof, source, candidates, out)
            self._insider(sec, start, asof, source, candidates, out)
        self._surveillance(by_symbol, asof, source, candidates, out)
        self._deals(by_symbol, asof, source, candidates, out)
        candidates.extend(self._lockins(securities, asof))

        for alert in candidates:
            key = alert.dedupe_key
            if key in seen:
                continue
            seen[key] = asof.isoformat()
            out.seen_new += 1
            out.alerts.append(alert)
            if alert.extra.get("refresh") and alert.isin and alert.isin not in out.refresh_isins:
                out.refresh_isins.append(alert.isin)

        if persist:
            SignalLog(self.store).append(
                [
                    history_entry(
                        key=a.dedupe_key,
                        isin=a.isin,
                        symbol=a.symbol,
                        code=a.code,
                        headline=a.headline,
                        asof=asof,
                        kind=a.kind,
                    )
                    for a in out.alerts
                ]
            )
            DocStore(self.store).put_many(
                {
                    a.dedupe_key: {
                        "text": a.extra.get("text") or a.headline,
                        "filing_url": a.extra.get("filing_url"),
                        "filed": a.extra.get("filed") or asof.isoformat(),
                        "rule": a.code,
                    }
                    for a in out.alerts
                },
                asof,
            )
        cutoff = (asof - dt.timedelta(days=SEEN_KEEP_DAYS)).isoformat()
        seen = {k: v for k, v in seen.items() if v >= cutoff}
        if persist:
            self.store.save(STATE, seen)
        return out

    # -- sources -----------------------------------------------------------------------------
    def _announcements(self, sec, start, asof, source, sink, out) -> None:  # type: ignore[no-untyped-def]
        try:
            rows = source.announcements(sec.symbol, start, asof)
        except Exception as exc:
            out.errors[f"announcements:{sec.symbol}"] = f"{type(exc).__name__}: {exc}"
            return
        for row in rows:
            day = parse_nse_date(row.get("an_dt") or row.get("sort_date"))
            if day is None or day < start or day > asof:
                continue
            m = match_announcement(self.rules, row)
            if m is None:
                continue
            text = str(row.get("attchmntText") or "").strip()
            headline = f"{m.rule.name}: {_clip(text.replace(sec.name, sec.symbol), 90)}"
            sink.append(
                self._alert(
                    sec,
                    m,
                    asof,
                    headline,
                    {
                        "filing_url": row.get("attchmntFile"),
                        "text": text,
                        "filed": day.isoformat(),
                        "desc": row.get("desc"),
                    },
                )
            )

    def _insider(self, sec, start, asof, source, sink, out) -> None:  # type: ignore[no-untyped-def]
        try:
            rows = source.insider(sec.symbol, start, asof)
        except Exception as exc:
            out.errors[f"insider:{sec.symbol}"] = f"{type(exc).__name__}: {exc}"
            return
        for row in rows:
            day = parse_nse_date(row.get("intimDt") or row.get("date"))
            if day is None or day < start or day > asof:
                continue
            m = match_insider(self.rules, row)
            if m is None:
                continue
            qty = row.get("secAcq") or "?"
            who = str(row.get("acqName") or "promoter group")
            headline = f"{m.rule.name}: {row.get('acqMode')}, {qty} shares ({who})"
            sink.append(
                self._alert(
                    sec, m, asof, headline, {"filed": day.isoformat(), "xbrl": row.get("xbrl")}
                )
            )

    def _surveillance(self, by_symbol, asof, source, sink, out) -> None:  # type: ignore[no-untyped-def]
        rule = self._rule("E08")
        try:
            asm_rows = source.asm()
            gsm_rows = source.gsm()
        except Exception as exc:
            out.errors["surveillance"] = f"{type(exc).__name__}: {exc}"
            return
        flat: list[tuple[str, str, str]] = []  # symbol, list name, stage text
        for row in _asm_rows(asm_rows):
            flat.append(
                (
                    str(row.get("symbol")),
                    "ASM",
                    str(row.get("asmSurvIndicator") or row.get("survDesc") or ""),
                )
            )
        for row in gsm_rows:
            flat.append(
                (
                    str(row.get("symbol")),
                    "GSM",
                    str(row.get("gsmStage") or row.get("survDesc") or ""),
                )
            )
        for symbol, lst, stage in flat:
            sec = by_symbol.get(symbol)
            if sec is None:
                continue
            m = Matched(
                rule,
                Severity(rule.severity),
                rule.valence,
                f"{lst}-{re.sub(r'\W+', '', stage).lower()}",
            )
            sink.append(
                self._alert(sec, m, asof, f"{lst} list: {stage}", {"list": lst, "stage": stage})
            )

    def _deals(self, by_symbol, asof, source, sink, out) -> None:  # type: ignore[no-untyped-def]
        rule = self._rule("E10")
        try:
            rows = source.deals(self.calendar.previous_trading_day(asof + dt.timedelta(days=1)))
        except Exception as exc:
            out.errors["deals"] = f"{type(exc).__name__}: {exc}"
            return
        for row in rows:
            sec = by_symbol.get(str(row.get("symbol")))
            if sec is None:
                continue
            side = str(row.get("buySell") or "").title()
            group = f"{row.get('date')}-{row.get('clientName')}-{side}-{row.get('qty')}"
            m = Matched(
                rule, Severity(rule.severity), rule.valence, re.sub(r"\W+", "", group).lower()[:60]
            )
            sink.append(
                self._alert(
                    sec,
                    m,
                    asof,
                    f"Bulk or block deal: {side} {row.get('qty')} @ {row.get('watp')} ({_clip(str(row.get('clientName')), 36)})",
                    {"client": row.get("clientName")},
                )
            )

    def _lockins(self, securities: list[Security], asof: dt.date) -> list[Alert]:
        cfg = self.bundle.events
        rule = self._rule("E11")
        out: list[Alert] = []
        for sec in securities:
            if sec.listed_on is None or (asof - sec.listed_on).days > cfg.lockin_max_age_days:
                continue
            for step in cfg.lockin_schedule:
                due = sec.listed_on + dt.timedelta(days=step.days_after_listing)
                if due < asof:
                    continue
                if self.calendar.trading_days_between(asof, due) <= cfg.lockin_warn_trading_days:
                    m = Matched(
                        rule, Severity(rule.severity), rule.valence, f"{step.days_after_listing}d"
                    )
                    out.append(
                        self._alert(
                            sec,
                            m,
                            asof,
                            f"Lock-in expiry expected {due.strftime('%d %b %Y')}: {step.label} (check the prospectus)",
                            {"due": due.isoformat()},
                        )
                    )
        return out


def _asm_rows(block: Any) -> list[dict[str, Any]]:
    """NSE's ASM response nests rows under `longterm` and `shortterm` → `data`."""
    if isinstance(block, list):
        return block
    rows: list[dict[str, Any]] = []
    if isinstance(block, dict):
        for part in block.values():
            if isinstance(part, dict):
                rows.extend(part.get("data") or [])
    return rows


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"
