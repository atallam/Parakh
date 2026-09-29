"""Tool registry sweep (AC-F24.1, AC-F24.3; plan 14 L0). T-MCP-01…"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from parakh.mcp.registry import FORBIDDEN_VERBS, TOOLS, ToolCall, ToolRegistrationError, Toolset
from parakh.registry import discover


class In(BaseModel):
    isin: str


class Out(BaseModel):
    ok: bool


DOC = "A docstring long enough to be written for a model, with units and IDs."


@pytest.mark.ac("AC-F24.1")
def test_every_tool_has_id_tier_annotations_and_models() -> None:
    """T-MCP-01"""
    discover()
    assert TOOLS, "no tools registered"
    for spec in TOOLS.values():
        assert spec.id.startswith(f"TOOL.{spec.toolset}.")
        assert spec.tier in {"R", "P", "N", "J"}
        assert issubclass(spec.input_model, BaseModel) and issubclass(spec.output_model, BaseModel)
        ann = spec.annotations
        assert ann.destructive_hint is False and ann.open_world_hint is False
        assert ann.read_only_hint is (spec.tier == "R")
        assert spec.agent_tool_name == f"mcp__parakh__{spec.toolset}_{spec.id.rsplit('.', 1)[1]}"


@pytest.mark.ac("AC-F24.3")
def test_no_registered_tool_changes_your_state() -> None:
    """T-MCP-02 (AG-03)"""
    discover()
    for spec in TOOLS.values():
        words = spec.id.rsplit(".", 1)[1].split("_")
        assert not set(words) & set(FORBIDDEN_VERBS), spec.id


@pytest.mark.ac("AC-F24.3")
@pytest.mark.parametrize(
    "name", ["approve_watchlist", "delete_lot", "edit_thesis", "publish_report", "set_weights"]
)
def test_state_changing_tools_cannot_be_registered(name: str) -> None:
    """T-MCP-03"""
    ts = Toolset("portfolio", version="0.0.0")
    with pytest.raises(ToolRegistrationError, match="AG-03"):

        @ts.tool(name, tier="R", title="x")
        def tool(params: In, call: ToolCall) -> Out:
            return Out(ok=True)

        tool.__doc__ = DOC


@pytest.mark.ac("AC-F24.1")
def test_a_tool_without_models_or_a_valid_tier_is_refused() -> None:
    """T-MCP-04"""
    ts = Toolset("reports", version="0.0.0")
    with pytest.raises(ToolRegistrationError, match="Pydantic"):

        @ts.tool("bad_types", tier="R", title="x")
        def bad_types(params: dict, call: ToolCall) -> Out:  # type: ignore[type-arg]
            return Out(ok=True)

    with pytest.raises(ToolRegistrationError, match="tier"):

        @ts.tool("bad_tier", tier="X", title="x")  # type: ignore[arg-type]
        def bad_tier(params: In, call: ToolCall) -> Out:
            """A docstring long enough to be written for a model, with units and IDs."""
            return Out(ok=True)

    with pytest.raises(ToolRegistrationError, match="propose_"):

        @ts.tool("watchlist_add", tier="P", title="x")
        def propose_wrong(params: In, call: ToolCall) -> Out:
            """A docstring long enough to be written for a model, with units and IDs."""
            return Out(ok=True)

    assert "TOOL.reports.bad_tier" not in TOOLS
