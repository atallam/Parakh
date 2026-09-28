# ADR-010: MCP as the agent-facing interface over services

- **Status:** Accepted
- **Date:** 2026-09-27
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 15 §10; plan 13 D20 (docs/plan/)

## Context
- Parakh should be agentic-forward. ADR-006 already made `services/` the single contract for every surface.
- Private per-agent tools would re-implement access and guardrails for every agent and client.

## Decision
- One server, **`parakh-mcp`**, exposes the services as namespaced toolsets. It is the **only** way agents reach data or state, and it also serves you in Claude Desktop and Claude Code.
- Scoring and watchers stay code workflows (AG-02). Agents only propose (AG-03): no approve, edit, delete, publish or config tools.
- Every tool has a `TOOL.<toolset>.<name>` ID, a tier (R/P/N/J), MCP annotations and Pydantic models; registration refuses anything else (`src/parakh/mcp/registry.py`), and `docs/TOOLS.md` is generated.
- Every call passes the audit middleware: one `AUD.MCP.TOOL_CALL` or `AUD.MCP.TOOL_DENIED` per call.

## Consequences
- ➕ One set of guardrails for every agent and for Claude; new agents are mostly a prompt, an allow-list and an output schema.
- ➖ An extra layer to test and version (tool schemas), kept thin by rule and lint.
