# Changelog

All notable changes. Framework and lens versions follow SemVer; tool schemas are versioned per toolset (plan 15 §4.4).

## [Unreleased] – R3a benchmark spike closed on manual CSVs, 2026-10-14

### Added
- Recorded fixtures `tests/fixtures/sources/niftyindices/pepb/` (NIFTY 100, MIDCAP 150, SMALLCAP 250 P/E, P/B and Div Yield, 16 Oct 2025 to 13 Oct 2026) and tests T-ADP-38 and T-ADP-39 pinning the layout and the non-price steps in the series.
- ADR-013 (coverage set plus a price-only benchmark panel) as a file; spike note `docs/spikes/R3a-nse-index-benchmarks.md`.

### Notes
- No production code, score, weight or verdict changes. The benchmark loader and mapping stay in Phase 3 (plan 09 v1.22).

## [Unreleased] – Phase 5 (calibration and stabilisation), 2026-10-11

### Added
- `config/calibration.yaml` (every threshold with a `# why:`) and `src/parakh/calibration/`: point-in-time index membership, a cached month-end momentum panel scored with the real lens, a price-only backtest (statutory costs, impact costs by cap, FIFO lots, STCG/LTCG tax by financial year, walk-forward parameter choice on a three-by-three grid), signal-outcome tracker (1M and 3M forward returns, hit rate, lift over the average stock-month), score-quintile calibration per lens, alert precision per signal with a Wilson lower bound, watchlist scorecard v1, decision journal, and the quarterly report with a CONFIRM / REVIEW / INSUFFICIENT recommendation per lens.
- The backtest **refuses** to run unless index membership history covers the window; `--allow-proxy` runs it labelled as survivorship-biased.
- Decision journal (`parakh journal add|list|due|review`, Calibration page); due reviews appear in the monthly summary. Alert ratings from Telegram and Streamlit go through one service (`services/alert_feedback.py`) with optional reason tags.
- Governance: replay determinism, drift monitoring (PSI, verdict mix, signal rate) and a backup restore test, run by the new `monthly-checks` workflow; `parakh calibrate drift|replay|restore-test`; a quarterly governance review template under `governance/reviews/`.
- Streamlit page **Calibration**; MCP toolset `calibration` (read-only: `report_summary`, `alert_precision`); audit events `AUD.JOURNAL.REVIEWED`, `AUD.BACKUP.RESTORE_TESTED`, `AUD.CALIBRATION.REPORT`, `AUD.REPLAY.CHECKED`, `AUD.DRIFT.CHECKED`.
- ADR-012 review brief and `docs/uat/UAT-5_prep.md`.

### Fixed
- `agents eval` in `cli_agents.py` carried a duplicated half-block from a merge and failed to import; the suite was red on `main`.

### Notes
- Nothing here changes a score, weight or verdict (AG-03). No framework version bump: that happens only if the calibration review changes weights.
- Verified on synthetic worlds only. The live backtest needs historical constituents and ten years of prices that this repo does not yet hold.

## [Unreleased] – Phase 4 (qualitative, watchlist and UI), 2026-10-10

### Added
- `parakh concalls fetch --symbol X` caches the latest concall transcript; `parakh agents eval --symbol X` runs the Qualitative and Devil's-advocate agents on real documents with the real model, prints status, unverified quotes and tokens, and writes `logs/agents_shadow.md`.
- `agents/runtime/factory.build_runner`: the real Claude Agent SDK runner, built only with `ANTHROPIC_API_KEY` and `uv sync --extra agents`.
- `parakh universe import --amfi FILE` fills large, mid and small from one AMFI half-yearly list (small = ranks 251+, default 250; BSE-only stocks skipped). Directory CSVs for the 30 Jun 2026 list: 100 large, 148 mid, 250 small.
- Qualitative and Devil's-advocate agents, Watchlist Curator, post-monthly step under the monthly lock, LLM failure alerts, prompt promote and rollback.
- Watchlist engine, service, Telegram approvals and queue-only Edge Function; full MCP `portfolio.*`, `jobs.*`, `data.*` toolsets.
- Streamlit app (six pages plus components), thesis and lot editors, XIRR, drawdown and HHI in the segment dashboard.
- Staged universe (`rollout`, `universe stage|import`), `jobs drain`, 500-stock load test.

### Changed
- Scheduled jobs (events, monthly with `--notify`, `jobs drain`) now get the real agent runner when a key is present; before, they ran with `runner=None` and skipped every agent step. Output stays in shadow (`agents.dry_run: true`); Qualitative stays off by flag.
- `universe.active` replaces pilot-only lookups; the `qualitative` flag ships off until the first priced eval run.

## [Unreleased] – Phase 3 (automation and shadow mode), 2026-10-04

### Added
- Seven workflows (monthly, daily watch, daily events, evening digest, Sunday heartbeat, bot poll, daily integrity) on a shared `parakh-job` action; run state lives on the `parakh-data` branch.
- Notifications: routing, cool-downs, severity and ownership rules, message templates, Telegram, email with a 30-day `.ics`, optional ntfy, owner-only bot with signed buttons, shadow logs with a `noise` box.
- Momentum watcher (shadow and 60-day replay), event watcher on NSE feeds, market context (FII/DII, breadth), NSE trading calendar.
- Thesis status-change alerts and a Home inbox; `parakh find <CODE>` searches the alert log by signal or rule code.
- MCP tools `notify.queue` and `data.get_document`; Monthly Reviewer and Event Triage agents, prompts, cards and inventory rows.
- `alerts_log` migration, `docs/FAILURE_MODES.md` with impact column (19 rows), per-stock `signal_log`.

- AWS secrets path (ADR-009): `infra/aws/parakh-github-oidc.yaml` (GitHub OIDC provider and a read-only role), `docs/AWS_SETUP.md`, and `secrets.load_ssm_environment`, which loads `/parakh/prod/*` into the environment on scheduled runs.
- Langfuse tracing on SDK v4: `generate-completion` generations (model, tokens, chat-style input and output, retries), one `agent` trace per agent run grouped by `run_id`, a `chain` trace for the summary pipeline, and Claude Agent SDK turns and tool calls through the OpenInference instrumentor (`--extra agents`). Spans are masked with the log scrubber before export. The Langfuse skill is installed under `.claude/skills/langfuse`.

### Changed
- `get_secret` no longer raises when an optional parameter is absent; parameters are read per environment path (`/parakh/prod/<NAME>`) instead of `/parakh/<NAME>`.
- Run manifests now carry alert, suppressed, agent-run, failed-step and token counts; the heartbeat checks the monthly 12:00 IST and watcher 19:30 IST service levels.

### Not yet
- `portfolio.positions` (AC-F24.4) and `jobs.request_refresh` arrive in Phase 4.

### Fixed
- Daily watch, events and digest default to the latest session whose data can exist (`service_levels.session_data_ready_ist`), so a scheduled run that GitHub starts after midnight IST no longer fails with a stale-price error.

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
