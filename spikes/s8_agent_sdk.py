"""Spike ⑧: Claude Agent SDK on a GitHub-hosted runner (ADR-011, ADR-012).

1. Install check: the SDK and its bundled CLI start on the runner.
2. Wiring: the SDK spawns `parakh-mcp` over stdio with the agent's identity; the agent sees only
   its allow-listed tool (no model call needed).
3. One real turn, only when ANTHROPIC_API_KEY is set: the agent calls TOOL.audit.get_run and
   returns a structured answer through ClaudeSDKRunner.
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings

from _common import Recorder
from pydantic import BaseModel

from parakh.agents.runtime.base import AgentSpec, AgentTask
from parakh.audit.context import RunContext
from parakh.orchestration.jobs import run_dummy

warnings.simplefilter("ignore")
TOOL = "mcp__parakh__audit_get_run"


class RunCheck(BaseModel):
    run_status: str
    steps: int
    summary: str


SPEC = AgentSpec(
    agent_id="AGENT.monthly_reviewer",
    version="0.0.1-spike",
    prompt_id="SPIKE",
    model_id=os.environ.get("PARAKH_SPIKE_MODEL", "claude-sonnet-5"),
    allowed_tools=(TOOL,),
    max_turns=4,
    token_budget=60000,
    output_model=RunCheck,
)


async def wiring(rec: Recorder) -> None:
    from claude_agent_sdk import ClaudeSDKClient

    from parakh.agents.runtime.claude_sdk import build_options

    async with ClaudeSDKClient(options=build_options(SPEC, "spike")) as client:
        server: dict = {}
        for _ in range(30):
            status = await client.get_mcp_status()
            server = next(s for s in status["mcpServers"] if s["name"] == "parakh")
            if server["status"] != "pending":
                break
            await asyncio.sleep(1)
        others = [(s["name"], s["status"]) for s in status["mcpServers"] if s["name"] != "parakh"]
        rec.note(
            probe="sdk.mcp_wiring",
            ok=server.get("status") == "connected"
            and [t["name"] for t in server.get("tools", [])] == ["audit_get_run"],
            status=server.get("status"),
            tools=server.get("tools"),
            other_servers=others,
        )


async def one_turn(rec: Recorder) -> None:
    from parakh.agents.runtime.claude_sdk import ClaudeSDKRunner

    prompt = (
        "You check Parakh runs. Call the audit_get_run tool with run_id='latest', then answer "
        "with the run status, the number of steps and one sentence. Use only the tool's data."
    )
    runner = ClaudeSDKRunner({"SPIKE": prompt})
    result = await runner.run(
        SPEC, AgentTask(task_id="spike8", kind="run_check"), RunContext.create(mode="spike")
    )
    rec.note(
        probe="sdk.one_turn",
        ok=result.status == "ok" and any(u.tool == TOOL for u in result.tool_uses),
        status=result.status,
        reason=result.reason,
        turns=result.turns,
        tokens=(result.tokens_in, result.tokens_out),
        tools=[(u.tool, u.ok) for u in result.tool_uses],
        output=result.output,
    )


def main() -> None:
    rec = Recorder("s8")
    try:
        import importlib.metadata as md

        rec.note(
            probe="sdk.install",
            ok=True,
            version=md.version("claude-agent-sdk"),
            python=sys.version.split()[0],
        )
    except Exception as exc:
        rec.note(probe="sdk.install", ok=False, error=str(exc)[:200])
        rec.save()
        return
    run_dummy()  # something for the tool to report
    asyncio.run(asyncio.wait_for(wiring(rec), 120))
    if os.environ.get("ANTHROPIC_API_KEY"):
        asyncio.run(asyncio.wait_for(one_turn(rec), 300))
    else:
        rec.note(
            probe="sdk.one_turn",
            ok=None,
            skipped="ANTHROPIC_API_KEY not set (add it as a repo secret)",
        )
    rec.save()


if __name__ == "__main__":
    main()
