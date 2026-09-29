"""Price loading job with fake providers (no network). T-JOB-10…"""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
import pytest

from parakh.adapters.corporate_actions import CorporateAction
from parakh.adapters.prices import PriceSourceError
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.configs.models import Security
from parakh.orchestration.prices import exchange_history, load_prices
from parakh.storage.prices import LocalBlobs, ParquetPriceStore

TODAY = dt.date(2026, 9, 30)
BUNDLE = load_all()


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def _series(isin: str, start: dt.date, end: dt.date, base: float = 100.0) -> pd.DataFrame:
    days = _weekdays(start, end)
    closes = [base * (1 + 0.0002 * i) for i in range(len(days))]
    return pd.DataFrame(
        {
            "isin": isin,
            "trade_date": days,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "adj_close": closes,
            "volume": 1000,
            "source": "yfinance",
        }
    )


class FakePrimary:
    source_id = "yfinance"

    def __init__(self, frames: dict[str, pd.DataFrame], fail: set[str] = frozenset()) -> None:  # type: ignore[assignment]
        self.frames, self.fail = frames, fail

    def history(self, symbol: str, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        if isin in self.fail:
            raise PriceSourceError("yahoo: no rows")
        f = self.frames[isin]
        return pd.DataFrame(f[(f["trade_date"] >= start) & (f["trade_date"] <= end)]).reset_index(
            drop=True
        )


class FakeExchange:
    """Bhavcopy bars per day built from given closes (unadjusted), under the given ISIN."""

    def __init__(self, closes: dict[tuple[str, dt.date], float]) -> None:
        self.closes = closes

    def bars(self, day: dt.date) -> pd.DataFrame | None:
        rows = [
            {
                "isin": i,
                "trade_date": d,
                "symbol": "X",
                "series": "EQ",
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": 10,
                "source": "nse_archives",
            }
            for (i, d), c in self.closes.items()
            if d == day
        ]
        return pd.DataFrame(rows) if rows else None


def _sec(symbol: str, isin: str, listed_on: dt.date | None = None) -> Security:
    base = BUNDLE.universe.by_isin(isin)
    assert base is not None
    return base.model_copy(update={"listed_on": listed_on})


@pytest.fixture
def store(tmp_path):  # type: ignore[no-untyped-def]
    return ParquetPriceStore(LocalBlobs(tmp_path / "blobs"), tmp_path / "cache")


def test_ten_years_loaded_checked_and_written(store: ParquetPriceStore) -> None:
    """T-JOB-10 (AC-F02 exit-gate shape): 10 years, all checks pass, one file per year."""
    mm = BUNDLE.universe.by_isin("INE101A01026")
    assert mm is not None
    frame = _series(mm.isin, dt.date(2016, 9, 1), TODAY)
    last = frame.iloc[-5:]
    exch = FakeExchange({(mm.isin, r.trade_date): r.close for r in last.itertuples()})
    ctx, outcome, loads = load_prices(
        BUNDLE, store, FakePrimary({mm.isin: frame}), exch, today=TODAY, securities=[mm]
    )
    assert outcome.status == "SUCCESS_AUDIT_PENDING"  # no Supabase syncer in tests
    (load,) = loads
    assert load.status == "pass", [r for r in load.dq if r.status != "pass"]
    assert {r.check_id for r in load.dq} == {
        "DQ.prices.schema",
        "DQ.prices.history",
        "DQ.prices.stale",
        "DQ.prices.gaps",
        "DQ.prices.cross_source",
    }
    assert len(load.files) == 11 and load.sha256.startswith("sha256:")
    back = store.query([mm.isin], dt.date(2016, 1, 1), TODAY)
    assert len(back) == load.rows > 2400  # ~250 sessions a year
    types = [e.event_type for e in get_sink().events_for_run(ctx.run_id)]
    assert types.count(AUD.RUN_START) == 1 and types.count(AUD.RUN_END) == 1
    assert AUD.DATA_FETCH in types


def test_young_listing_needs_history_only_since_listing(store: ParquetPriceStore) -> None:
    """T-JOB-11 (D24)."""
    ather = _sec("ATHERENERG", "INE0LEZ01016", dt.date(2025, 5, 6))
    frame = _series(ather.isin, dt.date(2025, 5, 6), TODAY)
    _, _, (load,) = load_prices(
        BUNDLE, store, FakePrimary({ather.isin: frame}), today=TODAY, securities=[ather]
    )
    hist = next(r for r in load.dq if r.check_id == "DQ.prices.history")
    assert hist.status == "pass" and hist.detail["since_listing"] is True


def test_short_or_stale_history_fails(store: ParquetPriceStore) -> None:
    """T-JOB-12"""
    mm = _sec("M&M", "INE101A01026", dt.date(1996, 1, 3))
    frame = _series(mm.isin, dt.date(2024, 1, 1), dt.date(2026, 9, 21))
    ctx, _, (load,) = load_prices(
        BUNDLE, store, FakePrimary({mm.isin: frame}), today=TODAY, securities=[mm]
    )
    status = {r.check_id: r.status for r in load.dq}
    assert status["DQ.prices.history"] == "fail" and status["DQ.prices.stale"] == "fail"
    events = get_sink().events_for_run(ctx.run_id)
    assert sum(e.event_type == AUD.DATA_VALIDATION_FAIL for e in events) == 2


def test_cross_source_mismatch_is_a_conflict(store: ParquetPriceStore) -> None:
    """T-JOB-13"""
    mm = BUNDLE.universe.by_isin("INE101A01026")
    assert mm is not None
    frame = _series(mm.isin, dt.date(2016, 9, 1), TODAY)
    last = frame.iloc[-1]
    exch = FakeExchange({(mm.isin, last.trade_date): last.close * 1.05})
    ctx, _, (load,) = load_prices(
        BUNDLE, store, FakePrimary({mm.isin: frame}), exch, today=TODAY, securities=[mm]
    )
    cross = next(r for r in load.dq if r.check_id == "DQ.prices.cross_source")
    assert cross.status == "fail" and cross.detail["max_diff_pct"] == pytest.approx(
        100 * 0.05 / 1.05, abs=0.001
    )
    assert any(e.event_type == AUD.DATA_CONFLICT for e in get_sink().events_for_run(ctx.run_id))


def test_fallback_rebuilds_from_bhavcopies_across_a_split(store: ParquetPriceStore) -> None:
    """T-JOB-14: Yahoo fails; bhavcopies list the old ISIN before the split and are back-adjusted."""
    mazdock = BUNDLE.universe.by_isin("INE249Z01020")
    assert mazdock is not None and mazdock.previous_isins
    old = mazdock.previous_isins[0].isin
    split = CorporateAction(mazdock.isin, dt.date(2024, 12, 27), "split", 2.0)
    closes = {(old, dt.date(2024, 12, 24)): 4000.0, (old, dt.date(2024, 12, 26)): 4010.0}
    closes[(mazdock.isin, dt.date(2024, 12, 27))] = 2006.0
    frame = exchange_history(
        FakeExchange(closes),
        mazdock.isin,
        {old},
        dt.date(2024, 12, 20),
        dt.date(2024, 12, 31),
        [split],
    )
    assert list(frame["close"]) == [2000.0, 2005.0, 2006.0]
    assert set(frame["isin"]) == {mazdock.isin} and all(math.isnan(x) for x in frame["adj_close"])

    ctx, _, (load,) = load_prices(
        BUNDLE,
        store,
        FakePrimary({}, fail={mazdock.isin}),
        FakeExchange(closes),
        actions_for=lambda _i: [split],
        today=dt.date(2024, 12, 31),
        securities=[mazdock],
    )
    assert load.source == "exchange_bhavcopy" and load.rows == 3
    types = [e.event_type for e in get_sink().events_for_run(ctx.run_id)]
    assert AUD.DATA_FALLBACK_USED in types
