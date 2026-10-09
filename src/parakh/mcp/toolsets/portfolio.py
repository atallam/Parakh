"""TOOL.portfolio.*: positions (masked), theses, the approvals inbox and three propose tools.

Reads are tier R; the `propose_*` tools are tier P and write a proposal row only (AG-03). Nothing
here approves, rejects, edits a holding or changes a thesis. An agent is refused `detail: true`, and the
refusal is logged `AUD.MCP.TOOL_DENIED` (AC-F24.4).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from parakh.configs import load_all
from parakh.mcp.middleware import ToolDenied
from parakh.mcp.registry import ToolCall, Toolset
from parakh.services import portfolio_service
from parakh.services.report_service import resolve
from parakh.services.view_models import PendingOut, PositionsOut, ProposalOut, ThesisOut
from parakh.services.watchlist import WatchlistError, WatchlistService, default_resolver
from parakh.watch.state import StateStore
from parakh.watchlist.proposals import LocalProposalStore, Proposal
from parakh.watchlist.repository import LocalWatchlistRepository

PORTFOLIO = Toolset("portfolio", version="0.1.0")


class PositionsIn(BaseModel):
    detail: bool = Field(
        default=False,
        description="true adds quantity, average cost and ₹ values. Only the owner's own Claude Desktop or Claude Code client may ask; an agent asking is refused.",
    )


@PORTFOLIO.tool("positions", tier="R", title="Owned stocks")
def positions(params: PositionsIn, call: ToolCall) -> PositionsOut:
    """List the stocks the owner holds, largest weight first: weight % of the holdings that have a
    loaded price, P&L %, days until the next lot turns long term, whether the cost is still pending,
    the verdict wording (ADD, HOLD, TRIM, EXIT) and the thesis status.

    Quantities, costs and ₹ amounts are not returned unless `detail` is true, and an agent may never
    set it. Use it to ask "what do I own and how is it doing?". Percentages are plain percent
    (4.2 means 4.2%). It reads the latest snapshots and recomputes nothing.
    """
    if params.detail and call.is_agent:
        raise ToolDenied("agents may not request holdings detail (AG-07)")
    return portfolio_service.positions(detail=params.detail)


class GetThesisIn(BaseModel):
    symbol_or_isin: str = Field(description="NSE symbol (e.g. INDIGO) or ISIN.")


@PORTFOLIO.tool("get_thesis", tier="R", title="A stock's thesis")
def get_thesis(params: GetThesisIn, call: ToolCall) -> ThesisOut:
    """Return the owner's structured thesis for one stock: the original statement, up to five key
    metrics (KM1…KM5), up to five exit conditions (BR1…BR5, each `metric` or `llm_flag`), the review
    date and the current status (INTACT, WATCH, BROKEN, NOT_SET) with where that status came from.

    Use it before judging a transcript or a filing against the thesis. It never returns holdings. A stock
    without a thesis comes back NOT_SET; do not invent one. Only the owner edits the thesis.
    """
    return portfolio_service.get_thesis(params.symbol_or_isin)


class PendingIn(BaseModel):
    pass


@PORTFOLIO.tool("pending_approvals", tier="R", title="Open suggestions and proposals")
def pending_approvals(params: PendingIn, call: ToolCall) -> PendingOut:
    """List what is waiting for the owner's decision: watchlist suggestions (from the rules or from an
    agent, with their expiry) and agent proposals not yet turned into suggestions.

    Use it before proposing, so you don't repeat something already open. You cannot approve or reject
    anything; decisions are made in the Streamlit app, on Telegram or on the command line.
    """
    return portfolio_service.pending_approvals(LocalWatchlistRepository(StateStore()))


def _service(call: ToolCall) -> WatchlistService:
    from parakh.audit.context import RunContext

    bundle = load_all()
    return WatchlistService(
        LocalWatchlistRepository(StateStore()), bundle,
        RunContext.create(mode="mcp-propose", actor_type="agent", actor_id=call.client.split(":")[-1]),
        resolver=default_resolver(bundle),
    )  # fmt: skip


class ProposeWatchlistIn(BaseModel):
    action: Literal["add_my", "remove_my", "promote"] = Field(
        description="add_my: suggest adding a stock to My Watchlist. remove_my: suggest removing one from it. promote: suggest moving a System Watchlist entry to My Watchlist."
    )
    symbol_or_isin: str = Field(description="NSE symbol or ISIN of a stock in the universe.")
    reason: str = Field(
        min_length=15,
        max_length=240,
        description="One or two plain sentences why, for the owner to read. No amounts, no links, no instructions.",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        max_length=6,
        description="parakh:// resource URIs or report paths that support the reason, for example parakh://stock/INE646L01027/report/2026-10.",
    )


@PORTFOLIO.tool("propose_watchlist", tier="P", title="Propose a watchlist change")
def propose_watchlist(params: ProposeWatchlistIn, call: ToolCall) -> ProposalOut:
    """Propose a watchlist change for the owner to approve. It writes a proposal and nothing else: the
    monthly job turns valid proposals into pending suggestions marked 🤖, applying the same capacity,
    minimum-stay and expiry rules as the rule-based ones, and the owner approves or rejects them.

    Use it for a stock you judge worth a deep dive (add_my), one whose reason to be watched has gone
    (remove_my), or a System entry that has earned a place (promote). Check `pending_approvals` first:
    a stock with an open suggestion is dropped. You cannot add, remove or promote anything yourself.
    """
    try:
        p = _service(call).propose(
            action=params.action,
            query=params.symbol_or_isin,
            reason=params.reason,
            evidence_refs=params.evidence_refs,
            client=call.client,
        )
    except WatchlistError as exc:
        return ProposalOut(accepted=False, message=str(exc))
    return ProposalOut(
        accepted=True,
        proposal_id=p.proposal_id,
        message="Recorded. It becomes a suggestion at the next review; only the owner can approve it.",
    )


class ProposeThesisFlagIn(BaseModel):
    symbol_or_isin: str = Field(
        description="NSE symbol or ISIN of a stock the owner holds or watches."
    )
    condition_id: str = Field(
        pattern=r"^(KM|BR)[1-5]$",
        description="The thesis item the evidence concerns: a key metric KM1…KM5 or an exit condition BR1…BR5.",
    )
    status: Literal["STRESSED", "BREAKS"] = Field(
        description="STRESSED: the evidence puts the item under pressure. BREAKS: the evidence suggests an exit condition has been met. Either sets WATCH for review; neither sets BROKEN."
    )
    evidence_refs: list[str] = Field(
        min_length=1,
        max_length=4,
        description="Document ids or resource URIs holding the exact quote, for example the transcript's sha256.",
    )


@PORTFOLIO.tool("propose_thesis_flag", tier="P", title="Flag a thesis item for review")
def propose_thesis_flag(params: ProposeThesisFlagIn, call: ToolCall) -> ProposalOut:
    """Flag one thesis item (a key metric or an exit condition) for the owner's review, with the
    evidence that triggered it. The stock's thesis moves to WATCH at the next run and a 🔴 review item
    appears in the inbox. BROKEN is never set from here: it needs a metric-based breaker or the owner's
    confirmation (D13).

    Use it only when a document you read supports it with an exact quote. Do not use it for general
    unease; a stock without a thesis cannot be flagged.
    """
    sec = resolve(params.symbol_or_isin)
    if sec is None:
        return ProposalOut(
            accepted=False, message=f"{params.symbol_or_isin} is not in the universe."
        )
    parsed = portfolio_service.get_thesis(sec.isin)
    ids = {k.id for k in parsed.key_metrics} | {b.id for b in parsed.breakers}
    if params.condition_id not in ids:
        return ProposalOut(
            accepted=False, message=f"{sec.symbol} has no thesis item {params.condition_id}."
        )
    p = LocalProposalStore().add(
        Proposal(
            kind="thesis_flag",
            isin=sec.isin,
            client=call.client,
            payload={
                "condition_id": params.condition_id,
                "status": params.status,
                "symbol": sec.symbol,
            },
            reason=f"{params.condition_id} {params.status.lower()} per a filed document",
            evidence_refs=params.evidence_refs,
        )  # fmt: skip
    )
    return ProposalOut(
        accepted=True, proposal_id=p.proposal_id, message="Recorded for the owner's review."
    )


class ProposeJournalIn(BaseModel):
    symbol_or_isin: str = Field(description="NSE symbol or ISIN.")
    text: str = Field(
        min_length=15,
        max_length=400,
        description="A draft decision-journal entry in the owner's voice: what was decided and why. Plain text, no amounts.",
    )


@PORTFOLIO.tool("propose_journal_entry", tier="P", title="Draft a journal entry")
def propose_journal_entry(params: ProposeJournalIn, call: ToolCall) -> ProposalOut:
    """Draft a decision-journal entry for the owner to confirm or discard. Nothing is written to the
    journal until the owner accepts it.

    Use it after a conversation that reached a decision worth recording. Do not use it to summarise
    news or to restate a verdict.
    """
    sec = resolve(params.symbol_or_isin)
    if sec is None:
        return ProposalOut(
            accepted=False, message=f"{params.symbol_or_isin} is not in the universe."
        )
    p = LocalProposalStore().add(
        Proposal(
            kind="journal",
            isin=sec.isin,
            client=call.client,
            payload={"symbol": sec.symbol, "action": "journal"},
            reason=params.text.strip(),
        )  # fmt: skip
    )
    return ProposalOut(
        accepted=True, proposal_id=p.proposal_id, message="Drafted for the owner to confirm."
    )
