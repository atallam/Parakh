"""Reference load job: AMFI cap categories and index membership for the universe (plan 05 §3.4).

    ctx, outcome, report = load_reference(bundle, amfi_bytes, {"NIFTY 100": csv_bytes, …}, asof)

Stores, for each security in the universe, its AMFI category (effective the list's period end)
and its membership of each index as of the file date. Membership history starts at the first
load; later loads close a membership (valid_to) when a stock leaves and open one when it joins.
The config's cap bucket must equal AMFI's: a mismatch fails the run's data quality (the config is
then corrected by a reviewed change, never silently).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from parakh.adapters.reference import (
    INDEX_SIZES,
    AmfiList,
    parse_amfi_list,
    parse_index_constituents,
)
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.quality import DqResult, worst


class ReferenceWriter(Protocol):
    def open_memberships(self) -> list[dict[str, Any]]: ...
    def write_reference(
        self, caps: list[dict[str, Any]], joins: list[dict[str, Any]], leaves: list[dict[str, Any]]
    ) -> None: ...


@dataclass
class ReferenceReport:
    amfi_period_end: dt.date | None = None
    caps: list[dict[str, Any]] = field(default_factory=list)
    joins: list[dict[str, Any]] = field(default_factory=list)
    leaves: list[dict[str, Any]] = field(default_factory=list)
    membership: dict[str, list[str]] = field(default_factory=dict)  # isin → indices
    dq: list[DqResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        return worst(self.dq)


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def cap_checks(
    bundle: ConfigBundle, amfi: AmfiList, today: dt.date
) -> tuple[list[dict[str, Any]], list[DqResult]]:
    cfg = bundle.data_quality.reference
    rows, dq = [], []
    by_isin = amfi.by_isin()
    age = (today - amfi.period_end).days
    dq.append(
        DqResult(
            "DQ.reference.amfi_age",
            "*",
            "pass" if age <= cfg.amfi_max_age_days else "fail",
            {"period_end": amfi.period_end.isoformat(), "age_days": age},
        )
    )
    for sec in bundle.universe.pilot:
        row = by_isin.get(sec.isin)
        if row is None:
            dq.append(
                DqResult(
                    "DQ.reference.cap_bucket", sec.isin, "fail", {"reason": "not in the AMFI list"}
                )
            )
            continue
        rows.append(
            {
                "isin": sec.isin,
                "effective_date": amfi.period_end.isoformat(),
                "amfi_rank": row.rank,
                "bucket": row.bucket,
                "source_id": "amfi",
            }
        )
        dq.append(
            DqResult(
                "DQ.reference.cap_bucket",
                sec.isin,
                "pass" if row.bucket == sec.cap else "fail",
                {"config": sec.cap, "amfi": row.bucket, "amfi_rank": row.rank},
            )
        )
    return rows, dq


def membership_changes(
    current: dict[str, set[str]],
    stored_open: list[dict[str, Any]],
    universe: set[str],
    asof: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(joins, leaves) for universe stocks: `current` is index → ISINs in today's files."""
    open_pairs = {(r["index_id"], r["isin"]) for r in stored_open}
    now_pairs = {
        (index, isin) for index, isins in current.items() for isin in isins if isin in universe
    }
    joins = [
        {"index_id": i, "isin": s, "valid_from": asof.isoformat(), "source_id": "niftyindices"}
        for i, s in sorted(now_pairs - open_pairs)
    ]
    leaves = [
        {"index_id": i, "isin": s, "valid_to": asof.isoformat()}
        for i, s in sorted(open_pairs - now_pairs)
        if i in current  # only close a membership when that index's file was loaded
    ]
    return joins, leaves


def load_reference(
    bundle: ConfigBundle,
    amfi_xlsx: bytes | None,
    index_files: dict[str, bytes],
    asof: dt.date | None = None,
    writer: ReferenceWriter | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, ReferenceReport]:
    sink = sink or get_sink()
    ctx = RunContext.create(mode="reference", asof=asof)
    report = ReferenceReport()
    universe = {s.isin for s in bundle.universe.pilot}
    cfg = bundle.data_quality.reference
    with run_lifecycle(ctx, sink) as outcome:
        if amfi_xlsx is not None:
            with audited_step(ctx, "amfi_caps", raw_hash=_sha(amfi_xlsx)) as step:
                amfi = parse_amfi_list(amfi_xlsx)
                report.amfi_period_end = amfi.period_end
                report.caps, dq = cap_checks(bundle, amfi, ctx.asof)
                report.dq += dq
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    step_id=step.record.step_id,
                    details={"source": "amfi", "rows": len(amfi.rows), "raw_hash": _sha(amfi_xlsx)},
                )
                step.record_output(rows=len(amfi.rows), sha256=_sha(amfi_xlsx))
        current: dict[str, set[str]] = {}
        for index_id, data in index_files.items():
            with audited_step(
                ctx, "index_constituents", index=index_id, raw_hash=_sha(data)
            ) as step:
                members = parse_index_constituents(data, index_id)
                current[index_id] = {m.isin for m in members}
                expected = INDEX_SIZES.get(index_id)
                off = abs(len(members) - expected) if expected else 0
                report.dq.append(
                    DqResult(
                        # one check per index: results are keyed (run, check, isin)
                        "DQ.reference.index_size_" + index_id.lower().replace(" ", "_"),
                        "*",
                        "pass"
                        if off == 0
                        else ("warn" if off <= cfg.index_size_tolerance else "fail"),
                        {"index": index_id, "rows": len(members), "expected": expected},
                    )
                )
                sink.emit(
                    ctx,
                    AUD.DATA_FETCH,
                    step_id=step.record.step_id,
                    details={"source": "niftyindices", "index": index_id, "rows": len(members)},
                )
                step.record_output(rows=len(members), sha256=_sha(data))
        for isin in sorted(universe):
            report.membership[isin] = sorted(i for i, isins in current.items() if isin in isins)
        with audited_step(ctx, "write_reference") as step:
            stored = writer.open_memberships() if writer else []
            report.joins, report.leaves = membership_changes(current, stored, universe, ctx.asof)
            if writer is not None:
                writer.write_reference(report.caps, report.joins, report.leaves)
            step.record_output(rows=len(report.caps) + len(report.joins) + len(report.leaves))
        for r in report.dq:
            if r.status == "fail":
                sink.emit(
                    ctx,
                    AUD.DATA_VALIDATION_FAIL,
                    isin=None if r.isin == "*" else r.isin,
                    reason=r.check_id,
                    details=r.detail,
                )
        outcome.summary = {
            "caps": len(report.caps),
            "joins": len(report.joins),
            "leaves": len(report.leaves),
        }
    return ctx, outcome, report
