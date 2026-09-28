"""Audit middleware and policy (AC-F24.5; AG-01, AG-05). T-MCP-10…"""

from __future__ import annotations

import pytest

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.mcp.middleware import Gateway, ToolDenied, ToolFailed
from parakh.mcp.registry import TOOLS
from parakh.orchestration.jobs import run_dummy
from parakh.registry import discover


def _spec():
    discover()
    return TOOLS["TOOL.audit.get_run"]


def _calls(gw: Gateway, event: AUD) -> list:
    return [e for e in get_sink().events_for_run(gw.ctx.run_id) if e.event_type == event]


@pytest.mark.ac("AC-F24.5")
def test_each_call_writes_exactly_one_tool_call_event() -> None:
    """T-MCP-10"""
    ctx, _ = run_dummy()
    gw = Gateway.for_client("claude:desktop")
    out = gw.invoke(_spec(), {"run_id": "latest"})
    gw.invoke(_spec(), {"run_id": ctx.run_id})
    assert out.found and out.run is not None and out.run.run_id == ctx.run_id  # type: ignore[attr-defined]
    events = _calls(gw, AUD.MCP_TOOL_CALL)
    assert len(events) == 2
    d = events[0].details
    assert (
        d["tool_id"] == "TOOL.audit.get_run"
        and d["tier"] == "R"
        and d["client"] == "claude:desktop"
    )
    assert d["args_hash"].startswith("sha256:") and d["result_hash"].startswith("sha256:")
    assert d["status"] == "ok" and d["latency_ms"] >= 0
    assert events[0].actor_type == "claude" and events[0].channel == "mcp"


@pytest.mark.ac("AC-F24.5")
def test_invalid_input_is_logged_once_as_a_failed_call() -> None:
    """T-MCP-11"""
    gw = Gateway.for_client("claude:code")
    with pytest.raises(ToolFailed):
        gw.invoke(_spec(), {"run_id": 42})
    events = _calls(gw, AUD.MCP_TOOL_CALL)
    assert len(events) == 1 and events[0].details["status"] == "invalid_input"


def test_disabled_toolset_is_denied_and_audited() -> None:
    """T-MCP-12"""
    gw = Gateway.for_client("claude:code")
    flags = gw.config.flags.model_copy(
        update={"mcp": gw.config.flags.mcp.model_copy(update={"toolsets": {"audit": False}})}
    )
    gw.config = type(gw.config)(**{**vars(gw.config), "flags": flags})
    with pytest.raises(ToolDenied):
        gw.invoke(_spec(), {})
    assert len(_calls(gw, AUD.MCP_TOOL_DENIED)) == 1
    assert _calls(gw, AUD.MCP_TOOL_CALL) == []


def test_agent_off_its_allow_list_is_denied() -> None:
    """T-MCP-13 (AG-01 enforced in the server, AG-05)"""
    gw = Gateway.for_client("agent:monthly_reviewer")
    assert load_all().agents.agents["AGENT.monthly_reviewer"].allowed_tools == []
    with pytest.raises(ToolDenied, match="allow-list"):
        gw.invoke(_spec(), {})
    denied = _calls(gw, AUD.MCP_TOOL_DENIED)
    assert len(denied) == 1 and denied[0].actor_type == "agent"
