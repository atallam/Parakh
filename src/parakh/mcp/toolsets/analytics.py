"""TOOL.analytics.*: verdict lineage and the catalogues, read-only (plan 15 §4.2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from parakh.mcp.registry import ToolCall, Toolset
from parakh.services import report_service
from parakh.services.view_models import CatalogueLookup, ExplainLookup

ANALYTICS = Toolset("analytics", version="0.1.0")


class ExplainIn(BaseModel):
    symbol_or_isin: str = Field(description="NSE symbol (e.g. INDIGO) or ISIN of a pilot stock.")
    period: str | None = Field(
        default=None, description="Month as YYYY-MM. Omit for the latest snapshot."
    )


@ANALYTICS.tool("explain_verdict", tier="R", title="Explain a verdict")
def explain_verdict(params: ExplainIn, call: ToolCall) -> ExplainLookup:
    """Return the lineage of one verdict: the policy rule that decided it, the value and
    momentum bands and lens versions, each sub-score with its weight, every metric with its
    value, source and as-of date, the top three drivers of any change, and the input hashes.

    Use it to answer "why?" for a verdict or a change. It reads the stored snapshot and
    recomputes nothing. The `text` field is the same tree `parakh explain` prints.
    """
    return report_service.explain(params.symbol_or_isin, params.period)


class CatalogueIn(BaseModel):
    kind: Literal["metric", "signal", "rule", "lens"] = Field(
        description="Which catalogue to list."
    )


@ANALYTICS.tool("list_catalogue", tier="R", title="Metric, signal, rule or lens catalogue")
def list_catalogue(params: CatalogueIn, call: ToolCall) -> CatalogueLookup:
    """List the registered metrics (MET.*), momentum signals (M##), rules (RULE.*) or lenses,
    with units, inputs and one-line summaries. Use it to look up what an ID in a report means.
    It is the same content as docs/METRICS.md, SIGNALS.md and RULES.md.
    """
    return report_service.list_catalogue(params.kind)
