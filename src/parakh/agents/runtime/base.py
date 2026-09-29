"""The AgentRunner interface (plan 15 §6.1; ADR-011).

Agents never import an SDK directly. `ClaudeSDKRunner` (Phase 0.5 spike) implements this for
production; `tests/fakes/agent_runner.py::FakeRunner` replays recorded trajectories so CI never
calls a model. Swapping runtimes means writing one adapter.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from parakh.audit.context import RunContext
from parakh.configs import ConfigBundle
from parakh.configs.models import MCP_TOOL_PREFIX, SDK_BUILTIN_TOOLS


class AgentSpec(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    agent_id: str  # "AGENT.qualitative"
    version: str  # SemVer; stored in llm_calls and the model inventory
    prompt_id: str | None  # pinned in config (P3); required once enabled
    model_id: str  # pinned in config/agents.yaml
    allowed_tools: tuple[str, ...]  # "mcp__parakh__data_get_document", … (AG-01)
    max_turns: int  # the hard max_iterations (SCAIX standard)
    token_budget: int  # per invocation; the run budget still applies on top
    output_model: type[BaseModel]  # the final answer must validate against this

    @classmethod
    def from_config(
        cls, agent_id: str, bundle: ConfigBundle, *, version: str, output_model: type[BaseModel]
    ) -> AgentSpec:
        cfg = bundle.agents.agents[agent_id]
        defaults = bundle.agents.defaults
        return cls(
            agent_id=agent_id,
            version=version,
            prompt_id=cfg.prompt_id,
            model_id=cfg.model_id or defaults.model_id,
            allowed_tools=tuple(cfg.allowed_tools),
            max_turns=cfg.max_turns or defaults.max_turns,
            token_budget=cfg.token_budget
            if cfg.token_budget is not None
            else defaults.token_budget,
            output_model=output_model,
        )

    def contract_problems(self) -> list[str]:
        """The runtime contract (plan 14 L2; AC-F25.1). Empty list = OK."""
        problems = []
        builtin = sorted(set(self.allowed_tools) & SDK_BUILTIN_TOOLS)
        if builtin:
            problems.append(f"built-in tools enabled: {builtin}")
        foreign = [t for t in self.allowed_tools if not t.startswith(MCP_TOOL_PREFIX)]
        if foreign:
            problems.append(f"non-parakh tools: {foreign}")
        return problems


class AgentTask(BaseModel):
    task_id: str
    kind: str  # "monthly_review" | "triage_event" | …
    inputs: dict[str, Any] = Field(default_factory=dict)  # IDs and enums only (AG-06)


class ToolUse(BaseModel):
    tool: str
    args: dict[str, Any]
    ok: bool
    detail: str = ""


class AgentResult(BaseModel):
    agent_run_id: str
    agent_id: str
    status: Literal["ok", "pending", "failed"]  # pending = budget or turn limit hit (AG-08)
    output: dict[str, Any] | None = None
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tool_uses: list[ToolUse] = Field(default_factory=list)
    reason: str = ""


class AgentRunner(Protocol):
    async def run(self, spec: AgentSpec, task: AgentTask, ctx: RunContext) -> AgentResult: ...
