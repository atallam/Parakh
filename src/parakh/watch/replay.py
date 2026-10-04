"""60-day watcher replay for UAT-2 (AC-F12.7; plan 14 §4.5).

    rows = replay_alerts(watcher, calendar, bundle, start, end)
    Path("logs/replay.md").write_text(render_replay(rows, start, end))

Runs the momentum watcher over stored prices day by day from empty state, applies the real
routing and cool-downs with a throwaway alert state, sends nothing and saves nothing, and lists the
alerts it would have sent (and what the cool-down or routing held back), with dates.
"""

from __future__ import annotations

import datetime as dt
import tempfile
from dataclasses import dataclass
from pathlib import Path

from parakh.calendar import Calendar
from parakh.configs import ConfigBundle
from parakh.notify.model import Alert
from parakh.notify.routing import AlertState, Router
from parakh.watch.momentum import MomentumWatcher
from parakh.watch.state import StateStore


@dataclass(frozen=True)
class ReplayRow:
    day: dt.date
    alert: Alert
    action: str  # send_now | digest | suppress
    reason: str


def replay_alerts(
    watcher: MomentumWatcher, calendar: Calendar, bundle: ConfigBundle, start: dt.date, end: dt.date
) -> list[ReplayRow]:
    rows: list[ReplayRow] = []
    with tempfile.TemporaryDirectory() as tmp:
        state = AlertState(StateStore(Path(tmp)))
        router = Router(bundle.notify, calendar, state)
        results = watcher.replay(start, end, calendar)
        for day in sorted(results):
            res = results[day]
            for isin, code in res.rearm:
                state.rearm(isin, code)
            for alert in sorted(
                res.alerts, key=lambda a: (-a.severity.rank, a.symbol or "", a.code)
            ):
                decision = router.decide(alert, day)
                router.commit(alert, decision, day)
                rows.append(ReplayRow(day, alert, decision.action, decision.reason))
    return rows


def render_replay(rows: list[ReplayRow], start: dt.date, end: dt.date) -> str:
    sent = [r for r in rows if r.action != "suppress"]
    out = [
        f"# Watcher replay {start:%d %b %Y} to {end:%d %b %Y}",
        "",
        f"{len(sent)} alert(s) would have been sent or digested; {len(rows) - len(sent)} held back by routing or cool-down.",
        "Nothing was sent and no state was saved.",
        "",
        "| Date | Stock | Signal | Severity | Route | Why |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r.day:%d %b %Y} | {r.alert.symbol} | {r.alert.code} {r.alert.headline} | {r.alert.severity.value} | {r.action} | {r.reason} |"
        )
    return "\n".join(out) + "\n"
