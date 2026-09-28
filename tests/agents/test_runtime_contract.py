"""Agent runtime contract and FakeRunner (AC-F25.1, AC-F25.6; plan 15 §6). T-AGT-01…"""

from __future__ import annotations

import asyncio
import dataclasses
import socket

import pytest
from pydantic import BaseModel

from parakh.agents.runtime.base import AgentSpec, AgentTask
from parakh.audit.context import RunContext
from parakh.configs import load_all
from parakh.mcp.middleware import Gateway
from parakh.orchestration.jobs import run_dummy
from parakh.registry import discover
from tests.fakes.agent_runner import FakeRunner, Trajectory, Turn

TOOL = "mcp__parakh__audit_get_run"


class ReviewOut(BaseModel):
    headline: str
    run_status: str


@pytest.mark.ac("AC-F25.1")
def test_every_configured_agent_passes_the_runtime_contract() -> None:
    """T-AGT-01: only mcp__parakh__* tools, never built-in SDK tools."""
    bundle = load_all()
    assert bundle.agents.agents, "roster is empty"
    for agent_id in bundle.agents.agents:
        spec = AgentSpec.from_config(agent_id, bundle, version="0.0.0", output_model=ReviewOut)
        assert spec.contract_problems() == [], agent_id
        assert spec.max_turns <= 50 and spec.token_budget > 0


def _gateway_allowing(tools: list[str]) -> Gateway:
    discover()
    gw = Gateway.for_client("agent:monthly_reviewer")
    agents = gw.config.agents
    cfg = agents.agents["AGENT.monthly_reviewer"].model_copy(update={"allowed_tools": tools})
    new_agents = agents.model_copy(
        update={"agents": {**agents.agents, "AGENT.monthly_reviewer": cfg}}
    )
    gw.config = dataclasses.replace(gw.config, agents=new_agents)
    return gw


def _spec(gw: Gateway, **overrides: object) -> AgentSpec:
    spec = AgentSpec.from_config(
        "AGENT.monthly_reviewer", gw.config, version="0.1.0", output_model=ReviewOut
    )
    return spec.model_copy(update=overrides)


def _run(runner: FakeRunner, spec: AgentSpec, task_id: str = "t1"):
    return asyncio.run(
        runner.run(
            spec, AgentTask(task_id=task_id, kind="monthly_review"), RunContext.create(mode="test")
        )
    )


@pytest.mark.ac("AC-F25.6")
def test_fake_runner_replays_a_trajectory_through_the_real_gateway() -> None:
    """T-AGT-02: sockets are blocked (conftest), so this proves CI never needs a model."""
    with pytest.raises(RuntimeError):
        socket.create_connection(("api.anthropic.com", 443), timeout=1)
    run_dummy()
    gw = _gateway_allowing([TOOL])
    traj = Trajectory(
        [Turn(TOOL, {"run_id": "latest"})],
        {"headline": "Dummy run ok", "run_status": "SUCCESS_AUDIT_PENDING"},
    )
    result = _run(FakeRunner(gw, {"t1": traj}), _spec(gw))
    assert result.status == "ok"
    assert result.tool_uses[0].ok and result.output == traj.final_output


def test_calls_off_the_allow_list_are_refused() -> None:
    """T-AGT-03"""
    gw = _gateway_allowing([])
    traj = Trajectory([Turn(TOOL, {})], {"headline": "x", "run_status": "?"})
    result = _run(FakeRunner(gw, {"t1": traj}), _spec(gw))
    assert not result.tool_uses[0].ok and "allow-list" in result.tool_uses[0].detail


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [({"max_turns": 2}, "turn limit"), ({"token_budget": 1000}, "token budget")],
)
def test_limits_end_as_pending_not_a_guess(overrides: dict[str, int], reason: str) -> None:
    """T-AGT-04 (AG-08)"""
    gw = _gateway_allowing([TOOL])
    traj = Trajectory([Turn(TOOL, {})] * 3, {"headline": "x", "run_status": "?"})
    result = _run(FakeRunner(gw, {"t1": traj}), _spec(gw, **overrides))
    assert result.status == "pending" and result.reason == reason


def test_invalid_final_output_is_pending() -> None:
    """T-AGT-05"""
    gw = _gateway_allowing([TOOL])
    result = _run(FakeRunner(gw, {"t1": Trajectory([], {"headline": 3})}), _spec(gw))
    assert result.status == "pending" and "validation" in result.reason


def test_built_in_tools_fail_the_contract_even_if_config_is_bypassed() -> None:
    """T-AGT-06"""
    gw = _gateway_allowing([TOOL])
    spec = _spec(gw, allowed_tools=(TOOL, "Bash"))
    result = _run(FakeRunner(gw, {"t1": Trajectory([], {})}), spec)
    assert result.status == "failed" and "Bash" in result.reason
