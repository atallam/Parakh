"""TOOL.audit.*: run manifests and audit events, read-only (plan 15 §4.2)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from parakh.mcp.registry import ToolCall, Toolset
from parakh.services import audit_service
from parakh.services.view_models import RunLookup

AUDIT = Toolset("audit", version="0.1.0")


class GetRunIn(BaseModel):
    run_id: str = Field(
        default="latest",
        description="Run ULID (26 characters, e.g. 01JB6X…), or 'latest' for the newest run.",
    )


@AUDIT.tool("get_run", tier="R", title="Run manifest and audit trail")
def get_run(params: GetRunIn, call: ToolCall) -> RunLookup:
    """Return one Parakh run: mode, as-of date, status, the code and config it ran on, each
    step's status, duration and outputs, and the audit event types it wrote (AUD.*).

    Use it to answer "did the last run succeed?", "what did run X do?" or "is anything still
    waiting to sync?". Pass run_id="latest" when you don't know the ID. It does not return
    scores, verdicts or holdings; those come from the reports toolset. Durations are in
    milliseconds; timestamps are UTC; asof is the IST trading date the run analysed.
    """
    return audit_service.get_run(params.run_id)
