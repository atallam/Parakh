# Spike ⑧: Claude Agent SDK on a runner (ADR-011, ADR-012)

- **Date:** 29 Sep 2026 · **Script:** `spikes/s8_agent_sdk.py` · **Code kept:** `src/parakh/agents/runtime/claude_sdk.py` (`ClaudeSDKRunner`, `build_options`)

## Result

- **Install:** `claude-agent-sdk` 0.2.161 installs on ubuntu-latest (Python 3.12.3) with its bundled CLI (optional extra: `uv sync --extra agents`).
- **Wiring:** the SDK spawns `parakh-mcp` over stdio with the agent's identity; status `connected` within about a second; the agent sees exactly one tool, `audit_get_run`, annotated read-only; no other MCP servers on the runner.
- **One model turn: pending an API key.** `ANTHROPIC_API_KEY` is neither in `.env` nor a repo secret. The workflow runs the turn automatically once the secret exists.

## SDK facts that shape the runner

- `tools=[]` removes every built-in tool; `disallowed_tools` repeats them as a second guard; `strict_mcp_config=True` and `setting_sources=[]` stop user or project settings from adding servers.
- Tools in `allowed_tools` are auto-approved **before** `can_use_tool` is consulted; the callback therefore only ever sees (and denies) off-list tools. The server-side allow-list (AG-05) is the third guard.
- There is no hard token stop: `task_budget` is advisory, so the runner marks an overspent run "pending" after the fact; `max_turns` is the hard cap.
- Structured output uses `output_format={"type": "json_schema", ...}` from the agent's Pydantic model; the result arrives in `ResultMessage.structured_output`.
- In the workspace, the CLI also registered a disabled `claude-in-chrome` server; the runner had none.

## Claude Desktop on your PC (ADR-012)

Add to `%APPDATA%\Claude\claude_desktop_config.json` (then restart Claude Desktop):

```json
{
  "mcpServers": {
    "parakh": {
      "command": "uv",
      "args": ["run", "--quiet", "--directory",
               "C:\\Users\\atall\\OneDrive\\Documents\\AI Experiments\\Stock Analysis\\parakh",
               "parakh", "mcp", "serve"],
      "env": { "PARAKH_MCP_CLIENT": "claude:desktop",
               "UV_PROJECT_ENVIRONMENT": "C:\\Users\\atall\\.venvs\\parakh" }
    }
  }
}
```

## To close

Add `ANTHROPIC_API_KEY` as a GitHub repo secret (and to `.env` for local agent runs), then re-run the `spikes` workflow.
