"""Profile-inputs job (plan 13 D24): lease debt and rentals, customer advances, listed stakes.

    ctx, outcome, report = load_profile_inputs(bundle, filings, shp, writer=repo)

Reads only exchange filings (T1): the results XBRL for described lines (`adapters.profile_inputs`)
and the investees' shareholding XBRL for a holding company's stakes. Rows go to `fundamentals`
as `profile.<id>` with the filing's broadcast date as `reported_on`, so they are versioned and
point-in-time like every other fundamental. What a filing does not contain (an order book, an
offer document) is not guessed: it stays a document input for Phase 2.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from parakh.adapters.profile_inputs import described_lines, pick
from parakh.adapters.shareholding import (
    ShareholdingFormatError,
    holder_stake,
    parse_shp_master,
    parse_shp_xbrl,
)
from parakh.adapters.xbrl import Filing
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.configs.models import FilingProfile, StakeRegister
from parakh.quality import DqResult, worst

SOURCE_ID = "nse_archives"


class ResultFilings(Protocol):
    def filings(self, symbol: str) -> list[Filing]: ...
    def xbrl(self, url: str) -> str: ...


class ShpSource(Protocol):
    def shareholding_master(self, symbol: str) -> list[dict[str, Any]]: ...
    def shareholding_xbrl(self, url: str) -> str: ...


class FactWriter(Protocol):
    def write_fundamentals(self, rows: list[dict[str, Any]], run_id: str) -> tuple[int, int]: ...


@dataclass
class ProfileLoad:
    symbol: str
    isin: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    inserted: int = 0
    restated: int = 0
    dq: list[DqResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(self.dq)

    def latest(self) -> dict[str, tuple[str, float]]:
        """metric → (period_end, value) for the newest period of each metric."""
        out: dict[str, tuple[str, float]] = {}
        for r in self.rows:
            if r["metric_id"] not in out or r["period_end"] > out[r["metric_id"]][0]:
                out[r["metric_id"]] = (r["period_end"], r["value"])
        return out


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row(
    isin: str, metric: str, period_end: str, reported_on: str, value: float, unit: str, raw: str
) -> dict[str, Any]:
    return {
        "isin": isin,
        "metric_id": f"profile.{metric}",
        "period_type": "quarter",
        "period_end": period_end,
        "reported_on": reported_on,
        "value": value,
        "unit": unit,
        "source_id": SOURCE_ID,
        "raw_hash": raw,
    }


def filing_item_rows(
    isin: str, symbol: str, profile: FilingProfile, source: ResultFilings, quarters: int
) -> tuple[list[dict[str, Any]], DqResult]:
    want = profile.basis == "consolidated"
    newest: dict[Any, Filing] = {}
    for f in source.filings(symbol):
        if f.consolidated != want:
            continue
        if f.period_end not in newest or f.broadcast_at > newest[f.period_end].broadcast_at:
            newest[f.period_end] = f
    rows: list[dict[str, Any]] = []
    found: dict[str, int] = {item.id: 0 for item in profile.items}
    periods = sorted(newest, reverse=True)[:quarters]
    for period in periods:
        filing = newest[period]
        xml = source.xbrl(filing.xbrl_url)
        lines = [x for x in described_lines(xml) if x.period_end == period]
        for item in profile.items:
            value = pick(lines, item.tag, item.match, item.kind)
            if value is None:
                continue
            found[item.id] += 1
            rows.append(
                _row(
                    isin,
                    item.id,
                    period.isoformat(),
                    filing.broadcast_at.date().isoformat(),
                    value,
                    "cr",
                    _sha(xml),
                )
            )
    missing = sorted(k for k, n in found.items() if n == 0)
    dq = DqResult(
        "DQ.profile.filing_items",
        isin,
        "fail" if missing or not periods else "pass",
        {"filings": len(periods), "found": found, "missing": missing},
    )
    return rows, dq


def stake_rows(
    isin: str, register: StakeRegister, source: ShpSource, quarters: int
) -> tuple[list[dict[str, Any]], DqResult]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for inv in register.investees:
        filings = parse_shp_master(source.shareholding_master(inv.symbol))[:quarters]
        hit_latest = False
        for i, filing in enumerate(filings):
            if not filing.xbrl_url:
                continue
            xml = source.shareholding_xbrl(filing.xbrl_url)
            try:
                scale = parse_shp_xbrl(xml).pct_scale
            except ShareholdingFormatError:
                continue
            stake = holder_stake(xml, register.holder, scale)
            if stake is None:
                continue
            hit_latest = hit_latest or i == 0
            period, when = filing.period_end.isoformat(), filing.reported_on.isoformat()
            raw = _sha(xml)
            rows.append(
                _row(isin, f"stake_pct.{inv.symbol}", period, when, stake.stake_pct, "pct", raw)
            )
            rows.append(
                _row(isin, f"stake_shares.{inv.symbol}", period, when, stake.shares, "count", raw)
            )
        if not hit_latest:
            missing.append(inv.symbol)
    dq = DqResult(
        "DQ.profile.listed_stakes",
        isin,
        "fail" if missing else "pass",
        {"investees": len(register.investees), "missing_in_latest_filing": missing},
    )
    return rows, dq


def load_profile_inputs(
    bundle: ConfigBundle,
    filings: ResultFilings,
    shp: ShpSource,
    writer: FactWriter | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, list[ProfileLoad]]:
    sink = sink or get_sink()
    cfg = bundle.profile_inputs
    ctx = RunContext.create(mode="profile_inputs")
    loads: dict[str, ProfileLoad] = {}
    with run_lifecycle(ctx, sink) as outcome:
        for sec in bundle.universe.pilot:
            profile, register = cfg.filing_items.get(sec.isin), cfg.listed_stakes.get(sec.isin)
            if profile is None and register is None:
                continue
            load = loads.setdefault(sec.isin, ProfileLoad(sec.symbol, sec.isin))
            with audited_step(ctx, "profile_inputs", isin=sec.isin) as step:
                if profile is not None:
                    rows, dq = filing_item_rows(
                        sec.isin, sec.symbol, profile, filings, cfg.quarters
                    )
                    load.rows += rows
                    load.dq.append(dq)
                if register is not None:
                    rows, dq = stake_rows(sec.isin, register, shp, cfg.stake_quarters)
                    load.rows += rows
                    load.dq.append(dq)
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    isin=sec.isin,
                    step_id=step.record.step_id,
                    details={"source": SOURCE_ID, "rows": len(load.rows)},
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
                if writer is not None and load.rows:
                    load.inserted, load.restated = writer.write_fundamentals(load.rows, ctx.run_id)
                step.record_output(rows=len(load.rows), inserted=load.inserted)
        outcome.summary = {
            "securities": len(loads),
            "rows": sum(len(x.rows) for x in loads.values()),
        }
    return ctx, outcome, list(loads.values())
