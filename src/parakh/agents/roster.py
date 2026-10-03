"""Shared plumbing for the Phase 3 agents: specs, prompts, the runner, audit events (plan 15 §5–6).

Every agent run writes `AUD.AGENT.START` and `AUD.AGENT.END` (AC-F25.7); a turn or token limit
also writes `AUD.AGENT.TURN_LIMIT` or `AUD.LLM.BUDGET_STOP` and counts toward the LLM-failure alert
(AC-F25.2). A run that does not finish returns `pending`, never a guess (AG-08).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from pydantic import BaseModel

from parakh.agents.runtime.base import AgentResult, AgentRunner, AgentSpec, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD
from parakh.configs import ConfigBundle
from parakh.prompts import load_prompt


def system_prompts(*names: str) -> dict[str, str]:
    """prompt_id → system text for the SDK runner, from the pinned prompt files (P3)."""
    out: dict[str, str] = {}
    for name in names:
        spec = load_prompt(name)
        out[f"{name}.{spec['version']}"] = spec["system"]
    return out


def build_spec(
    agent_id: str, bundle: ConfigBundle, *, version: str, output_model: type[BaseModel]
) -> AgentSpec:
    return AgentSpec.from_config(agent_id, bundle, version=version, output_model=output_model)


def agent_enabled(bundle: ConfigBundle, agent_id: str) -> bool:
    cfg = bundle.agents.agents.get(agent_id)
    return bool(cfg and cfg.enabled)


def run_agent(
    runner: AgentRunner,
    spec: AgentSpec,
    task: AgentTask,
    ctx: RunContext,
    sink: AuditSink,
    bundle: ConfigBundle,
) -> AgentResult:
    """Run one task with START and END audit events and the limit events when it stops early."""
    sink.emit(
        ctx,
        AUD.AGENT_START,
        entity_type="agent_run",
        entity_id=task.task_id,
        details={
            "agent_id": spec.agent_id,
            "version": spec.version,
            "prompt_id": spec.prompt_id,
            "model_id": spec.model_id,
            "kind": task.kind,
            "dry_run": bundle.agents.dry_run,
            "allowed_tools": list(spec.allowed_tools),
        },
    )
    try:
        result = _sync(runner.run(spec, task, ctx))
    except Exception as exc:  # a crashed agent is a failed agent, never a failed job
        result = AgentResult(
            agent_run_id=task.task_id,
            agent_id=spec.agent_id,
            status="failed",
            reason=f"{type(exc).__name__}",
        )
    if result.status == "pending":
        event = AUD.LLM_BUDGET_STOP if "budget" in result.reason else AUD.AGENT_TURN_LIMIT
        sink.emit(
            ctx,
            event,
            entity_type="agent_run",
            entity_id=task.task_id,
            reason=result.reason,
            details={
                "agent_id": spec.agent_id,
                "turns": result.turns,
                "tokens": result.tokens_in + result.tokens_out,
            },
        )
    sink.emit(
        ctx,
        AUD.AGENT_END,
        entity_type="agent_run",
        entity_id=task.task_id,
        reason=result.reason or None,
        details={
            "agent_id": spec.agent_id,
            "status": result.status,
            "turns": result.turns,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "tools": [t.tool for t in result.tool_uses],
            "tools_denied": [t.tool for t in result.tool_uses if not t.ok],
        },
    )
    return result


def _sync[T](coro: Awaitable[T]) -> T:
    async def wrap() -> T:
        return await coro

    return asyncio.run(wrap())


def sdk_runner(*prompt_names: str) -> AgentRunner:  # pragma: no cover - needs the SDK and a key
    from parakh.agents.runtime.claude_sdk import ClaudeSDKRunner

    return ClaudeSDKRunner(system_prompts(*prompt_names))


__all__ = ["agent_enabled", "build_spec", "run_agent", "sdk_runner", "system_prompts"]
