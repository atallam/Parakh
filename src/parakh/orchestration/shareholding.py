"""Shareholding load job: quarterly pattern and promoter pledge for the universe (plan 01 §3).

    ctx, outcome, report = load_shareholding(bundle, fetcher, writer=repo)

For each security: list the exchange's shareholding filings, read the XBRL of the latest N
quarters not stored yet, and store one row per (ISIN, quarter end, filing date). A revised filing
is a new row, never an update, so a score for a past date sees only what was public then
(AC-F02.3). The promoter % in the XBRL must equal the exchange's own
summary for the same filing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Protocol

from parakh.adapters.shareholding import (
    Shareholding,
    ShareholdingFormatError,
    ShpFiling,
    parse_shp_master,
    parse_shp_xbrl,
)
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.quality import DqResult, worst

SOURCE_ID = "nse_archives"


class ShpFetcher(Protocol):
    def shareholding_master(self, symbol: str) -> list[dict[str, Any]]: ...
    def shareholding_xbrl(self, url: str) -> str: ...


class ShpWriter(Protocol):
    def stored_shareholding(self, isin: str) -> list[dict[str, Any]]: ...
    def write_shareholding(self, rows: list[dict[str, Any]]) -> None: ...


@dataclass
class ShpLoad:
    symbol: str
    isin: str
    filings: int = 0
    added: int = 0
    latest: dict[str, Any] | None = None  # newest quarter, stored or just read
    quarters: int = 0  # quarters held after this load
    dq: list[DqResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(self.dq)


@dataclass
class ShpReport:
    loads: list[ShpLoad] = field(default_factory=list)

    @property
    def dq(self) -> list[DqResult]:
        return [r for load in self.loads for r in load.dq]

    @property
    def status(self) -> str:
        return worst(self.dq)


def shareholding_row(
    isin: str, filing: ShpFiling, shp: Shareholding, run_id: str
) -> dict[str, Any]:
    return {
        "isin": isin,
        "period_end": shp.period_end.isoformat(),
        "reported_on": filing.reported_on.isoformat(),
        "total_shares": shp.total_shares,
        "promoter_shares": shp.promoter_shares,
        "public_shares": shp.public_shares,
        "fii_shares": shp.fii_shares,
        "dii_shares": shp.dii_shares,
        "mf_shares": shp.mf_shares,
        "promoter_pledged_shares": shp.promoter_pledged_shares,
        "promoter_encumbered_shares": shp.promoter_encumbered_shares,
        "promoter_pct": shp.promoter_pct,
        "public_pct": shp.public_pct,
        "fii_pct": shp.fii_pct,
        "dii_pct": shp.dii_pct,
        "mf_pct": shp.mf_pct,
        "pledge_pct": shp.pledge_pct,
        "encumbered_pct": shp.encumbered_pct,
        "source_id": SOURCE_ID,
        "raw_hash": shp.raw_hash,
        "run_id": run_id,
    }


def _load_one(
    bundle: ConfigBundle,
    symbol: str,
    isin: str,
    fetcher: ShpFetcher,
    stored: list[dict[str, Any]],
    ctx: RunContext,
) -> tuple[ShpLoad, list[dict[str, Any]]]:
    cfg = bundle.data_quality.shareholding
    load = ShpLoad(symbol, isin)
    filings = parse_shp_master(fetcher.shareholding_master(symbol))
    load.filings = len(filings)
    have = {(r["period_end"], r["reported_on"]) for r in stored}
    rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for filing in filings[: cfg.quarters]:
        key = (filing.period_end.isoformat(), filing.reported_on.isoformat())
        if key in have or not filing.xbrl_url:
            continue  # stored before: no second download (AC-F02.5)
        try:
            shp = parse_shp_xbrl(fetcher.shareholding_xbrl(filing.xbrl_url))
        except ShareholdingFormatError:
            unreadable.append(filing.period_end.isoformat())
            continue
        if shp.period_end != filing.period_end:
            unreadable.append(filing.period_end.isoformat())
            continue
        if (
            filing.promoter_pct is not None
            and abs(shp.promoter_pct - filing.promoter_pct) > cfg.promoter_tolerance_pp
        ):
            mismatches.append(
                {
                    "period_end": key[0],
                    "xbrl_pct": shp.promoter_pct,
                    "exchange_pct": filing.promoter_pct,
                }
            )
        rows.append(shareholding_row(isin, filing, shp, ctx.run_id))
    held = sorted([*stored, *rows], key=lambda r: (r["period_end"], r["reported_on"]))
    periods = {r["period_end"] for r in held}
    load.added, load.quarters = len(rows), len(periods)
    load.latest = held[-1] if held else None
    load.dq.append(
        DqResult(
            "DQ.shareholding.readable",
            isin,
            "fail" if unreadable else "pass",
            {"unreadable": unreadable},
        )
    )
    load.dq.append(
        DqResult(
            "DQ.shareholding.promoter_tieout",
            isin,
            "fail" if mismatches else "pass",
            {"checked": len(rows), "mismatches": mismatches[:5]},
        )
    )
    expected = min(cfg.quarters, len(filings))
    load.dq.append(
        DqResult(
            "DQ.shareholding.coverage",
            isin,
            "pass" if load.quarters >= expected and load.quarters > 0 else "fail",
            {"quarters": load.quarters, "expected": expected},
        )
    )
    if load.latest is not None:
        age = (ctx.asof - dt.date.fromisoformat(load.latest["period_end"])).days
        load.dq.append(
            DqResult(
                "DQ.shareholding.freshness",
                isin,
                "pass" if age <= cfg.max_latest_age_days else "warn",
                {"period_end": load.latest["period_end"], "age_days": age},
            )
        )
    return load, rows


def load_shareholding(
    bundle: ConfigBundle,
    fetcher: ShpFetcher,
    symbols: list[str] | None = None,
    asof: dt.date | None = None,
    writer: ShpWriter | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, ShpReport]:
    sink = sink or get_sink()
    ctx = RunContext.create(mode="shareholding", asof=asof)
    report = ShpReport()
    with run_lifecycle(ctx, sink) as outcome:
        for sec in bundle.universe.pilot:
            if symbols and sec.symbol not in symbols:
                continue
            with audited_step(ctx, "shareholding", isin=sec.isin) as step:
                stored = writer.stored_shareholding(sec.isin) if writer else []
                load, rows = _load_one(bundle, sec.symbol, sec.isin, fetcher, stored, ctx)
                if writer is not None and rows:
                    writer.write_shareholding(rows)
                report.loads.append(load)
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    isin=sec.isin,
                    step_id=step.record.step_id,
                    details={"source": SOURCE_ID, "filings": load.filings, "rows": load.added},
                )
                for r in load.dq:
                    if r.status == "fail":
                        sink.emit(
                            ctx,
                            AUD.DATA_VALIDATION_FAIL,
                            isin=sec.isin,
                            reason=r.check_id,
                            details=r.detail,
                        )
                step.record_output(rows=load.added, quarters=load.quarters)
        outcome.summary = {
            "securities": len(report.loads),
            "rows": sum(x.added for x in report.loads),
        }
    return ctx, outcome, report
