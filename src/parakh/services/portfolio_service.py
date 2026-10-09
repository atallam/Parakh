"""Owned positions, theses and the approvals inbox as view models (plan 15 §4.2; AG-07).

Positions are masked by default: weight % and P&L % only. Quantities, cost and ₹ values appear only
when the caller is not an agent and asks for `detail` (AC-F24.4). Every function reads snapshots and
the watchlist store; none of them changes anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from parakh.services.report_service import _stamp, resolve
from parakh.services.view_models import (
    PendingItem,
    PendingOut,
    PositionRow,
    PositionsOut,
    ThesisBreaker,
    ThesisKeyMetric,
    ThesisOut,
)
from parakh.snapshots.store import (
    all_stock_dirs,
    periods_for,
    read_snapshot_dict,
    snapshot_path,
    stock_dir,
)
from parakh.thesis.model import read_thesis
from parakh.watchlist.proposals import LocalProposalStore
from parakh.watchlist.repository import WatchlistRepository

CAPS = ("large", "mid", "small")


def latest_snapshots(root: Path | None = None) -> list[dict[str, Any]]:
    """The newest snapshot of every stock (owned or not), across the three cap folders."""
    out: list[dict[str, Any]] = []
    for cap in CAPS:
        for folder in all_stock_dirs(cap, root):
            snaps = folder / "snapshots"
            files = sorted(snaps.glob("*.json")) if snaps.exists() else []
            if files and (s := read_snapshot_dict(files[-1])):
                out.append(s)
    return out


def positions(detail: bool = False, root: Path | None = None) -> PositionsOut:
    owned = [s for s in latest_snapshots(root) if s["verdict"].get("owned") and s.get("position")]
    if not owned:
        return PositionsOut(
            stamp=_stamp(), found=False, message="No owned stocks in the snapshots."
        )
    owned.sort(key=lambda s: -(s["position"].get("weight_pct") or 0))
    rows = []
    for s in owned:
        p = s["position"]
        row = PositionRow(
            symbol=s["symbol"],
            isin=s["isin"],
            cap=s["cap"],
            verdict=s["verdict"].get("action") or s["verdict"]["verdict"],
            weight_pct=p.get("weight_pct"),
            pnl_pct=p.get("pnl_pct"),
            days_to_long_term=p.get("days_to_long_term"),
            cost_pending=bool(p.get("cost_pending")),
            thesis_status=(s.get("thesis") or {}).get("status", "NOT_SET"),
        )
        if detail:
            row.quantity = p.get("quantity")
            row.avg_cost_inr = p.get("avg_cost_inr")
            row.market_value_inr = p.get("market_value_inr")
            row.pnl_inr = p.get("pnl_inr")
        rows.append(row)
    return PositionsOut(
        stamp=_stamp(owned[0]),
        found=True,
        masked=not detail,
        weight_basis=owned[0]["position"].get("weight_basis"),
        rows=rows,
    )


def get_thesis(symbol_or_isin: str, root: Path | None = None) -> ThesisOut:
    sec = resolve(symbol_or_isin, root)
    if sec is None:
        return ThesisOut(
            stamp=_stamp(), found=False, message=f"{symbol_or_isin} is not in the universe."
        )
    periods = periods_for(sec.cap, sec.symbol, root)
    snap = (
        read_snapshot_dict(snapshot_path(sec.cap, sec.symbol, periods[-1], root))
        if periods
        else None
    )
    block = (snap or {}).get("thesis", {})
    parsed = read_thesis(stock_dir(sec.cap, sec.symbol, root) / "THESIS.md")
    if not parsed.exists or parsed.front is None:
        return ThesisOut(
            stamp=_stamp(snap), found=True, symbol=sec.symbol, isin=sec.isin, status="NOT_SET",
            message="No valid THESIS.md for this stock." + (f" ({parsed.errors[0]})" if parsed.errors else ""),
        )  # fmt: skip
    f = parsed.front
    return ThesisOut(
        stamp=_stamp(snap),
        found=True,
        symbol=sec.symbol,
        isin=sec.isin,
        status=block.get("status", "NOT_SET"),
        status_source=block.get("status_source"),
        original_statement=f.original.statement,
        key_metrics=[ThesisKeyMetric(id=k.id, text=k.text) for k in f.key_metrics],
        breakers=[
            ThesisBreaker(id=b.id, text=b.text, check=b.check, rule=b.rule) for b in f.breakers
        ],
        review_by=f.review_by,
        review_due=bool(block.get("review_due")),
    )


def pending_approvals(
    repo: WatchlistRepository, proposals: LocalProposalStore | None = None
) -> PendingOut:
    state = repo.load()
    items = [
        PendingItem(
            kind="suggestion",
            id=s.sugg_id,
            symbol=s.symbol,
            action=s.action,
            origin=s.origin,
            reason=s.reason[:240],
            expires_on=s.expires_on,
            sources=s.sources,
        )  # fmt: skip
        for s in state.pending()
    ]
    for p in (proposals or LocalProposalStore()).pending():
        if p.payload.get("sugg_id"):
            continue  # already shown as a suggestion
        items.append(
            PendingItem(
                kind="proposal",
                id=p.proposal_id,
                symbol=p.payload.get("symbol"),
                action=str(p.payload.get("action") or p.kind),
                origin=p.client,
                reason=p.reason[:240],
            )  # fmt: skip
        )
    return PendingOut(stamp=_stamp(), items=items)
