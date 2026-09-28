# CLAUDE.md: Parakh

Guidance for AI coding assistants (Claude, Copilot, Cursor) working in this repo. AGENTS.md points here.

## Project

- Personal NSE stock-analysis framework (value + momentum lenses, verdict policy, Telegram alerts, MCP server).
- Tier: **Production**. Every change keeps the SCAIX checklist green (`aiscaffold.py check .`).
- Package: `src/parakh`. Python 3.12, managed with uv.
- Plan docs live in `docs/plan/` (canonical from Phase 0; the OneDrive FRAMEWORK folder and the Claude project are mirrors). Start at `docs/plan/README.md` and load only the owner doc for the task.
- When docs disagree: 13 → ADRs (`docs/adr/`) → 07/08 → 14 → topic docs → 00 → archive. Dates live only in 09, decisions only in 13 (doc lint).
- **Scope freeze until the M1 review (D25):** new ideas are backlog items, not code.
- Key everything on **ISIN**, never the ticker (M&M has an ampersand).
- The repo lives at `Stock Analysis\parakh` in OneDrive (D10). The .env sits one folder up and is found automatically (or through PARAKH_ENV_FILE, D19). Never print its values.
- Keep the virtual environment outside OneDrive (`UV_PROJECT_ENVIRONMENT`, e.g. `C:\Users\atall\.venvs\parakh`). Never create `.venv` in the repo.
- PAN, names, addresses and DP/client IDs from a CAS are never stored, logged or sent to an LLM (P6). Tests use the synthetic CAS only.

## IDs (plan 04 §3.1)

`MET.<lens-or-common>.<name>` metrics · `M<nn>`/`E<nn>` signals · `RULE.<area>.<name>` rules · `LENS.<name>` · `TOOL.<toolset>.<name>` · `AGENT.<name>` · `AUD.<DOMAIN>.<ACTION>` audit events · `ADR-nnn` · `AC-Fnn.m` acceptance criteria · `T-<AREA>-<nn>` tests. Registries refuse malformed IDs; catalogues in `docs/` are generated (`parakh catalogue`).

## Rules

- **Thresholds only in YAML**, each with a `# why:` comment; schemas in `src/parakh/configs/models.py`.
- **Audit** (plan 10 §14): every state-changing service method calls `audit.emit`; every pipeline step runs in `audited_step`; jobs run inside `run_lifecycle` (one START, one END/ABORT). New event types go in `audit/events.py`. No `print()` outside the CLI; use structlog.
- **Layering:** `app/` and `src/parakh/mcp/` never import `analytics/`, `lenses/` or `adapters/`; they call `services/` (lint: `tools/lint_rules.py`).
- **MCP tools** (plan 15 §4.4): register with `Toolset(...).tool(name, tier=..., title=...)`; Pydantic input and output models; a docstring written for a model; 5–20 lines over one service call. Never a tool that approves, rejects, edits, deletes, publishes or changes config (AG-03). Policy (allow-lists, masking, rate limits) lives in the middleware, not in prompts.
- **Agents** run only through `AgentRunner`; allowed tools are `mcp__parakh__*` only; CI uses `FakeRunner`, never a real model.
- **UI:** no hex colour outside `config/ui_tokens.yaml`; format numbers only with `render/format.py`; unit suffixes `_pct`, `_ratio`, `_x`, `_cr`, `_inr`, `_days`, `_bps`.
- **Metrics and signals:** test-first against oracle values; docstrings need `Formula / Meaning / Pitfalls / Source`.
- Prompts live in `src/parakh/prompts/` as YAML. Only `src/parakh/llm/` may import a provider SDK. Every LLM output is parsed into a Pydantic model; every loop has a hard cap.
- Tests never call a real LLM or the network (sockets are blocked). Mark tests that prove an acceptance criterion with `@pytest.mark.ac("AC-F21.1")`.
- The summarizer agent, summarize prompt and `llm/client.py` are scaffold samples kept for the checklist; replace them as the real agents land.

## Commands (PowerShell)

```powershell
uv sync
uv run pytest
uv run ruff check . ; uv run ruff format .
uv run pyright
uv run python tools/lint_rules.py ; uv run python tools/doclint.py
uv run parakh catalogue          # after adding metrics, signals, rules, tools or AUD events
uv run python tools/traceability.py
uv run parakh doctor ; uv run parakh config validate ; uv run parakh run --mode dummy
```
