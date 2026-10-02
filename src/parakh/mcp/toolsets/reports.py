"""TOOL.reports.*: monthly snapshots as view models, read-only and masked (plan 15 §4.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from parakh.mcp.registry import ToolCall, Toolset
from parakh.services import report_service
from parakh.services.view_models import HistoryLookup, SegmentLookup, StockLookup, WhatChanged

REPORTS = Toolset("reports", version="0.1.0")


class GetStockIn(BaseModel):
    symbol_or_isin: str = Field(
        description="NSE symbol (e.g. HDFCBANK) or ISIN (e.g. INE040A01034) of a pilot stock."
    )
    period: str | None = Field(
        default=None, description="Month as YYYY-MM. Omit for the latest snapshot."
    )


@REPORTS.tool("get_stock", tier="R", title="Stock detail for one month")
def get_stock(params: GetStockIn, call: ToolCall) -> StockLookup:
    """Return one stock's monthly view: TL;DR, verdict chip (previous → now), what changed
    (at most four bullets), action box (entry zone, stop, fair-value range, risk/reward),
    value and momentum scores with confidence, tri-state checks (CLEAN, FLAGGED, UNKNOWN) and
    thesis status. Use it for "why is X a BUY?" or "what should I look at on X?".

    It does not recompute anything and does not return quantities, ₹ values or ₹ P&L: a held
    stock shows weight % and P&L % only. For the derivation of a verdict use
    analytics_explain_verdict. Scores are 0–100; prices are ₹; asof is the IST trading date.
    """
    return report_service.get_stock(params.symbol_or_isin, params.period)


class WhatChangedIn(BaseModel):
    period: str | None = Field(
        default=None, description="Month as YYYY-MM. Omit for each stock's latest snapshot."
    )
    cap: str | None = Field(
        default=None, description="'large', 'mid' or 'small'. Omit for all pilot stocks."
    )


@REPORTS.tool("what_changed", tier="R", title="What changed this month")
def what_changed(params: WhatChangedIn, call: ToolCall) -> WhatChanged:
    """List this month's verdict changes, thesis status changes, fired momentum signals,
    flagged checks and regime changes across the pilot, owned stocks first.

    Use it to start a monthly review. Checks that could not run (UNKNOWN) are not listed here
    because they are not changes; they appear per stock in get_stock. Not a place to look for
    scores; use get_stock or segment_summary.
    """
    return report_service.what_changed(params.period, params.cap)


class SegmentIn(BaseModel):
    cap: str = Field(description="'large', 'mid' or 'small'.")
    period: str | None = Field(default=None, description="Month as YYYY-MM. Omit for the latest.")


@REPORTS.tool("segment_summary", tier="R", title="Segment summary")
def segment_summary(params: SegmentIn, call: ToolCall) -> SegmentLookup:
    """Return one cap segment's monthly summary: regime and regime history, verdict counts,
    the ranked table (first 25 rows, strongest verdict first), which holdings need attention,
    verdict changes and concentration flags.

    Holdings appear as symbols with weight % and P&L %; no ₹ amounts or quantities. XIRR and
    correlation are not included until Phase 4.
    """
    return report_service.segment_summary(params.cap, params.period)


class HistoryIn(BaseModel):
    symbol_or_isin: str = Field(description="NSE symbol or ISIN of a pilot stock.")
    metrics: list[str] | None = Field(
        default=None,
        description="history.csv column names, e.g. ['value_score','momentum_score','verdict']. Omit for all columns.",
    )
    months: int = Field(
        default=12, ge=1, le=60, description="How many of the latest months to return."
    )


@REPORTS.tool("get_history", tier="R", title="Monthly history of a stock")
def get_history(params: HistoryIn, call: ToolCall) -> HistoryLookup:
    """Return a stock's month-by-month history (scores, verdict, regime, fair value and so on)
    from history.csv, oldest first. Use it for trends ("has value been falling?").

    A change of weights_hash or policy_version between rows means a score move may come from
    the rules rather than the stock. Scores are 0–100; fair values are ₹.
    """
    return report_service.get_history(params.symbol_or_isin, params.metrics, params.months)
