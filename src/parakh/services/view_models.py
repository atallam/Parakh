"""View models: the only shapes the CLI, Streamlit, Telegram and MCP may show (ADR-006, UX-02).

Because every surface renders the same model from the same service call, MCP and the CLI
can't disagree about a number (AG-04, AC-F24.2).
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class Stamp(BaseModel):
    """Carried by every MCP response (plan 15 §4.1)."""

    asof: dt.date | None
    run_id: str | None
    framework_version: str


class StepSummary(BaseModel):
    name: str
    status: str
    duration_ms: float | None
    outputs: dict[str, object] = Field(default_factory=dict)


class RunView(BaseModel):
    run_id: str
    mode: str
    env: str
    asof: dt.date
    status: str
    trigger: str
    triggered_by: str
    started_at: dt.datetime
    finished_at: dt.datetime
    code_version: str
    config_hash: str
    steps: list[StepSummary]
    audit_event_types: list[str]
    audit_pending: int


class RunLookup(BaseModel):
    stamp: Stamp
    found: bool
    run: RunView | None = None
    message: str = ""


# -- Reports and analytics (Phase 2; plan 15 §4.2) ----------------------------------------------
from typing import Any  # noqa: E402


class StockLookup(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    symbol: str | None = None
    period: str | None = None
    view: dict[str, Any] | None = None


class ChangeItem(BaseModel):
    symbol: str
    owned: bool
    kind: str  # verdict | thesis | signal | red_flag | regime
    text: str


class WhatChanged(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    period: str | None = None
    items: list[ChangeItem] = Field(default_factory=list)


class SegmentLookup(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    cap: str | None = None
    period: str | None = None
    summary: dict[str, Any] | None = None
    truncated: bool = False


class HistoryLookup(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    symbol: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class ExplainLookup(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    tree: dict[str, Any] | None = None
    text: str = ""


class CatalogueLookup(BaseModel):
    stamp: Stamp
    kind: str
    items: list[dict[str, Any]] = Field(default_factory=list)


# -- Phase 4: portfolio, jobs and data tools (plan 15 §4.2) ---------------------------------------
class PositionRow(BaseModel):
    symbol: str
    isin: str
    cap: str
    verdict: str
    weight_pct: float | None = None
    pnl_pct: float | None = None
    days_to_long_term: int | None = None
    cost_pending: bool = False
    thesis_status: str = "NOT_SET"
    # present only for the owner's own interactive client with detail=true (AG-07, AC-F24.4)
    quantity: float | None = None
    avg_cost_inr: float | None = None
    market_value_inr: float | None = None
    pnl_inr: float | None = None


class PositionsOut(BaseModel):
    stamp: Stamp
    found: bool
    masked: bool = True
    message: str = ""
    weight_basis: str | None = None
    rows: list[PositionRow] = Field(default_factory=list)


class ThesisKeyMetric(BaseModel):
    id: str
    text: str


class ThesisBreaker(BaseModel):
    id: str
    text: str
    check: str
    rule: str | None = None


class ThesisOut(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    symbol: str | None = None
    isin: str | None = None
    status: str = "NOT_SET"
    status_source: str | None = None
    original_statement: str | None = None
    key_metrics: list[ThesisKeyMetric] = Field(default_factory=list)
    breakers: list[ThesisBreaker] = Field(default_factory=list)
    review_by: dt.date | None = None
    review_due: bool = False


class PendingItem(BaseModel):
    kind: str  # suggestion | proposal
    id: str
    symbol: str | None = None
    action: str
    origin: str
    reason: str
    expires_on: dt.date | None = None
    sources: list[str] = Field(default_factory=list)


class PendingOut(BaseModel):
    stamp: Stamp
    items: list[PendingItem] = Field(default_factory=list)


class ProposalOut(BaseModel):
    accepted: bool
    proposal_id: str | None = None
    message: str = ""


class RefreshOut(BaseModel):
    queued: bool
    request_id: str | None = None
    remaining_today: int = 0
    message: str = ""


class MetricValue(BaseModel):
    id: str
    value: float | None
    source: str | None = None
    asof: str | None = None


class FundamentalsOut(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    symbol: str | None = None
    as_of: str | None = None
    metrics: list[MetricValue] = Field(default_factory=list)
    unavailable: dict[str, str] = Field(default_factory=dict)


class PriceRow(BaseModel):
    date: dt.date
    close: float
    dma50: float | None = None
    dma200: float | None = None


class PricesOut(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    symbol: str | None = None
    source: str | None = None
    rows: list[PriceRow] = Field(default_factory=list)
    truncated: bool = False


class DqCheck(BaseModel):
    isin: str
    symbol: str
    check_id: str
    status: str
    detail: str = ""


class QualityOut(BaseModel):
    stamp: Stamp
    found: bool
    message: str = ""
    checks: list[DqCheck] = Field(default_factory=list)
    confidence: dict[str, str] = Field(default_factory=dict)
