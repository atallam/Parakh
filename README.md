# Parakh

Personal NSE stock-analysis framework with value and momentum lenses and Telegram alerts

Scaffolded with `aiscaffold` 1.0.0 at tier **Production (live system)** on 2026-09-28.

## Quick start (PowerShell)

```powershell
uv sync
uv run pre-commit install
Copy-Item .env.example .env   # then fill in the keys
uv run pytest
uv run parakh doctor
```

## Layout

| Path | What lives there |
|---|---|
| `src/parakh/prompts/` | Prompt YAML files, rendered with Jinja2. Never hardcode prompts |
| `src/parakh/llm/` | The only code that talks to the LLM provider |
| `src/parakh/agents/` | Agents: prompt in, validated Pydantic object out |
| `src/parakh/mcp/toolsets/` | Pure, read-only tools with unit tests |
| `src/parakh/orchestration/` | Pipelines and graphs, including human-review checkpoints |
| `src/parakh/observability/` | Logging, tracing, cost, alerts |
| `tests/` | Tests; the LLM is always faked |

## Checklist

This project follows the SCAIX checklist for its tier. Check it any time:

```powershell
uv run path\to\aiscaffold.py check .
```
