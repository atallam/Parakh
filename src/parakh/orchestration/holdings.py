"""Holdings import job: CAS (quantities) + broker report (cost seed) → restricted tables (F03).

    ctx, outcome, result = import_holdings(statement, cas_sha256, report, writer)

What gets stored (plan 05 §4, plan 13 P6): the statement's period and file hash, positions per
account reference and ISIN, tax lots with settlement dates and cost, and one buy transaction per
lot. Never a name, PAN, DP/client ID or the file itself. Re-importing the same CAS changes
nothing; lots are seeded from the broker report only for an account that has none yet. Every
shortfall the CAS shows becomes a cost-pending lot (AC-F03.6). Audit events carry counts only,
never quantities or costs.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from parakh.adapters.broker_pnl import BrokerPnl
from parakh.adapters.cas import CasStatement
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.ids import new_ulid
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.holdings.lots import (
    Lot,
    ReconRow,
    lots_from_broker,
    match_broker_account,
    pending_lots,
    reconcile,
)


class HoldingsWriter(Protocol):
    def statement_exists(self, file_sha256: str) -> bool: ...
    def lots_for_account(self, account_ref: str) -> list[Lot]: ...
    def write_holdings(self, plan: ImportPlan, run_id: str) -> None: ...


@dataclass
class ImportPlan:
    statement: dict[str, Any] | None  # None when this CAS was imported before
    positions: list[dict[str, Any]] = field(default_factory=list)
    lots: list[Lot] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    account_ref: str | None = None
    recon: list[ReconRow] = field(default_factory=list)
    seeded: bool = False


def lot_row(lot: Lot) -> dict[str, Any]:
    return {
        "lot_id": lot.lot_id,
        "account_ref": lot.account_ref,
        "isin": lot.isin,
        "qty": lot.qty,
        "trade_date": lot.trade_date.isoformat(),
        "settle_date": lot.settle_date.isoformat(),
        "price_inr": lot.price_inr,
        "source": lot.source,
    }


def plan_import(
    statement: CasStatement,
    file_sha256: str,
    report: BrokerPnl | None,
    already_imported: bool,
    existing_lots: list[Lot],
) -> ImportPlan:
    """Pure: what to store for this statement and broker report, given what is stored."""
    plan = ImportPlan(statement=None)
    if not already_imported:
        statement_id = new_ulid()
        plan.statement = {
            "statement_id": statement_id,
            "file_sha256": file_sha256,
            "file_type": statement.file_type if statement.file_type in ("NSDL", "CDSL") else "NSDL",
            "period_from": statement.period_from.isoformat(),
            "period_to": statement.period_to.isoformat(),
        }
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for h in statement.holdings:
            key = (h.account_ref, h.isin)
            row = merged.setdefault(
                key,
                {
                    "statement_id": statement_id,
                    "account_ref": h.account_ref,
                    "isin": h.isin,
                    "kind": h.kind,
                    "qty": 0.0,
                },
            )
            row["qty"] += h.qty
        plan.positions = list(merged.values())

    ref = match_broker_account(statement, report) if report is not None else None
    plan.account_ref = ref
    lots = list(existing_lots)
    if (
        ref is not None
        and report is not None
        and not any(lot.account_ref == ref and lot.source == "broker_pnl" for lot in existing_lots)
    ):
        seed = lots_from_broker(report, ref)
        plan.lots.extend(seed)
        lots.extend(seed)
        plan.seeded = True
    accounts = {lot.account_ref for lot in lots}
    plan.recon = reconcile(statement, lots, accounts)
    if not already_imported:
        plan.lots.extend(pending_lots(plan.recon, statement))
    for lot in plan.lots:
        if lot.price_inr is not None:
            plan.transactions.append(
                {
                    "txn_id": new_ulid(),
                    "lot_id": lot.lot_id,
                    "account_ref": lot.account_ref,
                    "isin": lot.isin,
                    "side": "buy",
                    "qty": lot.qty,
                    "price_inr": lot.price_inr,
                    "trade_date": lot.trade_date.isoformat(),
                    "source": lot.source,
                }
            )
    return plan


@dataclass
class ImportResult:
    statement_new: bool
    positions: int
    lots_added: int
    cost_pending: int
    seeded: bool
    recon: Counter[str]
    in_transit: int


def import_holdings(
    statement: CasStatement,
    file_sha256: str,
    report: BrokerPnl | None,
    writer: HoldingsWriter,
    today: dt.date | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, ImportResult]:
    sink = sink or get_sink()
    ctx = RunContext.create(mode="holdings_import", asof=today)
    with run_lifecycle(ctx, sink) as outcome:
        with audited_step(ctx, "plan_import", file_sha256=file_sha256) as step:
            already = writer.statement_exists(file_sha256)
            # The broker's account is inferred on the first import (quantities equal); later
            # statements differ once you trade, so accounts that already have lots are used.
            ref = match_broker_account(statement, report) if report is not None else None
            existing: list[Lot] = []
            for acct in [ref] if ref else statement.account_refs:
                existing += writer.lots_for_account(acct)
            plan = plan_import(statement, file_sha256, report, already, existing)
            step.record_output(
                rows=len(plan.lots), positions=len(plan.positions), seeded=plan.seeded
            )
        with audited_step(ctx, "write_holdings") as step:
            writer.write_holdings(plan, ctx.run_id)
            step.record_output(rows=len(plan.lots) + len(plan.positions))
        result = ImportResult(
            statement_new=not already,
            positions=len(plan.positions),
            lots_added=len(plan.lots),
            cost_pending=sum(1 for lot in plan.lots if lot.cost_pending),
            seeded=plan.seeded,
            recon=Counter(r.status for r in plan.recon),
            in_transit=sum(1 for r in plan.recon if r.in_transit_qty),
        )
        sink.emit(
            ctx,
            AUD.HOLDINGS_IMPORT,
            entity_type="cas_statement",
            entity_id=file_sha256,
            details={
                "period_to": statement.period_to.isoformat(),
                "statement_new": result.statement_new,
                "positions": result.positions,
                "lots_added": result.lots_added,
                "cost_pending": result.cost_pending,
                "reconciliation": dict(result.recon),
            },
        )
        if result.lots_added:
            sink.emit(
                ctx,
                AUD.HOLDINGS_LOT_ADDED,
                entity_type="holdings_lots",
                details={"lots": result.lots_added, "seeded_from_broker": plan.seeded},
            )
        outcome.summary = {"lots_added": result.lots_added, "statement_new": result.statement_new}
    return ctx, outcome, result
