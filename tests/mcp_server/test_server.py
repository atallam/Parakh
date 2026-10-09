"""parakh-mcp over MCP (plan 14 L2/L4; AC-F24.6). T-MCP-20…"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path

import pytest
from mcp import Client, ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from parakh.config import REPO_ROOT
from parakh.mcp.server import build_server
from parakh.orchestration.jobs import run_dummy
from tests.conftest import called_from_socketpair


def test_tools_are_listed_with_flat_schemas_and_annotations() -> None:
    """T-MCP-20"""

    async def go() -> None:
        tools = await build_server("claude:code").list_tools()
        by_name = {t.name: t for t in tools}
        tool = by_name["audit_get_run"]
        schema = tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema  # type: ignore[attr-defined]
        assert set(schema["properties"]) == {"run_id"}
        assert "latest" in schema["properties"]["run_id"]["description"]
        assert tool.annotations is not None and tool.annotations.read_only_hint is True

    asyncio.run(go())


@pytest.mark.ac("AC-F24.6")
def test_server_never_listens_on_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-MCP-21: build the server and answer a call with bind/listen forbidden."""

    def forbid(name: str):
        real = getattr(socket.socket, name)

        def guarded(self: socket.socket, *a: object, **k: object) -> object:
            # asyncio's self-pipe on Windows is a loopback socketpair, not a listener.
            if called_from_socketpair():
                return real(self, *a, **k)
            raise AssertionError("parakh-mcp must not open a network listener (ADR-012)")

        return guarded

    monkeypatch.setattr(socket.socket, "bind", forbid("bind"))
    monkeypatch.setattr(socket.socket, "listen", forbid("listen"))
    run_dummy()

    async def go() -> None:
        async with Client(build_server("claude:desktop")) as client:
            result = await client.call_tool("audit_get_run", {"run_id": "latest"})
            assert result.structured_content is not None
            assert result.structured_content["found"] is True
            assert result.structured_content["run"]["status"] == "SUCCESS_AUDIT_PENDING"

    asyncio.run(go())


@pytest.mark.ac("AC-F24.6")
def test_stdio_end_to_end_with_a_real_client(isolated_state: Path) -> None:
    """T-MCP-22 (L4): spawn `python -m parakh.mcp.server` and talk to it over stdio."""
    run_dummy()
    env = {
        **os.environ,
        "PARAKH_STATE_DIR": str(isolated_state),
        "PARAKH_MCP_CLIENT": "claude:code",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "parakh.mcp.server"], env=env, cwd=REPO_ROOT
    )

    async def go() -> None:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"audit_get_run", "reports_get_stock", "analytics_explain_verdict"} <= names
            assert all(
                n.split("_", 1)[0]
                in {"audit", "reports", "analytics", "data", "notify", "portfolio", "jobs"}
                for n in names
            )
            result = await session.call_tool("audit_get_run", {"run_id": "latest"})
            assert (
                result.structured_content is not None and result.structured_content["found"] is True
            )  # type: ignore[attr-defined]

    asyncio.run(asyncio.wait_for(go(), timeout=60))
