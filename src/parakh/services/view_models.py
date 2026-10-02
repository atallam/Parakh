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
