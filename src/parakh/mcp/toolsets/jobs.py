"""TOOL.jobs.*: the one tier-J tool, `request_refresh` (plan 15 §4.2; AC-F25.4).

It queues a request; the daily job refreshes the stock's qualitative read. At most
`jobs.refresh_daily_cap` a day, and none while a monthly run is going.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from parakh.configs import load_all
from parakh.mcp.registry import ToolCall, Toolset
from parakh.services.job_requests import JobRequests
from parakh.services.report_service import resolve
from parakh.services.view_models import RefreshOut
from parakh.watch.state import StateStore

JOBS = Toolset("jobs", version="0.1.0")


class RefreshIn(BaseModel):
    symbol_or_isin: str = Field(
        description="NSE symbol (e.g. MAZDOCK) or ISIN of a stock in the universe."
    )
    reason_code: Literal["new_transcript", "new_results", "material_filing", "data_gap"] = Field(
        description="Why: a new concall transcript was filed, new results were filed, a material filing needs a fresh read, or the stock's data has a gap."
    )


@JOBS.tool("request_refresh", tier="J", title="Ask for a single-stock refresh")
def request_refresh(params: RefreshIn, call: ToolCall) -> RefreshOut:
    """Ask for one stock's qualitative read to be refreshed by the next daily job. It does not run
    anything now and does not recompute scores or verdicts.

    At most five requests are accepted per IST day across all agents, one per stock at a time, and none
    while a monthly run is in progress; the answer says how many remain. Use it only when a new
    transcript or results filing makes the current read out of date. The reason is a code, never free text.
    """
    sec = resolve(params.symbol_or_isin)
    if sec is None:
        return RefreshOut(queued=False, message=f"{params.symbol_or_isin} is not in the universe.")
    cap = load_all().flags.jobs.refresh_daily_cap
    return JobRequests(StateStore(), cap).request(sec.isin, params.reason_code, call.client)
