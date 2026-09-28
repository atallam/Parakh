# Parakh

Personal NSE stock-analysis framework: value and momentum lenses, a verdict policy, Telegram
alerts and an MCP server so Claude can read the results. Plan of record: `docs/plan/` (start at
`docs/plan/README.md`; decisions in plan 13, dates in plan 09).

**Status:** Phase 0 (skeleton) · Production tier · pilot universe of 7 stocks.

## Quick start (PowerShell)

The repo lives in OneDrive (`Stock Analysis\parakh`, plan 13 D10). Keep the virtual environment
outside OneDrive, once per machine:

```powershell
[Environment]::SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", "C:\Users\atall\.venvs\parakh", "User")
# open a new PowerShell window, then:
uv sync
uv run pre-commit install
uv run pytest
uv run parakh doctor            # .env is found one folder up (D19); no external calls
uv run parakh config validate   # config/*.yaml against their schemas; lists the pilot ISINs
uv run parakh run --mode dummy  # Phase 0 exit gate: audit START/END + run manifest
uv run parakh audit verify      # re-check the audit hash chain
```

## Commands

| Command | What it does |
|---|---|
| `parakh doctor` | Which secrets are set (never their values) |
| `parakh config validate` | Validates `config/*.yaml`, including ISIN check digits |
| `parakh run --mode dummy` | End-to-end skeleton run (monthly/watch/events arrive in Phases 2–3) |
| `parakh audit verify` | Recomputes the audit hash chain from genesis |
| `parakh catalogue [--check]` | Regenerates `docs/METRICS.md`, `SIGNALS.md`, `RULES.md`, `TOOLS.md`, `AUDIT_EVENTS.md` |
| `parakh mcp serve` | The `parakh-mcp` server over stdio (Claude Code reads `.mcp.json`) |
| `python run.py …` | Same as `parakh …` |

Dev tools in `tools/`: `lint_rules.py` (token + layering lint), `doclint.py`, `traceability.py`,
`make_seed.py`, `make_synthetic_cas.py`.

## Layout

| Path | What lives there |
|---|---|
| `config/` | `universe.yaml` (pilot, keyed by ISIN), `lenses.yaml`, `flags.yaml`, `agents.yaml`, `ui_tokens.yaml` |
| `src/parakh/audit/` | RunContext + ULIDs, `AUD.*` events, hash-chained outbox, `audited_step`, run manifests |
| `src/parakh/configs/` | Pydantic schemas and loader for `config/` |
| `src/parakh/lenses/` · `registry/` | The Lens contract; metric, signal, rule and lens registries; catalogue generator |
| `src/parakh/mcp/` | `parakh-mcp`: tool registry (ID + tier), audit middleware, stdio server, toolsets |
| `src/parakh/agents/runtime/` | `AgentRunner` interface (Claude Agent SDK adapter from the Phase 0.5 spike) |
| `src/parakh/services/` | The only API the CLI, Streamlit, Telegram and MCP may call; `view_models.py` |
| `src/parakh/render/` | `format.py` (₹ en-IN, L/Cr, %, dates) and status tokens for every surface |
| `src/parakh/orchestration/` | Deterministic jobs made of audited steps |
| `supabase/` | Migrations (RLS, append-only audit, `parakh_mcp` role, staging schema), seed, pgTAP tests |
| `docs/adr/` | ADR-001…012 |
| `docs/plan/` | The plan docs (canonical copy from Phase 0) |
| `tests/` | Unit, contract, static (L0), MCP, agents; `tests/fakes/` has `FakeRunner`; CAS fixtures are synthetic |

State (audit outbox, run manifests) goes to `state/` (git-ignored) or `PARAKH_STATE_DIR`.

## Checklist

This project follows the SCAIX checklist for its tier:

```powershell
uv run ..\Parakh-scaffold\aiscaffold.py check .
```

*Personal analytical framework; not investment advice.*
