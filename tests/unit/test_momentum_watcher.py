"""Daily Momentum Watcher: validation, transitions, re-arm, seeding, replay (AC-F12.1–F12.7)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from parakh.analytics.signals.momentum import SignalState
from parakh.orchestration.analysis_data import InMemoryData
from parakh.watch.momentum import Held, MomentumWatcher, validate_prices
from parakh.watch.state import StateStore
from tests.helpers.notify import bundle
from tests.helpers.prices import make_prices

D1, D2, D3 = dt.date(2026, 10, 1), dt.date(2026, 10, 5), dt.date(2026, 10, 6)


def _sig(ident: str, status: str, confirmed: bool = True) -> SignalState:
    sev = "High" if ident in {"M21", "M03", "M01"} else "Medium"
    return SignalState(ident, f"{ident} name", sev, status, confirmed, D2, 100.0)


def _watcher(tmp_path, held=None):  # type: ignore[no-untyped-def]
    b = bundle()
    sec = b.universe.pilot[0]
    data = InMemoryData(price_frames={sec.isin: make_prices(400, end=D3, isin=sec.isin)})
    w = MomentumWatcher(b, data, StateStore(tmp_path), held)
    return w, sec


def _script(w, monkeypatch, per_day):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(w, "_signals", lambda sec, frame, asof: per_day[asof])


def test_validation_reasons() -> None:
    ok = make_prices(10, end=D3)
    assert validate_prices(ok, D3) is None
    assert "stale" in (validate_prices(ok, D3 + dt.timedelta(days=1)) or "")
    assert validate_prices(pd.DataFrame(), D3) == "no price data"
    bad = ok.copy()
    bad.loc[bad.index[-2], "close"] = 0.0
    assert "zero" in (validate_prices(bad, D3) or "")
    nan = ok.copy()
    nan.loc[nan.index[-1], "close"] = np.nan
    assert validate_prices(nan, D3) is not None


@pytest.mark.ac("AC-F12.1")
def test_first_scan_seeds_silently_then_transition_alerts_once(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w, sec = _watcher(tmp_path, {})
    _script(
        w,
        monkeypatch,
        {D1: [_sig("M21", "fired")], D2: [_sig("M21", "fired")], D3: [_sig("M21", "fired")]},
    )
    # data ends D3, so scan the days it has bars for
    first = w.scan(D3, persist=True)
    assert first.seeded and first.alerts == []
    again = w.scan(D3)
    assert again.alerts == [], "an active signal stays quiet"


def test_new_signal_alerts_with_ownership_and_direction(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w, sec = _watcher(tmp_path, None)
    w.positions = {}
    w.scan(D3)  # seed (real signals, whatever they are)
    w.positions = {sec.isin: Held(12.0, 18.4)}
    _script(w, monkeypatch, {D3: [_sig("M21", "fired")]})
    # clear any real state so M21 is new
    st = w.store.load("momentum_state")
    st[sec.isin]["active"].pop("M21", None)
    w.store.save("momentum_state", st)
    r = w.scan(D3)
    (a,) = r.alerts
    assert a.code == "M21" and a.direction == "exit" and a.owned and a.weight_pct == 12.0


@pytest.mark.ac("AC-F12.2")
def test_unconfirmed_waits_unless_leading(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w, sec = _watcher(tmp_path)
    w.scan(D3)
    st = w.store.load("momentum_state")
    st[sec.isin] = {"active": {}, "pending": {}}
    w.store.save("momentum_state", st)
    _script(
        w,
        monkeypatch,
        {D3: [_sig("M20", "fired", confirmed=False), _sig("M03", "fired", confirmed=False)]},
    )
    r = w.scan(D3)
    assert [a.code for a in r.alerts] == ["M03"], (
        "M03 is a day-1 leading signal; M20 waits for 2 closes"
    )
    assert "M20" in w.store.load("momentum_state")[sec.isin]["pending"]


def test_cleared_signal_is_rearmed(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    w, sec = _watcher(tmp_path)
    w.scan(D3)
    st = w.store.load("momentum_state")
    st[sec.isin] = {"active": {"M21": D1.isoformat()}, "pending": {}}
    w.store.save("momentum_state", st)
    _script(w, monkeypatch, {D3: [_sig("M21", "not_fired")]})
    r = w.scan(D3)
    assert (sec.isin, "M21") in r.rearm
    assert "M21" not in w.store.load("momentum_state")[sec.isin]["active"]


def test_stale_stock_reported_and_state_untouched(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, sec = _watcher(tmp_path)
    r = w.scan(D3 + dt.timedelta(days=3))
    assert sec.symbol in r.errors and "stale" in r.errors[sec.symbol] and r.scanned == 0


@pytest.mark.ac("AC-F12.7")
def test_replay_never_saves_state(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from parakh.calendar import default_calendar

    w, sec = _watcher(tmp_path)
    cal = default_calendar()
    days = {
        d: [_sig("M21", "fired" if d >= D2 else "not_fired")]
        for d in cal.trading_days(D1 - dt.timedelta(days=5), D3)
    }
    _script(w, monkeypatch, days)
    res = w.replay(D1, D3, cal)
    assert [a.code for a in res[D2].alerts] == ["M21"]
    assert not (tmp_path / "momentum_state.json").exists()
