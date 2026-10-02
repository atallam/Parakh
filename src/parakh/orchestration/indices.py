# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Index series loader (benchmarks and India VIX) → the price store under `IDX-<NAME>` keys.

A wrong Yahoo symbol returns nothing, and that fails loudly with the symbol named, so an empty
benchmark can never pass as a flat one (plan 02 §2).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd

from parakh.adapters.prices import PriceSourceError
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.orchestration.analysis_data import index_key
from parakh.storage.prices import PRICE_COLUMNS, ParquetPriceStore

Fetch = Callable[[str, dt.date, dt.date], pd.DataFrame]


def fetch_yahoo_raw(
    symbol: str, start: dt.date, end: dt.date
) -> pd.DataFrame:  # pragma: no cover - network
    import yfinance as yf

    h = yf.Ticker(symbol).history(
        start=start.isoformat(),
        end=(end + dt.timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        raise_errors=True,
    )
    if h.empty:
        raise PriceSourceError(f"yahoo: no rows for index symbol {symbol}")
    return h


def to_frame(history: pd.DataFrame, key: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex(history.index)
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Kolkata").tz_localize(None)
    h = history.copy()
    h.index = idx
    h = h[h["Close"].notna()]
    close = h["Close"].astype(float).to_numpy()
    vol = h["Volume"].fillna(0).astype("int64").to_numpy() if "Volume" in h else 0
    return pd.DataFrame(
        {
            "isin": key,
            "trade_date": [d.date() for d in h.index],
            "open": h["Open"].astype(float).to_numpy(),
            "high": h["High"].astype(float).to_numpy(),
            "low": h["Low"].astype(float).to_numpy(),
            "close": close,
            "adj_close": close,
            "volume": vol,
            "source": "yfinance",
        }
    )[PRICE_COLUMNS]


def load_indices(
    bundle: ConfigBundle,
    store: ParquetPriceStore,
    fetch: Fetch = fetch_yahoo_raw,
    today: dt.date | None = None,
    years: int = 11,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, dict[str, int]]:
    sink = sink or get_sink()
    ctx = RunContext.create(mode="indices", asof=today)
    start = dt.date(ctx.asof.year - years, ctx.asof.month, 1)
    rows: dict[str, int] = {}
    with run_lifecycle(ctx, sink) as outcome:
        for spec in bundle.indices.indices:
            with audited_step(ctx, "fetch_index", index=spec.name, symbol=spec.yahoo) as step:
                frame = to_frame(fetch(spec.yahoo, start, ctx.asof), index_key(spec.name))
                store.write(frame)
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    step_id=step.record.step_id,
                    details={"index": spec.name, "source": "yfinance", "rows": len(frame)},
                )
                step.record_output(rows=len(frame))
                rows[spec.name] = len(frame)
        outcome.summary = {"indices": rows}
    return ctx, outcome, rows
