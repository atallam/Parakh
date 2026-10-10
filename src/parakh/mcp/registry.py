"""parakh-mcp tool registry (plan 15 §4.2, §4.4; AC-F24.1, AC-F24.3).

A tool can't exist without a `TOOL.<toolset>.<name>` ID, a permission tier and Pydantic input and
output models, and no tool may approve, reject, edit, delete, publish or change config (AG-03):
the decorator refuses to register one, and a registry sweep test checks it again.

    AUDIT = Toolset("audit", version="0.1.0")

    @AUDIT.tool("get_run", tier="R", title="Run manifest")
    def get_run(params: GetRunIn, call: ToolCall) -> RunLookup:
        '''Docstring written for a model: what it's for, when not to use it, units, IDs.'''
        return audit_service.get_run(params.run_id)
"""

from __future__ import annotations

import inspect
import re
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from mcp.types import ToolAnnotations
from pydantic import BaseModel

Tier = Literal["R", "P", "N", "J"]
TIER_MEANING = {
    "R": "read-only",
    "P": "propose (writes a proposal row only)",
    "N": "notify (queued through routing policy)",
    "J": "job request (bounded, rate-limited)",
}
TOOLSETS = (
    "reports", "analytics", "data", "portfolio", "notify", "jobs", "audit", "calibration",
)  # fmt: skip
TOOL_ID = re.compile(rf"^TOOL\.({'|'.join(TOOLSETS)})\.[a-z][a-z0-9_]*$")
# Verbs that change your state. They stay with you in Streamlit, Telegram or the CLI (AG-03).
FORBIDDEN_VERBS = (
    "approve",
    "reject",
    "delete",
    "remove",
    "edit",
    "update",
    "set",
    "publish",
    "promote",
    "import",
    "write",
    "rescore",
    "invalidate",
    "rotate",
)
_FORBIDDEN = re.compile(rf"(^|_)({'|'.join(FORBIDDEN_VERBS)})(_|$)")
MCP_PREFIX = "mcp__parakh__"


class ToolRegistrationError(ValueError):
    pass


@dataclass(frozen=True)
class ToolCall:
    """Who is calling, passed to every tool (masking and allow-lists depend on it)."""

    client: str  # "claude:desktop" | "claude:code" | "agent:<name>"
    mcp_call_id: str

    @property
    def is_agent(self) -> bool:
        return self.client.startswith("agent:")


@dataclass(frozen=True)
class ToolSpec:
    id: str
    toolset: str
    toolset_version: str
    name: str  # MCP name, e.g. "audit_get_run"
    tier: Tier
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    fn: Callable[[Any, ToolCall], BaseModel]

    @property
    def agent_tool_name(self) -> str:
        """The name an Agent SDK allow-list uses: mcp__parakh__<toolset>_<name>."""
        return MCP_PREFIX + self.name

    @property
    def annotations(self) -> ToolAnnotations:
        read_only = self.tier == "R"
        return ToolAnnotations(
            title=self.title,
            read_only_hint=read_only,
            destructive_hint=False,
            idempotent_hint=read_only,
            open_world_hint=False,
        )


TOOLS: dict[str, ToolSpec] = {}


def _validate(spec: ToolSpec) -> None:
    problems: list[str] = []
    if not TOOL_ID.match(spec.id):
        problems.append(f"id must look like TOOL.<toolset>.<name> with toolset in {TOOLSETS}")
    if spec.tier not in TIER_MEANING:
        problems.append(f"tier must be one of {sorted(TIER_MEANING)}")
    local = spec.id.rsplit(".", 1)[-1]
    if _FORBIDDEN.search(local):
        problems.append("state-changing verbs are never MCP tools (AG-03)")
    if spec.tier == "P" and not local.startswith("propose_"):
        problems.append("tier P tools must be named propose_*")
    if spec.tier != "P" and local.startswith("propose_"):
        problems.append("propose_* tools must be tier P")
    if spec.tier == "N" and spec.toolset != "notify":
        problems.append("tier N tools live in the notify toolset")
    if spec.tier == "J" and spec.toolset != "jobs":
        problems.append("tier J tools live in the jobs toolset")
    if len(spec.description) < 40:
        problems.append("needs a docstring written for a model (what, when not, units, IDs)")
    if spec.id in TOOLS:
        problems.append("registered twice")
    if problems:
        raise ToolRegistrationError(f"{spec.id}: " + "; ".join(problems))


class Toolset:
    def __init__(self, name: str, *, version: str) -> None:
        if name not in TOOLSETS:
            raise ToolRegistrationError(f"unknown toolset {name!r}; add it to TOOLSETS first")
        self.name = name
        self.version = version

    def tool(
        self, name: str, *, tier: Tier, title: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            hints = typing.get_type_hints(fn)
            params = list(inspect.signature(fn).parameters)
            in_model = hints.get(params[0]) if params else None
            out_model = hints.get("return")
            if not (isinstance(in_model, type) and issubclass(in_model, BaseModel)):
                raise ToolRegistrationError(
                    f"TOOL.{self.name}.{name}: first parameter needs a Pydantic model"
                )
            if not (isinstance(out_model, type) and issubclass(out_model, BaseModel)):
                raise ToolRegistrationError(
                    f"TOOL.{self.name}.{name}: return type needs a Pydantic model"
                )
            spec = ToolSpec(
                id=f"TOOL.{self.name}.{name}",
                toolset=self.name,
                toolset_version=self.version,
                name=f"{self.name}_{name}",
                tier=tier,
                title=title,
                description=inspect.cleandoc(fn.__doc__ or ""),
                input_model=in_model,
                output_model=out_model,
                fn=fn,
            )
            _validate(spec)
            TOOLS[spec.id] = spec
            return fn

        return deco


def by_mcp_name(name: str) -> ToolSpec | None:
    return next((s for s in TOOLS.values() if s.name == name), None)
