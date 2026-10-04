"""Routing: should this alert go now, wait for the digest, or be suppressed? (plan 03 §0, §4.2).

Ownership-aware rules (plan 03):
- exit and warning signals on a stock you own: immediately, whatever the severity;
- entry signals on a stock you don't own: the digest, unless High *and* the stock is in the top
  decile of its cap by RS percentile; High entry signals on an owned stock: immediately;
- exit or warning signals on a stock you don't own: the digest (nothing to act on);
- events: High immediately, the rest in the digest; thesis status changes on owned stocks:
  immediately; system faults and the monthly review: immediately.

Before routing, an alert can be suppressed: muted (🔕), duplicate inside the cool-down, the same
signal inside the 10-trading-day cool-down (a reversal re-arms it, see `AlertState.rearm`), or an
agent past its daily cap (AG-05). Every suppression is returned with its reason, so it can be
logged: silence must be explainable (plan 10 §14).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from parakh.calendar import Calendar
from parakh.configs.notify_models import NotifyConfig
from parakh.notify.model import Alert, Decision, Severity
from parakh.watch.state import StateStore


class AlertState:
    """Cool-downs, mutes, agent counters and the digest queue, persisted in `alert_state.json`."""

    NAME = "alert_state"

    def __init__(self, store: StateStore) -> None:
        self.store = store
        self.data: dict[str, Any] = store.load(self.NAME)
        for key, default in (
            ("last_sent", {}),
            ("last_dedupe", {}),
            ("muted", []),
            ("agent_counts", {}),
            ("digest", {}),
        ):
            self.data.setdefault(key, default)

    def save(self) -> None:
        self.store.save(self.NAME, self.data)

    # -- cool-downs ----------------------------------------------------------------------------
    def last_sent(self, key: str) -> dt.date | None:
        raw = self.data["last_sent"].get(key)
        return dt.date.fromisoformat(raw) if raw else None

    def last_dedupe(self, key: str) -> dt.date | None:
        raw = self.data["last_dedupe"].get(key)
        return dt.date.fromisoformat(raw) if raw else None

    def mark_sent(self, alert: Alert, day: dt.date) -> None:
        self.data["last_sent"][alert.cooldown_key] = day.isoformat()
        self.data["last_dedupe"][alert.dedupe_key] = day.isoformat()

    def rearm(self, isin: str, code: str) -> None:
        """A signal that reversed may fire again at once (AC-F12.3)."""
        self.data["last_sent"].pop(f"signal:{isin}:{code}", None)

    # -- mutes ---------------------------------------------------------------------------------
    def mute(self, isin: str | None, code: str | None, until: dt.date) -> None:
        self.data["muted"].append({"isin": isin, "code": code, "until": until.isoformat()})

    def muted_until(self, alert: Alert, today: dt.date) -> dt.date | None:
        best: dt.date | None = None
        for m in self.data["muted"]:
            until = dt.date.fromisoformat(m["until"])
            if until < today:
                continue
            if m["isin"] in (None, alert.isin) and m["code"] in (None, alert.code):
                best = max(best, until) if best else until
        return best

    # -- agent counters ------------------------------------------------------------------------
    def agent_count(self, agent: str, day: dt.date) -> int:
        return int(self.data["agent_counts"].get(day.isoformat(), {}).get(agent, 0))

    def bump_agent(self, agent: str, day: dt.date) -> None:
        bucket = self.data["agent_counts"].setdefault(day.isoformat(), {})
        bucket[agent] = int(bucket.get(agent, 0)) + 1
        for old in sorted(self.data["agent_counts"])[:-14]:  # keep two weeks
            del self.data["agent_counts"][old]

    # -- digest --------------------------------------------------------------------------------
    def queue_digest(self, day: dt.date, row: dict[str, Any]) -> None:
        self.data["digest"].setdefault(day.isoformat(), []).append(row)

    def pending_digest(self, up_to: dt.date) -> dict[str, list[dict[str, Any]]]:
        return {
            d: rows for d, rows in sorted(self.data["digest"].items()) if d <= up_to.isoformat()
        }

    def clear_digest(self, days: list[str]) -> None:
        for d in days:
            self.data["digest"].pop(d, None)


@dataclass
class Router:
    config: NotifyConfig
    calendar: Calendar
    state: AlertState

    def _agent(self, alert: Alert) -> str | None:
        return alert.source.split(":", 1)[1] if alert.source.startswith("agent:") else None

    def decide(self, alert: Alert, today: dt.date) -> Decision:
        until = self.state.muted_until(alert, today)
        if until:
            return Decision("suppress", f"muted until {until.isoformat()}")

        agent = self._agent(alert)
        cap = self.config.routing.agent_daily_cap
        if agent and self.state.agent_count(agent, today) >= cap:
            return Decision("suppress", f"agent {agent} reached its daily cap of {cap}")

        cooldown = self.config.routing.cooldown_trading_days
        dup = self.state.last_dedupe(alert.dedupe_key)
        if dup and self.calendar.trading_days_between(dup, today) < cooldown:
            return Decision("suppress", f"duplicate inside the {cooldown}-day cool-down ({dup})")
        if alert.kind == "signal":
            last = self.state.last_sent(alert.cooldown_key)
            if last and self.calendar.trading_days_between(last, today) < cooldown:
                return Decision(
                    "suppress", f"same signal inside the {cooldown}-day cool-down (sent {last})"
                )
        return self._route(alert)

    def _route(self, alert: Alert) -> Decision:
        ntfy = self.config.channels.ntfy.enabled and alert.owned and alert.severity is Severity.HIGH
        if alert.kind in ("system", "review"):
            return Decision("send_now", f"{alert.kind} message")
        if alert.kind == "thesis":
            if alert.owned:
                return Decision("send_now", "thesis status change on an owned stock", ntfy=ntfy)
            return Decision("digest", "thesis status change on a stock you do not own")
        if alert.kind == "event":
            if alert.severity is Severity.HIGH:
                return Decision("send_now", "High-severity event", ntfy=ntfy)
            return Decision("digest", f"{alert.severity.value} event goes in the digest")
        # signals
        if alert.owned and alert.direction in ("exit", "warning"):
            return Decision("send_now", "exit or warning signal on an owned stock", ntfy=ntfy)
        if alert.direction == "entry":
            if alert.owned and alert.severity is Severity.HIGH:
                return Decision("send_now", "High entry signal on an owned stock", ntfy=ntfy)
            if alert.severity is Severity.HIGH and alert.top_decile:
                return Decision("send_now", "High entry signal in the top decile of its cap")
            return Decision("digest", "entry signal goes in the digest")
        return Decision("digest", "no action on a stock you do not own")

    def commit(self, alert: Alert, decision: Decision, today: dt.date) -> None:
        """Record a sent or digested alert so the next call sees it (cool-down, agent cap)."""
        if decision.action == "suppress":
            return
        self.state.mark_sent(alert, today)
        agent = self._agent(alert)
        if agent:
            self.state.bump_agent(agent, today)
