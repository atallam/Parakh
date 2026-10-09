"""Daily Momentum Watcher: diff today's signals against yesterday's saved state (plan 03 §5).

    watcher = MomentumWatcher(bundle, data, StateStore(root), positions)
    result = watcher.scan(asof)        # alerts on transitions only; saves the new state
    results = watcher.replay(start, end)   # same logic over past days, never saved (AC-F12.7)

Rules (AC-F12):
- the data is checked first: the last bar is the as-of day, closes are positive and finite;
  a stock that fails is reported and left alone, never alerted on stale data (F12.1);
- an alert is a *transition*: a signal that was not active becomes active. Active stays quiet (F12.2);
- a signal that stops firing is cleared and re-armed, so it can fire again at once (F12.3);
- confirmation is the signal's own `confirmed` flag (momentum.yaml, two closes), except the
  leading signals listed in `notify.routing.confirm_closes`, which fire on day 1;
- the very first scan seeds the state silently: nothing is "new" about a signal that was
  already true when the watcher started (F12.4).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import structlog

from parakh.analytics.momentum_build import momentum_inputs
from parakh.analytics.momentum_calc import Calc
from parakh.analytics.signals.momentum import SignalState, evaluate_signals
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.notify.model import Alert, Severity
from parakh.orchestration.analysis_data import AnalysisData
from parakh.watch.state import StateStore

log = structlog.get_logger(__name__)
STATE = "momentum_state"
HISTORY_YEARS = 3  # why: the longest signal window is 52 weeks plus the 200-day average


@dataclass(frozen=True)
class Held:
    weight_pct: float | None
    pnl_pct: float | None


@dataclass
class WatchResult:
    asof: dt.date
    alerts: list[Alert] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # symbol → reason
    scanned: int = 0
    seeded: bool = False  # first scan: state written, no alerts
    rearm: list[tuple[str, str]] = field(default_factory=list)  # (isin, code) that stopped firing


def validate_prices(frame: pd.DataFrame | None, asof: dt.date) -> str | None:
    """None when the frame can be used; otherwise one plain reason."""
    if frame is None or frame.empty:
        return "no price data"
    f = frame.sort_values("trade_date")
    last = pd.Timestamp(f["trade_date"].iloc[-1]).date()
    if last != asof:
        return f"stale: last bar is {last.isoformat()}, expected {asof.isoformat()}"
    tail = f["close"].astype(float).tail(5)
    if any((not math.isfinite(v)) or v <= 0 for v in tail):
        return "zero or missing close in the last 5 sessions"
    return None


class MomentumWatcher:
    def __init__(
        self,
        bundle: ConfigBundle,
        data: AnalysisData,
        store: StateStore,
        positions: dict[str, Held] | None = None,
    ) -> None:
        self.bundle, self.data, self.store = bundle, data, store
        self.positions = positions or {}

    # -- helpers -----------------------------------------------------------------------------
    def _qualifies(self, s: SignalState) -> bool:
        if s.status != "fired":
            return False
        override = self.bundle.notify.routing.confirm_closes.get(s.id)
        return s.confirmed or (override is not None and override <= 1)

    def _signals(self, sec: Security, frame: pd.DataFrame, asof: dt.date) -> list[SignalState]:
        caps = self.bundle.momentum.cap_settings[sec.cap]
        bench = self.data.index_close(caps.benchmark, asof)
        inp = momentum_inputs(
            sec.isin, sec.symbol, sec.cap, asof, frame, self.bundle.momentum, sec.listed_on, bench
        )
        return evaluate_signals(Calc(inp, self.bundle.momentum))

    def _alert(self, sec: Security, s: SignalState, asof: dt.date, top_decile: bool) -> Alert:
        direction = self.bundle.notify.routing.signal_direction.get(s.id, "info")
        held = self.positions.get(sec.isin)
        price = f" · close {s.price:,.2f}" if s.price else ""
        return Alert(
            kind="signal",
            code=s.id,
            severity=Severity(s.severity),
            headline=f"{s.name}{price}",
            asof=asof,
            isin=sec.isin,
            symbol=sec.symbol,
            direction=direction,
            valence="positive" if direction == "entry" else "negative",
            owned=held is not None,
            weight_pct=held.weight_pct if held else None,
            pnl_pct=held.pnl_pct if held else None,
            top_decile=top_decile,
            source="watcher",
            note=None,
        )

    # -- scan --------------------------------------------------------------------------------
    def scan(
        self,
        asof: dt.date,
        securities: list[Security] | None = None,
        *,
        persist: bool = True,
        state: dict[str, Any] | None = None,
    ) -> WatchResult:
        secs = securities if securities is not None else self.bundle.universe.active
        state = state if state is not None else self.store.load(STATE)
        first = not state
        out = WatchResult(asof=asof, seeded=first)
        start = dt.date(asof.year - HISTORY_YEARS, 1, 1)
        for sec in secs:
            try:
                frame = self.data.prices(sec.isin, start, asof)
                problem = validate_prices(frame, asof)
                if problem:
                    out.errors[sec.symbol] = problem
                    continue
                signals = self._signals(sec, frame, asof)
            except Exception as exc:  # one stock never sinks the scan
                out.errors[sec.symbol] = f"{type(exc).__name__}: {exc}"
                continue
            out.scanned += 1
            mine = state.setdefault(sec.isin, {"active": {}, "pending": {}})
            active: dict[str, str] = mine["active"]
            pending: dict[str, str] = mine["pending"]
            for s in signals:
                if s.status == "cannot_evaluate":
                    continue
                if self._qualifies(s):
                    pending.pop(s.id, None)
                    if s.id not in active:
                        active[s.id] = asof.isoformat()
                        if not first:
                            out.alerts.append(self._alert(sec, s, asof, False))
                elif s.status == "fired":
                    pending.setdefault(s.id, asof.isoformat())
                else:
                    pending.pop(s.id, None)
                    if s.id in active:
                        del active[s.id]
                        out.rearm.append((sec.isin, s.id))
            mine["asof"] = asof.isoformat()
        if persist:
            self.store.save(STATE, state)
        return out

    def replay(self, start: dt.date, end: dt.date, calendar: Any) -> dict[dt.date, WatchResult]:
        """The same logic over each trading day, from empty state; nothing is saved."""
        results: dict[dt.date, WatchResult] = {}
        state: dict[str, Any] = {}
        first = True
        for day in calendar.trading_days(start, end):
            if first:
                # seed on the day before `start` so the first replayed day can alert
                seed_day = calendar.previous_trading_day(day)
                self.scan(seed_day, persist=False, state=state)
                first = False
            results[day] = self.scan(day, persist=False, state=state)
        return results
