# Changelog

All notable changes. Framework and lens versions follow SemVer; tool schemas are versioned per toolset (plan 15 §4.4).

## [Unreleased] – Phase 0 (skeleton), 2026-09-29

### Added
- **Config:** `config/universe.yaml` with the 7 pilot stocks keyed by ISIN (D3, D18 golden stocks, D24 profiles), `lenses.yaml`, `flags.yaml` (plan 09 feature flags), `agents.yaml` (roster, all disabled, dry run), `ui_tokens.yaml` (plan 12 palette and status vocabulary); Pydantic schemas with ISIN check-digit validation; `parakh config validate`.
- **Audit core (F21, ADR-007):** ULIDs, `RunContext`, `AUD.*` event enum and record model, hash-chained JSONL outbox, `audited_step`, `run_lifecycle` (one START, one END/ABORT), run manifests, `parakh audit verify`.
- **Lens contract and registries (F18):** `Lens` / `LensResult` / `StockContext`, metric, signal, rule and lens registries with ID and docstring checks, lens contract tests, generated catalogues (`parakh catalogue`).
- **parakh-mcp skeleton (F24, ADR-010/012):** tool registry (ID, tier, annotations, Pydantic models; state-changing verbs refused), audit middleware (`AUD.MCP.TOOL_CALL` / `TOOL_DENIED`), stdio server on MCP SDK 2.x, first tool `TOOL.audit.get_run`, `.mcp.json`.
- **Agent runtime (F25, ADR-011):** `AgentSpec`, `AgentRunner`, `FakeRunner` with turn, budget and output limits.
- **UI/UX (F22):** `render/format.py` (₹ en-IN, L/Cr, %, pp, ×, IST dates) and status tokens.
- **Supabase:** first migration (securities, runs, run_steps, append-only `audit_events` and `mcp_tool_calls`, proposals and queues, RLS, `parakh_mcp` and `parakh_staging` roles, `staging` schema), generated seed, pgTAP tests.
- **Governance and CI:** ADR-001…012, doc lint, token and layering lint, traceability generator (`docs/TRACEABILITY.md`), synthetic CAS fixtures, CI jobs for L0 static, tests, database and security.
- `docs/plan/` copy of the plan docs; `run.py`.

### Changed
- Redaction covers NSDL DP/client IDs, CDSL BO IDs and holdings quantity/amount fields at any depth (AC-F21.11).
- Removed the scaffold sample tool `text_stats` (replaced by the real audit toolset).
