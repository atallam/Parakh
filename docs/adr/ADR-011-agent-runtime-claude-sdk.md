# ADR-011: Agent runtime: Claude Agent SDK behind AgentRunner

- **Status:** Accepted (recorded deviation from SCAIX LangGraph default)
- **Date:** 2026-09-27
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 15 §6, §10; plan 13 D21 (docs/plan/)

## Context
- Agents are MCP clients. The runtime must support MCP natively, allow-lists, turn limits, audit hooks and structured outputs.

## Decision
- Use the **Claude Agent SDK** for all agents, only through the `AgentRunner` interface (`src/parakh/agents/runtime/base.py`).
- Built-in SDK tools disabled; allowed tools are `mcp__parakh__*` only, checked by the config schema and a contract test (AC-F25.1).
- CI uses `FakeRunner` (`tests/fakes/agent_runner.py`) with recorded trajectories and sockets blocked; `ClaudeSDKRunner` comes from the Phase 0.5 spike.

## Consequences
- ➕ Native MCP, hooks, cost reporting; least code.
- ➖ Claude-only; a young API to pin in `uv.lock`.
- Revisit when a non-Claude model is needed, the SDK can't run on the scheduled runner, or an SDK change breaks L5/L7 twice in a quarter.

## Spike outcome (29 Sep 2026, Phase 0.5 ⑧)

`claude-agent-sdk` 0.2.161 installs on a GitHub-hosted runner with its bundled CLI and connects to `parakh-mcp` over stdio; the agent sees only its allow-listed tool. `ClaudeSDKRunner` applies plan 15 §6.2 (`tools=[]`, `strict_mcp_config`, `setting_sources=[]`, default permission mode, JSON-schema output). The SDK has no hard token stop, so an overspent run ends "pending". The first real model turn waits for `ANTHROPIC_API_KEY`. See `docs/spikes/S8-agent-sdk.md`.
