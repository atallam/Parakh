# Changelog

All notable changes. Framework and lens versions follow SemVer; tool schemas are versioned per toolset (plan 15 §4.4).

## [Unreleased] – Phase 3 (automation and shadow mode), 2026-10-04

### Added
- Seven workflows (monthly, daily watch, daily events, evening digest, Sunday heartbeat, bot poll, daily integrity) on a shared `parakh-job` action; run state lives on the `parakh-data` branch.
- Notifications: routing, cool-downs, severity and ownership rules, message templates, Telegram, email with a 30-day `.ics`, optional ntfy, owner-only bot with signed buttons, shadow logs with a `noise` box.
- Momentum watcher (shadow and 60-day replay), event watcher on NSE feeds, market context (FII/DII, breadth), NSE trading calendar.
- Thesis status-change alerts and a Home inbox; `parakh find <CODE>` searches the alert log by signal or rule code.
- MCP tools `notify.queue` and `data.get_document`; Monthly Reviewer and Event Triage agents, prompts, cards and inventory rows.
- `alerts_log` migration, `docs/FAILURE_MODES.md` with impact column (19 rows), per-stock `signal_log`.

### Changed
- Run manifests now carry alert, suppressed, agent-run, failed-step and token counts; the heartbeat checks the monthly 12:00 IST and watcher 19:30 IST service levels.

### Not yet
- `portfolio.positions` (AC-F24.4) and `jobs.request_refresh` arrive in Phase 4.

## Phase 0.5 (infrastructure spikes), 2026-09-29

### Added
- Spike scripts (`spikes/`), the `spikes` workflow and outcome notes (`docs/spikes/S1…S8`).
- `adapters/concalls.py`: Screener Concalls → BSE-filed transcript provider, ported from Drishti (extractor, validator with reasons, Q&A-preserving truncation, staleness flag).
- `adapters/screener_export.py`: Data Sheet v2.1 parser with data-quality checks.
- `adapters/corporate_actions.py`: split/bonus back-adjustment and unexplained-gap detection.
- `storage/supabase_repo.py` (runs, steps, append-safe audit inserts, `SupabaseAuditSyncer`) and `storage/prices.py` (Parquet per ISIN/year in Storage or a local folder, DuckDB queries).
- `notify/telegram.py`: `Notifier` interface and Telegram adapter.
- `agents/runtime/claude_sdk.py`: `ClaudeSDKRunner` and `build_options` (optional extra `agents`).
- Recorded source fixtures from a GitHub runner (NSE, BSE, niftyindices, AMFI, Screener, BSE transcript PDF, NSE XBRL) with parsing and T1↔T2 tie-out tests.

### Changed
- Synthetic CAS fixtures now match casparser 1.4.1's real output shape.
- Dependencies: httpx, beautifulsoup4, pymupdf, openpyxl, pandas, pyarrow, duckdb; `spikes` group (yfinance); `agents` extra (claude-agent-sdk).

## Phase 0 (skeleton), 2026-09-29

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
