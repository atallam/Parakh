"""ClaudeSDKRunner: the production AgentRunner on the Claude Agent SDK (plan 15 §6; ADR-011).

Every setting in plan 15 §6.2 is applied by `build_options`, a pure function the contract tests
check without calling a model:
- built-in tools removed (`tools=[]`) and denied again (`disallowed_tools`) — AG-01;
- only `parakh-mcp` over stdio (`strict_mcp_config`), with this agent's identity, so the
  server enforces the allow-list too (AG-05);
- user and project settings are not loaded (`setting_sources=[]`);
- permission mode "default" plus a `can_use_tool` callback that refuses anything off the list;
- `max_turns` is the hard loop cap; the final answer must match the output model's JSON schema.

The SDK has no hard token stop: `task_budget` makes the model aware of its budget, and a run
that still overspends ends as "pending" (AG-08). Import is lazy: `uv sync --extra agents`.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from parakh.agents.runtime.base import AgentResult, AgentSpec, AgentTask, ToolUse
from parakh.audit.context import RunContext
from parakh.audit.ids import new_ulid
from parakh.configs.models import SDK_BUILTIN_TOOLS
from parakh.observability.tracing import enable_agent_sdk_tracing

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions

SERVER_NAME = "parakh"


def agent_client_id(agent_id: str) -> str:
    """AGENT.monthly_reviewer → agent:monthly_reviewer (PARAKH_MCP_CLIENT for the server)."""
    return "agent:" + agent_id.removeprefix("AGENT.")


def build_options(
    spec: AgentSpec, system_prompt: str, *, extra_env: dict[str, str] | None = None
) -> ClaudeAgentOptions:
    from claude_agent_sdk import ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny

    allowed = set(spec.allowed_tools)

    async def can_use_tool(
        name: str, _input: dict[str, Any], _ctx: Any
    ) -> PermissionResultAllow | PermissionResultDeny:
        if name in allowed:
            return PermissionResultAllow()
        return PermissionResultDeny(
            message=f"{name} is not on {spec.agent_id}'s allow-list (AG-01)"
        )

    server_env = {
        "PARAKH_MCP_CLIENT": agent_client_id(spec.agent_id),
        **{
            k: v
            for k in ("PARAKH_STATE_DIR", "PARAKH_CONFIG_DIR", "PARAKH_ENV_FILE")
            if (v := os.environ.get(k))
        },
        **(extra_env or {}),
    }
    return ClaudeAgentOptions(
        tools=[],
        allowed_tools=sorted(allowed),
        disallowed_tools=sorted(SDK_BUILTIN_TOOLS),
        mcp_servers={
            SERVER_NAME: {
                "type": "stdio",
                "command": sys.executable,
                "args": ["-m", "parakh.mcp.server"],
                "env": server_env,
            }
        },
        strict_mcp_config=True,
        setting_sources=[],
        permission_mode="default",
        can_use_tool=can_use_tool,
        system_prompt=system_prompt,
        model=spec.model_id,
        max_turns=spec.max_turns,
        task_budget={"total": spec.token_budget},
        output_format={"type": "json_schema", "schema": spec.output_model.model_json_schema()},
    )


class ClaudeSDKRunner:
    """Runs one agent task through the SDK and maps the outcome onto AgentResult."""

    def __init__(self, system_prompts: dict[str, str]) -> None:
        # prompt_id → rendered system prompt; comes from src/parakh/prompts (P3)
        self.system_prompts = system_prompts

    async def run(self, spec: AgentSpec, task: AgentTask, ctx: RunContext) -> AgentResult:
        from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock, query

        enable_agent_sdk_tracing()  # turns and tool calls nest under run_agent's observation
        result = AgentResult(agent_run_id=new_ulid(), agent_id=spec.agent_id, status="ok")
        problems = spec.contract_problems()
        if problems:
            return result.model_copy(update={"status": "failed", "reason": "; ".join(problems)})
        system = self.system_prompts.get(spec.prompt_id or "", "")
        options = build_options(spec, system, extra_env={"PARAKH_RUN_ID": ctx.run_id})
        prompt = f"Task {task.kind} ({task.task_id}). Inputs: {task.inputs}"
        final: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        result.tool_uses.append(ToolUse(tool=block.name, args=block.input, ok=True))
            elif isinstance(message, ResultMessage):
                final = message
        if final is None:
            return result.model_copy(update={"status": "failed", "reason": "no result message"})
        usage = final.usage or {}
        result.turns = final.num_turns
        result.tokens_in = int(usage.get("input_tokens", 0))
        result.tokens_out = int(usage.get("output_tokens", 0))
        for denial in final.permission_denials or []:
            name = denial.get("tool_name", "?") if isinstance(denial, dict) else str(denial)
            result.tool_uses.append(ToolUse(tool=name, args={}, ok=False, detail="denied"))
        if final.subtype == "error_max_turns":
            return result.model_copy(update={"status": "pending", "reason": "turn limit"})
        if final.is_error:
            return result.model_copy(
                update={"status": "pending", "reason": f"sdk error: {final.subtype}"}
            )
        if result.tokens_in + result.tokens_out > spec.token_budget:
            return result.model_copy(update={"status": "pending", "reason": "token budget"})
        try:
            output = spec.output_model.model_validate(final.structured_output)
        except ValidationError:
            return result.model_copy(
                update={"status": "pending", "reason": "output failed validation"}
            )
        return result.model_copy(update={"output": output.model_dump(mode="json")})
