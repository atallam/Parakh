"""Audit middleware: every tool call goes through `invoke` (plan 15 AG-05; AC-F24.5).

Policy lives here, not in the agent's instructions:
- the toolset must be enabled in config/flags.yaml (`mcp.toolsets`);
- an agent client may only call the tools on its allow-list in config/agents.yaml (AG-01);
- each call writes exactly one audit event: `AUD.MCP.TOOL_CALL` (tool, tier, client, args and
  result hashes, latency, status) or `AUD.MCP.TOOL_DENIED` with the reason.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, canonical_json, get_sink
from parakh.audit.events import AUD
from parakh.audit.ids import new_ulid
from parakh.configs import ConfigBundle, load_all
from parakh.mcp.registry import ToolCall, ToolSpec
from parakh.observability.logging import scrub_text

log = structlog.get_logger(__name__)


class ToolDenied(PermissionError):
    pass


class ToolFailed(RuntimeError):
    pass


def _hash(data: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json({"v": data}).encode("utf-8")).hexdigest()


def session_context(client: str) -> RunContext:
    """One audit context per server session; the client decides the actor (plan 10 §3)."""
    kind, _, who = client.partition(":")
    actor_type = "agent" if kind == "agent" else "claude"
    return RunContext.create(
        mode="mcp-session", actor_type=actor_type, actor_id=who or kind, trigger="manual"
    )


@dataclass
class Gateway:
    """Runs tool calls for one client with policy and audit applied."""

    client: str
    ctx: RunContext
    config: ConfigBundle
    sink: AuditSink

    @classmethod
    def for_client(cls, client: str, sink: AuditSink | None = None) -> Gateway:
        return cls(
            client=client, ctx=session_context(client), config=load_all(), sink=sink or get_sink()
        )

    def _deny(self, spec: ToolSpec, call: ToolCall, reason: str) -> ToolDenied:
        self.sink.emit(
            self.ctx,
            AUD.MCP_TOOL_DENIED,
            channel="mcp",
            entity_type="tool",
            entity_id=spec.id,
            reason=reason,
            details={
                "tool_id": spec.id,
                "tier": spec.tier,
                "client": self.client,
                "mcp_call_id": call.mcp_call_id,
            },
        )
        log.warning("mcp.denied", tool_id=spec.id, client=self.client, reason=reason)
        return ToolDenied(f"{spec.id} denied: {reason}")

    def _policy(self, spec: ToolSpec, call: ToolCall) -> str | None:
        if not self.config.flags.mcp.toolsets.get(spec.toolset, False):
            return f"toolset '{spec.toolset}' is disabled in config/flags.yaml"
        if call.is_agent:
            agent_id = "AGENT." + self.client.split(":", 1)[1]
            agent = self.config.agents.agents.get(agent_id)
            if agent is None:
                return f"unknown agent {agent_id}"
            if spec.agent_tool_name not in agent.allowed_tools:
                return f"not on {agent_id}'s allow-list"
        return None

    def invoke(self, spec: ToolSpec, args: dict[str, Any]) -> BaseModel:
        call = ToolCall(client=self.client, mcp_call_id=new_ulid())
        reason = self._policy(spec, call)
        if reason:
            raise self._deny(spec, call, reason)
        start = time.perf_counter()
        status, result, error = "ok", None, None
        try:
            params = spec.input_model.model_validate(args)
            result = spec.fn(params, call)
            if not isinstance(result, spec.output_model):
                raise TypeError(
                    f"{spec.id} returned {type(result).__name__}, not {spec.output_model.__name__}"
                )
            return result
        except ValidationError as exc:
            status, error = "invalid_input", exc
            raise ToolFailed(f"{spec.id}: invalid input: {exc.error_count()} error(s)") from exc
        except Exception as exc:
            status, error = "error", exc
            raise ToolFailed(f"{spec.id} failed: {type(exc).__name__}") from exc
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            self.sink.emit(
                self.ctx,
                AUD.MCP_TOOL_CALL,
                channel="mcp",
                entity_type="tool",
                entity_id=spec.id,
                reason=scrub_text(str(error))[:300] if error else None,
                details={
                    "tool_id": spec.id,
                    "tier": spec.tier,
                    "client": self.client,
                    "mcp_call_id": call.mcp_call_id,
                    "args_hash": _hash(args),
                    "result_hash": _hash(result.model_dump(mode="json"))
                    if result is not None
                    else None,
                    "latency_ms": latency_ms,
                    "status": status,
                },
            )
            log.info(
                "mcp.call",
                tool_id=spec.id,
                client=self.client,
                status=status,
                latency_ms=latency_ms,
            )
