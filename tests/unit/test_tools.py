"""MCP tool functions tested directly, with no LLM and no server (C5.1). T-MCP-30…"""

from __future__ import annotations

from parakh.mcp.registry import ToolCall
from parakh.mcp.toolsets.audit import GetRunIn, get_run
from parakh.orchestration.jobs import run_dummy

CALL = ToolCall(client="claude:code", mcp_call_id="01K0000000000000000000CALL")


def test_get_run_with_no_runs_says_what_to_do() -> None:
    """T-MCP-30"""
    out = get_run(GetRunIn(), CALL)
    assert not out.found and "parakh run --mode dummy" in out.message
    assert out.stamp.run_id is None


def test_get_run_latest_and_by_id_return_the_same_run() -> None:
    """T-MCP-31"""
    run_dummy()
    ctx, _ = run_dummy()
    latest = get_run(GetRunIn(), CALL)
    by_id = get_run(GetRunIn(run_id=ctx.run_id), CALL)
    assert latest.run == by_id.run
    assert latest.run is not None
    assert latest.run.run_id == ctx.run_id
    assert latest.stamp.run_id == ctx.run_id and latest.stamp.asof == ctx.asof
    assert [s.name for s in latest.run.steps] == ["load_config", "load_universe", "noop_score"]
    assert latest.run.audit_event_types == ["AUD.RUN.START", "AUD.RUN.END"]


def test_get_run_unknown_id() -> None:
    """T-MCP-32"""
    out = get_run(GetRunIn(run_id="01K00000000000000000000000"), CALL)
    assert not out.found and "No manifest" in out.message
