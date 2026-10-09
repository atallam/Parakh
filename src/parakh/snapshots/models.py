"""The canonical monthly snapshot (plan 00 §3; AC-F09.5). Everything else is rendered from it.

One run writes the JSON first; the Markdown report, history.csv, HISTORY.md, the share export
and the MCP views are all derived, so there are never two sources of truth.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 1


class Framework(BaseModel):
    """What produced the numbers: without it a score change could be a rules change (plan 00 §2b)."""

    version: str  # package version
    policy_version: str
    lens_versions: dict[str, str]
    config_hash: str
    weights_hash: (
        str  # value.yaml + momentum.yaml + verdict_policy.yaml, the part that moves scores
    )
    code_version: str


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    symbol: str
    isin: str
    name: str
    cap: str
    sector: str | None = None
    profile: str
    history_class: str
    period: str  # YYYY-MM
    asof: dt.date
    run_id: str
    generated_at: dt.datetime
    framework: Framework
    price: dict[str, Any]
    fundamentals_asof: dict[str, Any]
    value: dict[str, Any]  # a LensResult dump
    momentum: dict[str, Any]  # a LensResult dump
    regime: dict[str, Any]
    verdict: dict[str, Any]  # a VerdictResult dump
    position: dict[str, Any] | None = None  # personal; masked in shared views
    thesis: dict[str, Any]
    checks: list[dict[str, Any]] = Field(default_factory=list)  # tri-state (UX-05)
    qualitative: dict[str, Any]
    devils_advocate: dict[str, Any] | None = None  # F07 overlay, added after the monthly run
    events: dict[str, Any]
    data_quality: dict[str, Any]
    lineage: dict[str, Any]
    chart: dict[str, Any] = Field(default_factory=dict)
    overrides: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def period_of(asof: dt.date) -> str:
    return f"{asof.year:04d}-{asof.month:02d}"
