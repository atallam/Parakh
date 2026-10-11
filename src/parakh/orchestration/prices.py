"""Price loading job: primary (Yahoo) → fallback (exchange bhavcopies) → checks → Parquet store.

    ctx, outcome, loads = load_prices(bundle, store, primary=YahooPrimary(), exchange=archive)

For each pilot stock (keyed by ISIN) it fetches the required history (10 years, or since listing),
checks it (schema, history, staleness, gaps), compares the latest sessions with the exchange
close, writes one Parquet file per year, and records lineage (path, sha256, rows) plus DQ
results. Every fetch, fallback and failed check is an audit event (plan 10 §14).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from parakh.adapters.corporate_actions import CorporateAction, back_adjust
from parakh.adapters.prices import PriceSourceError, apply_price_adjustments, cross_check_closes
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.quality import DqResult, worst
from parakh.quality.prices import check_cross_source, check_prices, required_start
from parakh.storage.prices import PRICE_COLUMNS, ParquetPriceStore


class PrimaryPrices(Protocol):
    source_id: str

    def history(self, symbol: str, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame: ...


class ExchangeBars(Protocol):
    def bars(self, day: dt.date) -> pd.DataFrame | None:
        """The day's bhavcopy as an exchange frame, or None (holiday, weekend, not published)."""
        ...


class YahooPrimary:  # pragma: no cover - network
    source_id = "yfinance"

    def history(self, symbol: str, isin: str, start: dt.date, end: dt.date) -> pd.DataFrame:
        from parakh.adapters.prices import fetch_yahoo

        return fetch_yahoo(symbol, isin, start, end)


@dataclass
class PriceLoad:
    isin: str
    symbol: str
    source: str
    rows: int = 0
    first: dt.date | None = None
    last: dt.date | None = None
    files: list[str] = field(default_factory=list)
    sha256: str = ""
    dq: list[DqResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(self.dq)


def frame_sha256(frame: pd.DataFrame) -> str:
    """A stable hash of a price frame's contents (lineage; plan 10 §6)."""
    canon = (
        pd.DataFrame(frame[PRICE_COLUMNS])
        .sort_values(by=["isin", "trade_date"])
        .to_csv(index=False)
    )
    return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()


def _weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def exchange_history(
    exchange: ExchangeBars,
    isin: str,
    aliases: set[str],
    start: dt.date,
    end: dt.date,
    actions: list[CorporateAction],
) -> pd.DataFrame:
    """Fallback history from bhavcopies, back-adjusted to today's share structure.

    `aliases` are earlier ISINs of the same security (isin_history): bhavcopies before a split
    list the old ISIN. adj_close is left empty (bhavcopies carry no dividend adjustment).
    """
    wanted = {isin, *aliases}
    rows = []
    for day in _weekdays(start, end):
        bars = exchange.bars(day)
        if bars is None or bars.empty:
            continue
        hit = bars[bars["isin"].isin(sorted(wanted))]
        if not hit.empty:
            rows.append(hit.iloc[0])
    if not rows:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    raw = pd.DataFrame(rows)
    frame = pd.DataFrame(
        {
            "isin": isin,
            "trade_date": list(raw["trade_date"]),
            "open": raw["open"].astype(float).to_numpy(),
            "high": raw["high"].astype(float).to_numpy(),
            "low": raw["low"].astype(float).to_numpy(),
            "close": raw["close"].astype(float).to_numpy(),
            "adj_close": float("nan"),
            "volume": raw["volume"].astype("int64").to_numpy(),
            "source": list(raw["source"]),
        }
    )
    splits = [a for a in actions if a.type in ("split", "bonus")]
    for col in ("open", "high", "low", "close"):
        adjusted = back_adjust(dict(zip(frame["trade_date"], frame[col], strict=True)), splits)
        frame[col] = [adjusted[d] for d in frame["trade_date"]]
    return frame.reset_index(drop=True)


def _recent_exchange(exchange: ExchangeBars, days: list[dt.date], wanted: set[str]) -> pd.DataFrame:
    frames = []
    for day in days:
        bars = exchange.bars(day)
        if bars is not None and not bars.empty:
            frames.append(pd.DataFrame(bars[bars["isin"].isin(sorted(wanted))]))
    return pd.concat(frames) if frames else pd.DataFrame(columns=["trade_date", "close"])


def load_prices(
    bundle: ConfigBundle,
    store: ParquetPriceStore,
    primary: PrimaryPrices,
    exchange: ExchangeBars | None = None,
    actions_for: Callable[[str], list[CorporateAction]] = lambda _isin: [],
    today: dt.date | None = None,
    securities: list[Security] | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, list[PriceLoad]]:
    sink = sink or get_sink()
    cfg = bundle.data_quality.prices
    ctx = RunContext.create(mode="prices", asof=today)
    today = ctx.asof
    loads: list[PriceLoad] = []
    with run_lifecycle(ctx, sink) as outcome:
        for sec in securities or bundle.universe.active:
            aliases = {p.isin for p in sec.previous_isins}
            start = required_start(today, cfg.history_years, sec.listed_on)
            actions = actions_for(sec.isin)
            load = PriceLoad(sec.isin, sec.symbol, primary.source_id)
            with audited_step(ctx, "fetch_prices", isin=sec.isin, start=start.isoformat()) as step:
                try:
                    frame = primary.history(sec.symbol, sec.isin, start, today)
                except (PriceSourceError, OSError, ValueError) as exc:
                    if exchange is None:
                        raise
                    sink.emit(
                        ctx,
                        AUD.DATA_FALLBACK_USED,
                        step_id=step.record.step_id,
                        isin=sec.isin,
                        reason=f"{primary.source_id} failed: {type(exc).__name__}",
                        details={"fallback": "exchange_bhavcopy"},
                    )
                    frame = exchange_history(exchange, sec.isin, aliases, start, today, actions)
                    load.source = "exchange_bhavcopy"
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    step_id=step.record.step_id,
                    isin=sec.isin,
                    details={"source": load.source, "rows": len(frame)},
                )
                step.record_output(rows=len(frame), source=load.source)

            if load.source == primary.source_id and cfg.manual_adjustments:
                frame, notes = apply_price_adjustments(frame, sec.isin, cfg.manual_adjustments)
                for note in notes:
                    sink.emit(
                        ctx,
                        AUD.DATA_CORP_ACTION_APPLIED,
                        isin=sec.isin,
                        reason="manual price adjustment",
                        details={"note": note},
                    )
            with audited_step(ctx, "check_prices", isin=sec.isin) as step:
                load.dq = check_prices(frame, sec.isin, today, sec.listed_on, actions, cfg)
                if exchange is not None and not frame.empty:
                    recent = sorted(frame["trade_date"])[-cfg.cross_check_sessions :]
                    exch = _recent_exchange(exchange, recent, {sec.isin, *aliases})
                    later = [a for a in actions if a.ex_date > recent[0]]
                    checks = cross_check_closes(frame, exch, later, cfg.close_mismatch_pct)
                    load.dq.append(check_cross_source(sec.isin, checks, cfg))
                    if any(not c.ok for c in checks):
                        sink.emit(
                            ctx,
                            AUD.DATA_CONFLICT,
                            step_id=step.record.step_id,
                            isin=sec.isin,
                            details=load.dq[-1].detail,
                        )
                for r in load.dq:
                    if r.status == "fail":
                        sink.emit(
                            ctx,
                            AUD.DATA_VALIDATION_FAIL,
                            step_id=step.record.step_id,
                            isin=sec.isin,
                            reason=r.check_id,
                            details=r.detail,
                        )
                step.record_output(status=load.status, checks=len(load.dq))

            if not frame.empty and not any(
                r.status == "fail" and r.check_id == "DQ.prices.schema" for r in load.dq
            ):
                with audited_step(ctx, "write_prices", isin=sec.isin) as step:
                    load.files = store.write(frame)
                    load.sha256 = frame_sha256(frame)
                    load.rows = len(frame)
                    load.first, load.last = min(frame["trade_date"]), max(frame["trade_date"])
                    step.record_output(rows=load.rows, sha256=load.sha256, files=len(load.files))
            loads.append(load)
        outcome.summary = {
            "stocks": len(loads),
            "rows": sum(x.rows for x in loads),
            "dq": {x.isin: x.status for x in loads},
        }
    return ctx, outcome, loads
