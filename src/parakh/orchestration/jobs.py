"""Job entry points: each job is a deterministic workflow of audited steps (plan 15 AG-02, P2).

Phase 0 has one job, `dummy`: it proves the skeleton end to end (config validates, the pilot
universe loads keyed by ISIN, audit START/END events are chained, a manifest is written)
without touching the network. The monthly, watch and events jobs arrive in Phases 2–3.
"""

from __future__ import annotations

import datetime as dt

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle, sha256_bytes
from parakh.configs import load_all


def run_dummy(
    asof: dt.date | None = None, sink: AuditSink | None = None
) -> tuple[RunContext, RunOutcome]:
    ctx = RunContext.create(mode="dummy", asof=asof)
    with run_lifecycle(ctx, sink) as outcome:
        with audited_step(ctx, "load_config") as step:
            bundle = load_all()
            step.record_output(files=len(bundle.sources), config_hash=ctx.config_hash)
        with audited_step(ctx, "load_universe", mode=bundle.universe.mode) as step:
            pilot = bundle.universe.pilot
            isins = sorted(s.isin for s in pilot)
            step.record_output(rows=len(pilot), sha256=sha256_bytes("\n".join(isins).encode()))
        with audited_step(ctx, "noop_score") as step:
            step.record_output(rows=0, note="no lenses before Phase 2")
        outcome.summary = {"pilot_stocks": len(pilot)}
    return ctx, outcome
