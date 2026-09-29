"""FakeRunner: replays a recorded agent trajectory against the real parakh-mcp gateway.

CI never calls a model (plan 14 §6). A trajectory is the list of tool calls an agent made plus
its final answer. The runner enforces the same limits the real runner must: the allow-list
(through the gateway, AG-01/AG-05), `max_turns` and `token_budget` (AG-08: running out means
"pending", not "guess"), and output validation against the agent's `output_model`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from parakh.agents.runtime.base import AgentResult, AgentSpec, AgentTask, ToolUse
from parakh.audit.context import RunContext
from parakh.audit.ids import new_ulid
from parakh.mcp.middleware import Gateway, ToolDenied, ToolFailed
from parakh.mcp.registry import MCP_PREFIX, by_mcp_name


@dataclass
class Turn:
    tool: str  # "mcp__parakh__audit_get_run"
    args: dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 500
    tokens_out: int = 100


@dataclass
class Trajectory:
    turns: list[Turn]
    final_output: dict[str, Any]


@dataclass
class FakeRunner:
    gateway: Gateway
    trajectories: dict[str, Trajectory]  # keyed by task_id

    async def run(self, spec: AgentSpec, task: AgentTask, ctx: RunContext) -> AgentResult:
        result = AgentResult(agent_run_id=new_ulid(), agent_id=spec.agent_id, status="ok")
        problems = spec.contract_problems()
        if problems:
            return result.model_copy(update={"status": "failed", "reason": "; ".join(problems)})
        trajectory = self.trajectories[task.task_id]
        for turn in trajectory.turns:
            if result.turns >= spec.max_turns:
                return result.model_copy(update={"status": "pending", "reason": "turn limit"})
            result.turns += 1
            result.tokens_in += turn.tokens_in
            result.tokens_out += turn.tokens_out
            if result.tokens_in + result.tokens_out > spec.token_budget:
                return result.model_copy(update={"status": "pending", "reason": "token budget"})
            tool_spec = by_mcp_name(turn.tool.removeprefix(MCP_PREFIX))
            if tool_spec is None:
                result.tool_uses.append(
                    ToolUse(tool=turn.tool, args=turn.args, ok=False, detail="unknown tool")
                )
                continue
            try:
                out = self.gateway.invoke(tool_spec, turn.args)
                result.tool_uses.append(
                    ToolUse(tool=turn.tool, args=turn.args, ok=True, detail=type(out).__name__)
                )
            except (ToolDenied, ToolFailed) as exc:
                result.tool_uses.append(
                    ToolUse(tool=turn.tool, args=turn.args, ok=False, detail=str(exc))
                )
        try:
            output = spec.output_model.model_validate(trajectory.final_output)
        except ValidationError:
            return result.model_copy(
                update={"status": "pending", "reason": "output failed validation"}
            )
        return result.model_copy(update={"output": output.model_dump(mode="json")})
