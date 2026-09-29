"""ClaudeSDKRunner options honour plan 15 §6.2 — checked without calling a model (AC-F25.1).

Skipped when the optional `agents` extra isn't installed (`uv sync --extra agents`).
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from parakh.agents.runtime.base import AgentSpec
from parakh.configs.models import SDK_BUILTIN_TOOLS

pytest.importorskip("claude_agent_sdk")

from parakh.agents.runtime.claude_sdk import agent_client_id, build_options  # noqa: E402

TOOL = "mcp__parakh__audit_get_run"


class Out(BaseModel):
    headline: str


SPEC = AgentSpec(
    agent_id="AGENT.monthly_reviewer",
    version="0.1.0",
    prompt_id="MONTHLY_REVIEW.v1",
    model_id="claude-sonnet-5",
    allowed_tools=(TOOL,),
    max_turns=6,
    token_budget=40000,
    output_model=Out,
)


@pytest.mark.ac("AC-F25.1")
def test_options_allow_only_parakh_tools_and_no_built_ins() -> None:
    """T-AGT-10"""
    opts = build_options(SPEC, "system")
    assert opts.tools == []
    assert opts.allowed_tools == [TOOL]
    assert set(opts.disallowed_tools) == SDK_BUILTIN_TOOLS
    assert opts.permission_mode == "default"
    assert opts.strict_mcp_config is True and opts.setting_sources == []
    assert opts.max_turns == 6 and opts.model == "claude-sonnet-5"
    assert opts.output_format is not None and opts.output_format["schema"]["title"] == "Out"


@pytest.mark.ac("AC-F25.1")
def test_mcp_server_is_stdio_with_the_agent_identity() -> None:
    """T-AGT-11: the server enforces the allow-list again for this client (AG-05)."""
    servers = build_options(SPEC, "system").mcp_servers
    assert isinstance(servers, dict)
    server: dict = dict(servers["parakh"])
    assert server["type"] == "stdio" and server["args"] == ["-m", "parakh.mcp.server"]
    assert (
        server["env"]["PARAKH_MCP_CLIENT"]
        == agent_client_id(SPEC.agent_id)
        == "agent:monthly_reviewer"
    )


def test_permission_callback_refuses_anything_off_the_list() -> None:
    """T-AGT-12"""
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    cb = build_options(SPEC, "system").can_use_tool
    assert cb is not None
    assert isinstance(asyncio.run(cb(TOOL, {}, None)), PermissionResultAllow)  # type: ignore[arg-type]
    for name in ("Bash", "mcp__parakh__portfolio_propose_watchlist", "mcp__other__x"):
        assert isinstance(asyncio.run(cb(name, {}, None)), PermissionResultDeny)  # type: ignore[arg-type]
