# CLAUDE.md: Parakh

Guidance for AI coding assistants (Claude, Copilot, Cursor) working in this repo.

## Project

- Personal NSE stock-analysis framework with value and momentum lenses and Telegram alerts
- Tier: **Production (live system)**. Every change keeps the tier's checklist green (`aiscaffold.py check .`).
- Package: `src/parakh`. Python 3.12, managed with uv.
- Plan docs live in docs/plan/. Start at docs/plan/README.md and load only the owner doc for the task (about 45,000 words is too much context).
- When docs disagree: 13 → ADRs in 04 → 07/08 → 14 → topic docs → 00 → archive.
- Key everything on ISIN, never on the ticker (M&M has an ampersand).
- The repo lives at `Stock Analysis\parakh` in OneDrive (plan 13 D10, v1.17). The .env sits one folder up and is found automatically (or through PARAKH_ENV_FILE, D19). Never print its values.
- Keep the virtual environment outside OneDrive: set `UV_PROJECT_ENVIRONMENT` (e.g. `C:\Users\atall\.venvs\parakh`). Never create `.venv` in the repo.
- PAN, names, addresses and DP/client IDs from a CAS are never stored, logged or sent to an LLM (plan 13 P6).
- Agents are MCP-first (plan 13 D20, plan 15): they reach data only through the parakh-mcp toolsets in src/parakh/mcp/, and only propose. Real agents run on the Claude Agent SDK behind agents/runtime/AgentRunner (D21); the Phase 0.5 spike builds ClaudeSDKRunner and FakeRunner.
- The generated summarizer agent, text_stats tool, summarize prompt and llm/client.py are scaffold samples. Replace them as the real agents and toolsets land; keep the tests' shape.

## Rules

- Prompts live in `src/parakh/prompts/` as YAML and render with Jinja2. No prompt strings in code.
- Only `src/parakh/llm/` may import the provider SDK. Agents call `LLMClient`; business logic never calls the LLM.
- Every agent loop has a hard cap (`llm_max_iterations`). Every LLM output is parsed into a Pydantic model before use.
- LLM calls go through `LLMClient.complete`, which retries with exponential backoff and logs tokens, latency and cost.
- Tools in `mcp/toolsets/` are pure and read-only: no network, no writes, no LLM.
- Secrets come from `.env` via `config.get_settings()`. Never print, log or commit them.
- Run text through `privacy.redact_pii` before it goes to a cloud model.
- Tests never call a real LLM or the network: use the `fake_llm` fixture.
- A prompt change is a deployment: add a new version file, update `prompts/registry.yaml`, run the golden tests.

## Commands (PowerShell)

```powershell
uv sync                      # install
uv run pytest                # tests
uv run ruff check . ; uv run ruff format .
uv run pyright               # types
uv run parakh doctor     # config check, no external calls
```
