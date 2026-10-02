"""The parakh-mcp server: local stdio only, no network listener (ADR-010, ADR-012).

Start it with `parakh mcp serve` (Claude Code reads `.mcp.json`; Claude Desktop needs the same
command in its config). The client identity comes from PARAKH_MCP_CLIENT
(`claude:desktop`, `claude:code`, or `agent:<name>` when an AgentRunner starts it).
"""

from __future__ import annotations

import inspect
import os
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from parakh import __version__
from parakh.mcp.middleware import Gateway
from parakh.mcp.registry import TOOLS, ToolSpec
from parakh.registry import discover

CLIENT_ENV = "PARAKH_MCP_CLIENT"
DEFAULT_CLIENT = "claude:code"
INSTRUCTIONS = (
    "Parakh is Avinash's personal stock-analysis framework for NSE stocks. Every tool is "
    "read-only or propose-only: nothing here approves, edits or deletes. Numbers come from "
    "deterministic code; quote them with their as-of date and run_id. Holdings are masked."
)


def _flatten(spec: ToolSpec, gateway: Gateway) -> Any:
    """A function whose signature is the input model's fields, so the MCP schema is flat."""

    def tool(**kwargs: Any) -> BaseModel:
        return gateway.invoke(spec, kwargs)

    params = []
    annotations: dict[str, Any] = {}
    for name, field in spec.input_model.model_fields.items():
        annotation = Annotated[field.annotation, field]
        default = (
            inspect.Parameter.empty
            if field.is_required()
            else field.get_default(call_default_factory=True)
        )
        params.append(
            inspect.Parameter(
                name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation
            )
        )
        annotations[name] = annotation
    tool.__signature__ = inspect.Signature(params, return_annotation=spec.output_model)  # type: ignore[attr-defined]
    tool.__annotations__ = annotations | {"return": spec.output_model}
    tool.__name__ = spec.name
    tool.__doc__ = spec.description
    return tool


def build_server(client: str | None = None, gateway: Gateway | None = None) -> MCPServer:
    discover()
    gw = gateway or Gateway.for_client(client or os.environ.get(CLIENT_ENV, DEFAULT_CLIENT))
    server = MCPServer("parakh", version=__version__, instructions=INSTRUCTIONS)
    enabled = gw.config.flags.mcp.toolsets
    for spec in sorted(TOOLS.values(), key=lambda s: s.id):
        if not enabled.get(spec.toolset, False):
            continue
        server.add_tool(
            _flatten(spec, gw),
            name=spec.name,
            title=spec.title,
            description=spec.description,
            annotations=spec.annotations,
            structured_output=True,
        )
    from parakh.mcp.resources import register

    register(server)
    return server


def serve() -> None:
    """Run over stdio until the client disconnects. Never opens a network socket (AC-F24.6)."""
    build_server().run("stdio")


if __name__ == "__main__":
    serve()
