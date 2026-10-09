"""Fundamentals load job: Screener exports → checked, lineage-stamped facts (+ XBRL tie-out).

    ctx, outcome, loads = load_fundamentals(bundle, exports, filings=NseFilings(api), writer=repo)

For each export it identifies the pilot stock by the COMPANY NAME cell (never the file name),
runs the export checks, stamps every fact with its source and the sha256 of the file, attaches
`reported_on` from the exchange's broadcast time for that quarter (point-in-time scoring, plan
04 §4 #3), cross-checks the latest quarters against the filed XBRL, and hands the rows to a
writer. Exports that match no pilot stock are reported and skipped.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from parakh.adapters.screener_export import ScreenerExport, parse_export
from parakh.adapters.xbrl import (
    Filing,
    first_reported,
    parse_xbrl,
    screener_lines,
    screener_quarter,
)
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.quality import DqResult, worst
from parakh.quality.fundamentals import check_export, check_tieout, match_security, tieout

ANNUAL_SECTIONS = {"annual_pl", "balance_sheet", "cash_flow", "annual_price", "derived"}
UNITS = {"cr": "cr", "inr": "inr", "count": "count", "count_cr": "count_cr"}


class FilingsSource(Protocol):
    def filings(self, symbol: str) -> list[Filing]: ...
    def xbrl(self, url: str) -> str: ...


class FundamentalsWriter(Protocol):
    def write_fundamentals(self, rows: list[dict[str, Any]], run_id: str) -> tuple[int, int]:
        """Insert rows; returns (inserted, restated). Unchanged values are skipped."""
        ...


@dataclass
class FundamentalsLoad:
    isin: str
    symbol: str
    company_name: str
    raw_hash: str
    facts: int = 0
    with_reported_on: int = 0
    inserted: int = 0
    restated: int = 0
    dq: list[DqResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(self.dq)


def fact_rows(
    export: ScreenerExport, isin: str, raw_hash: str, reported: dict[dt.date, dt.datetime]
) -> list[dict[str, Any]]:
    rows = []
    for f in export.facts:
        when = reported.get(f.period_end)
        rows.append(
            {
                "isin": isin,
                "metric_id": f"{f.section}.{f.item}",
                "period_type": "annual" if f.section in ANNUAL_SECTIONS else "quarter",
                "period_end": f.period_end.isoformat(),
                "reported_on": when.date().isoformat() if when else None,
                "value": f.value,
                "unit": UNITS.get(f.unit, "cr"),
                "source_id": "screener_export",
                "raw_hash": raw_hash,
            }
        )
    return rows


def _tieout_quarters(
    export: ScreenerExport,
    filings: list[Filing],
    source: FilingsSource,
    n: int,
    bundle: ConfigBundle,
) -> list[dict[str, Any]]:
    """Compare the latest n quarters, trying consolidated then standalone filings."""
    cfg = bundle.data_quality.fundamentals
    checks = []
    for quarter in export.periods("quarterly_pl")[-n:]:
        screener = screener_quarter(
            {
                f.item: f.value
                for f in export.facts
                if f.section == "quarterly_pl" and f.period_end == quarter
            }
        )
        candidates = sorted(
            (f for f in filings if f.period_end == quarter),
            key=lambda f: (not f.consolidated, f.revised, f.broadcast_at),
        )
        best: dict[str, Any] | None = None
        for filing in candidates:
            mapped = screener_lines(parse_xbrl(source.xbrl(filing.xbrl_url)))
            compared, bad = tieout(screener, mapped, cfg)
            attempt = {
                "quarter": quarter.isoformat(),
                "basis": "consolidated" if filing.consolidated else "standalone",
                "source": filing.source,
                "lines": len(compared),
                "mismatches": bad,
            }
            if best is None or len(bad) < len(best["mismatches"]):
                best = attempt
            if not bad and compared:
                break
        if best is not None:
            checks.append(best)
    return checks


def load_fundamentals(
    bundle: ConfigBundle,
    exports: list[bytes],
    filings: FilingsSource | None = None,
    writer: FundamentalsWriter | None = None,
    today: dt.date | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, list[FundamentalsLoad]]:
    sink = sink or get_sink()
    cfg = bundle.data_quality.fundamentals
    ctx = RunContext.create(mode="fundamentals", asof=today)
    loads: list[FundamentalsLoad] = []
    with run_lifecycle(ctx, sink) as outcome:
        unmatched = 0
        for data in exports:
            raw_hash = "sha256:" + hashlib.sha256(data).hexdigest()
            with audited_step(ctx, "parse_export", raw_hash=raw_hash) as step:
                export = parse_export(data)
                sec: Security | None = match_security(export, bundle.universe.active)
                step.record_output(
                    rows=len(export.facts), company=export.company_name, matched=sec is not None
                )
            if sec is None:
                unmatched += 1
                sink.emit(
                    ctx,
                    AUD.DATA_VALIDATION_FAIL,
                    reason="DQ.fundamentals.unmatched",
                    details={"company": export.company_name, "raw_hash": raw_hash},
                )
                continue
            load = FundamentalsLoad(sec.isin, sec.symbol, export.company_name, raw_hash)
            load.dq = check_export(export, sec, ctx.asof, cfg)

            reported: dict[dt.date, dt.datetime] = {}
            if filings is not None:
                with audited_step(ctx, "xbrl_tieout", isin=sec.isin) as step:
                    listed = filings.filings(sec.symbol)
                    reported = first_reported(listed)
                    checks = _tieout_quarters(export, listed, filings, cfg.xbrl_quarters, bundle)
                    load.dq.append(check_tieout(sec.isin, checks, len(listed)))
                    sink.emit(
                        ctx,
                        AUD.DATA_FETCH,
                        step_id=step.record.step_id,
                        isin=sec.isin,
                        details={
                            "source": "nse_filings",
                            "filings": len(listed),
                            "quarters_compared": len(checks),
                        },
                    )
                    if load.dq[-1].status == "fail":
                        sink.emit(
                            ctx,
                            AUD.DATA_CONFLICT,
                            step_id=step.record.step_id,
                            isin=sec.isin,
                            details=load.dq[-1].detail,
                        )
                    step.record_output(rows=len(checks), status=load.dq[-1].status)

            for r in load.dq:
                if r.status == "fail":
                    sink.emit(
                        ctx,
                        AUD.DATA_VALIDATION_FAIL,
                        isin=sec.isin,
                        reason=r.check_id,
                        details=r.detail,
                    )

            rows = fact_rows(export, sec.isin, raw_hash, reported)
            load.facts = len(rows)
            load.with_reported_on = sum(1 for r in rows if r["reported_on"])
            if writer is not None and not any(
                r.status == "fail" and r.check_id == "DQ.fundamentals.export" for r in load.dq
            ):
                with audited_step(ctx, "write_fundamentals", isin=sec.isin) as step:
                    load.inserted, load.restated = writer.write_fundamentals(rows, ctx.run_id)
                    if load.restated:
                        sink.emit(
                            ctx,
                            AUD.DATA_RESTATEMENT_DETECTED,
                            step_id=step.record.step_id,
                            isin=sec.isin,
                            details={"restated": load.restated},
                        )
                    step.record_output(rows=load.inserted, sha256=raw_hash, restated=load.restated)
            loads.append(load)
        outcome.summary = {
            "exports": len(exports),
            "unmatched": unmatched,
            "facts": sum(x.facts for x in loads),
            "dq": {x.isin: x.status for x in loads},
        }
    return ctx, outcome, loads
