"""Flows and breadth feeding the regime (AC-F16.1, F16.3 inputs; no estimates)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from parakh.watch.context import (
    FlowStore,
    MarketContext,
    breadth_pct,
    record_breadth,
    regime_kwargs,
)
from parakh.watch.state import StateStore
from tests.helpers.notify import bundle
from tests.helpers.prices import make_prices

FIX = Path(__file__).parent.parent / "fixtures" / "sources" / "nse" / "fii_dii_2026-10-01.json"


def test_real_nse_flows_are_parsed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path)
    fs = FlowStore(store)
    days = fs.record(json.loads(FIX.read_text(encoding="utf-8")))
    assert days == [dt.date(2026, 10, 1)]
    assert fs.data["2026-10-01"] == {"fii_net_cr": -9484.22, "dii_net_cr": 10041.84}
    assert FlowStore(store).data == fs.data, "persisted"


def test_twenty_day_figure_needs_twenty_sessions(tmp_path) -> None:  # type: ignore[no-untyped-def]
    fs = FlowStore(StateStore(tmp_path))
    for i in range(19):
        d = dt.date(2026, 9, 1) + dt.timedelta(days=i)
        fs.data[d.isoformat()] = {"fii_net_cr": -1500.0, "dii_net_cr": 1800.0}
    assert fs.net_20d(dt.date(2026, 10, 1)) == (None, False)
    fs.data["2026-09-25"] = {"fii_net_cr": -1500.0, "dii_net_cr": 1800.0}
    fii, absorbed = fs.net_20d(dt.date(2026, 10, 1))
    assert fii == -30000.0 and absorbed is True


def test_breadth_counts_members_above_200dma() -> None:
    end = dt.date(2026, 9, 30)
    up = make_prices(260, end=end, drift=0.002, vol=0.002, seed=1)
    down = make_prices(260, end=end, drift=-0.002, vol=0.002, seed=2)
    frames = {"A": up, "B": up.copy(), "C": down, "D": up.copy(), "E": up.copy()}
    assert breadth_pct(frames, end) == 0.8


def test_breadth_is_none_when_coverage_is_short() -> None:
    end = dt.date(2026, 9, 30)
    ok = make_prices(260, end=end)
    short = make_prices(50, end=end)
    assert breadth_pct({"A": ok, "B": short, "C": short, "D": short}, end) is None
    assert breadth_pct({}, end) is None


def test_context_loads_notes_and_feeds_regime(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = StateStore(tmp_path)
    asof = dt.date(2026, 10, 1)
    record_breadth(store, asof, {"Large": 0.62, "Mid": None})
    ctx = MarketContext.load(store, asof)
    assert ctx.fii_net_20d_cr is None and ctx.notes
    kw = regime_kwargs(ctx, "Large", bundle().regime)
    assert kw["breadth"] == 0.62 and kw["fii_net_20d_cr"] is None
    assert regime_kwargs(None, "Large", bundle().regime) == {}
