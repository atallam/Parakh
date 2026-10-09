"""The monthly analysis run (plan 09 Phase 2): data → regime → lenses → verdict → files.

    result = run_monthly(bundle, data, asof=date(2026, 9, 30))

Each stock is one audited step; a stock that fails is recorded and skipped, never silently
dropped, and the run still finishes for the others (AC-F21.1). Snapshots are written first and
everything else (reports, history, segment summary) is rendered from them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from parakh.analytics.pipeline import (
    RunMeta,
    StockRequest,
    StockResult,
    analyse_stock,
)
from parakh.analytics.regime import RegimeResult, segment_regime
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle, sha256_bytes
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.holdings.position import positions_from_lots
from parakh.lenses.momentum import MomentumLens
from parakh.lenses.value import ValueLens
from parakh.orchestration.analysis_data import AnalysisData
from parakh.policy.overrides import expired_since
from parakh.snapshots.models import Snapshot, period_of
from parakh.snapshots.store import load_previous, stock_dir, write_snapshot
from parakh.thesis.model import read_thesis
from parakh.watch.context import MarketContext, regime_kwargs

HISTORY_YEARS = 11
VALUE_LENS_VERSION = ValueLens.lens_version
MOMENTUM_LENS_VERSION = MomentumLens.lens_version


@dataclass
class StockOutcome:
    symbol: str
    isin: str
    snapshot: Snapshot | None = None
    path: Path | None = None
    error: str | None = None


@dataclass
class MonthlyResult:
    ctx: RunContext
    outcome: RunOutcome
    stocks: list[StockOutcome] = field(default_factory=list)
    regimes: dict[str, RegimeResult] = field(default_factory=dict)
    output_root: Path | None = None

    @property
    def snapshots(self) -> list[Snapshot]:
        return [s.snapshot for s in self.stocks if s.snapshot is not None]


def _as_date(i) -> dt.date:  # type: ignore[no-untyped-def]
    return i.date() if hasattr(i, "date") else i


def _regimes(
    bundle: ConfigBundle, data: AnalysisData, asof: dt.date, context: MarketContext | None = None
) -> tuple[dict, dict]:
    vix = data.index_close("INDIA VIX", asof)
    out: dict[str, RegimeResult] = {}
    benches = {}
    for cap, settings in bundle.momentum.cap_settings.items():
        name = settings.benchmark
        bench = data.index_close(name, asof)
        benches[cap] = bench
        out[cap] = segment_regime(
            bench, bundle.regime, vix=vix, **regime_kwargs(context, cap, bundle.regime)
        )
    return out, benches


def _lineage(frame, fundamentals: list[dict], shareholding: list[dict]) -> dict:
    from parakh.orchestration.prices import frame_sha256

    prices = {"rows": 0}
    if frame is not None and not frame.empty:
        prices = {
            "rows": len(frame),
            "first": str(min(frame["trade_date"])),
            "last": str(max(frame["trade_date"])),
            "sha256": frame_sha256(frame),
            "source": ",".join(sorted({str(s) for s in frame["source"].unique()})),
        }
    sources = sorted({str(r.get("source_id")) for r in fundamentals if r.get("source_id")})
    runs = sorted({str(r.get("run_id")) for r in fundamentals if r.get("run_id")})
    return {
        "prices": prices,
        "fundamentals": {"rows": len(fundamentals), "sources": sources, "runs": runs[-3:]},
        "shareholding": {"rows": len(shareholding)},
    }


def run_monthly(
    bundle: ConfigBundle,
    data: AnalysisData,
    asof: dt.date,
    out_root: Path | None = None,
    securities: list[Security] | None = None,
    sink: AuditSink | None = None,
    trigger: str = "manual",
    context: MarketContext | None = None,
) -> MonthlyResult:
    sink = sink or get_sink()
    ctx = RunContext.create(mode="monthly", asof=asof, trigger=trigger)
    ctx.lens_versions = {"value": VALUE_LENS_VERSION, "momentum": MOMENTUM_LENS_VERSION}
    ctx.policy_version = bundle.verdict_policy.policy_version
    result = MonthlyResult(ctx, RunOutcome(), output_root=out_root)
    meta = RunMeta(
        asof=asof,
        run_id=ctx.run_id,
        code_version=ctx.code_version,
        config_hash=ctx.config_hash,
        now=dt.datetime.now(dt.UTC),
    )
    sec_list = securities or bundle.universe.active
    with run_lifecycle(ctx, sink) as outcome:
        result.outcome = outcome
        with audited_step(ctx, "regime") as step:
            regimes, benches = _regimes(bundle, data, asof, context)
            result.regimes = regimes
            step.record_output(**{cap: r.regime for cap, r in regimes.items()})

        start = dt.date(asof.year - HISTORY_YEARS, 1, 1)
        frames = {s.isin: data.prices(s.isin, start, asof) for s in sec_list}
        closes = {}
        for isin, f in frames.items():
            try:
                if f is not None and not f.empty:
                    closes[isin] = float(f.sort_values("trade_date")["close"].iloc[-1])
            except (KeyError, ValueError, TypeError):
                continue  # a broken price frame is reported for that stock below, not for the run
        sec_cap = {sec.isin: sec.cap for sec in sec_list}
        bench_series = {
            cap: {_as_date(i): float(v) for i, v in b.dropna().items()}
            for cap, b in benches.items()
            if b is not None and len(b)
        }
        positions = positions_from_lots(
            data.open_lots(), closes, asof, bundle.portfolio.tax,
            cap_of=sec_cap, bench_series=bench_series,
        )  # fmt: skip

        for sec in sec_list:
            so = StockOutcome(sec.symbol, sec.isin)
            result.stocks.append(so)
            with audited_step(ctx, "analyse_stock", isin=sec.isin, symbol=sec.symbol) as step:
                try:
                    frame = frames[sec.isin]
                    fund = data.fundamentals(sec.isin)
                    shp = data.shareholding(sec.isin)
                    req = StockRequest(
                        sec=sec,
                        prices=frame,
                        fundamentals=fund,
                        shareholding=shp,
                        bench=benches.get(sec.cap),
                        regime=regimes[sec.cap],
                        thesis=read_thesis(stock_dir(sec.cap, sec.symbol, out_root) / "THESIS.md"),
                        position=positions.get(sec.isin),
                        prev=load_previous(sec.cap, sec.symbol, period_of(asof), out_root),
                        lineage=_lineage(frame, fund, shp),
                        dq=data.dq(sec.isin),
                    )
                    res: StockResult = analyse_stock(req, bundle, meta)
                    so.snapshot = res.snapshot
                    so.path = write_snapshot(res.snapshot, out_root)
                    for event_type, payload in res.events:
                        payload = dict(payload)
                        sink.emit(
                            ctx,
                            event_type,
                            step_id=step.record.step_id,
                            isin=sec.isin,
                            before=payload.pop("before", None),
                            after=payload.pop("after", None),
                            reason=payload.pop("rule", None),
                            details=payload,
                        )
                    step.record_output(
                        verdict=res.snapshot.verdict["verdict"],
                        snapshot=sha256_bytes(so.path.read_bytes()),
                    )
                except Exception as exc:  # one stock never sinks the run
                    so.error = f"{type(exc).__name__}: {exc}"
                    step.record_output(error=so.error)

        for ov in expired_since(bundle.overrides, _prev_asof(result, asof), asof):
            sink.emit(
                ctx,
                AUD.OVERRIDE_EXPIRED,
                isin=ov.isin,
                details={
                    "field": ov.field,
                    "value": ov.value,
                    "expired_on": ov.expires_on.isoformat(),
                },
            )
        outcome.summary = {
            "stocks": len(result.stocks),
            "ok": sum(1 for s in result.stocks if s.snapshot),
            "failed": {s.symbol: s.error for s in result.stocks if s.error},
        }
    return result


def _prev_asof(result: MonthlyResult, asof: dt.date) -> dt.date | None:
    """The previous run's as-of: the latest earlier snapshot date seen for any stock."""
    dates = []
    for s in result.stocks:
        if s.snapshot is None:
            continue
        prev = load_previous(s.snapshot.cap, s.symbol, s.snapshot.period, result.output_root)
        if prev:
            dates.append(dt.date.fromisoformat(prev["asof"]))
    return max(dates) if dates else None
