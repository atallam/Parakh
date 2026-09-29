---
title: Audit, Logging & Governance Layer
version: 1.0 (MCP and agents: `AUD.MCP.*` / `AUD.AGENT.*`, tool permission tiers, proposals, `mcp_tool_calls`/`proposals`/`notify_queue`/`job_requests` tables — plan 15; v0.9: §16 now points to 09/14; v0.8 baseline: CAS data classification, prompt rollback event, secrets via SSM — plan 13 P1/P3/P6; v0.7: UI and channel interaction events; `channel` on human actions — plan 12, plan 03 §4)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
related: 04 (standards, ADRs) · 05 (data model) · 07 (PRD FR-21/22, NFR-11/12) · 08 (F21) · 09 (rollout)
principle: "Every step that reads, computes, decides, notifies or changes something leaves a record: who, what, when, why, with which inputs, code and config."
scale: Proportionate for a single-owner personal system, but built on the same patterns used in regulated model-risk and data governance, so it scales if the project grows
---

# Audit, Logging and Governance Layer

## 1. Why this layer, and what "end to end" covers

The system makes **decisions that affect money** (verdicts, alerts, watchlist changes), uses **unreliable inputs** (scraped and third-party data, LLM outputs) and runs **unattended**. Without this layer, you can't answer:

- *"Why did it say BUY on POLYCAB in March, and would it still say so with today's rules?"*
- *"Why didn't I get an alert when XYZ broke its 200 DMA?"*
- *"Which number in this report came from which source, and when?"*
- *"Who or what changed this weight, this holding, this watchlist entry, and why?"*
- *"Did the LLM make that up?"*

**End-to-end coverage: every step emits records.**

```
 TRIGGER ─► CONFIG ─► FETCH ─► VALIDATE ─► TRANSFORM ─► METRICS ─► LENSES ─► LLM AGENTS ─► VERDICT ─► RENDER ─► PUBLISH ─► NOTIFY
 (cron/     (load +   (per     (pandera,   (adjust,     (registry) (scores)  (qual, devil's (policy)  (md/json)  (OneDrive,  (Telegram,
  manual/    hash)     source)  reconcile)  point-in-    │          │         advocate)      │                   git)       suppressed
  event)                                    time)        │          │           │            │                               too)
    │           │        │         │           │         ▼          ▼           ▼            ▼            ▼          ▼          ▼
    └───────────┴────────┴─────────┴───────────┴──── run_id / step_id / isin correlation on every record ─────────────────────────┘
                                                             ▲
 HUMAN ACTIONS: watchlist approvals · holdings edits · thesis edits · overrides · config/weight/prompt changes · journal entries
 AGENT + MCP ACTIONS (v1.0): every tool call (agents and your Claude sessions) · proposals · queued notifications · refresh requests
 PLATFORM ACTIONS: deployments (git SHA) · secret rotation · access to the UI · backups · re-scoring history
```

---

## 2. Four sub-layers (each with a clear job)

| Sub-layer | Question it answers | Mutability | Store | Retention |
|---|---|---|---|---|
| **① Operational logs** | "What happened technically?" (debugging) | Append; rotated | structlog JSON → files + GitHub Actions logs | 90 days |
| **② Step ledger and run manifests** | "What did each run do, with which inputs and outputs, and can I reproduce it?" | Append-only | `runs`, `run_steps` tables + `runs/<run_id>/manifest.json` | 3 years |
| **③ Audit trail** | "Who or what changed or decided what, when and why?" | **Append-only, hash-chained (tamper-evident)** | `audit_events` table + local JSONL outbox | **Indefinite** (small) |
| **④ Lineage and explainability** | "Where did this number or verdict come from?" | Append-only per run | `metric_values` (with source refs), `verdict_explanations`, raw-input hashes | As long as the snapshot (24-month raw inputs, indefinite hashes) |

Plus two cross-cutting records: **LLM traces** (Langfuse + `llm_calls` table) and **alert delivery logs** (`alerts_log`, including *suppressed* alerts).

---

## 3. Correlation and identity (what makes it searchable)

| Field | Format | Present on |
|---|---|---|
| `run_id` | ULID (time-sortable), e.g. `01JB6X…` | Every log line, step, audit event, LLM call, alert, snapshot, report footer |
| `step_id` | `<run_id>.<step_name>.<seq>`, e.g. `…fetch_prices.03` | Logs, step ledger, lineage |
| `trace_id` | Langfuse trace per agent invocation | LLM calls |
| `isin` | Security key | Anything stock-specific |
| `actor_type` / `actor_id` | `scheduler:gha-monthly`, `user:avinash`, `agent:qualitative@1.3.0`, `agent:monthly_reviewer@1.0.0`, `ci:github`, `claude:desktop` / `claude:code` (you, through MCP) | Audit events |
| `mcp_call_id` / `agent_run_id` *(v1.0)* | ULIDs | MCP tool calls, agent runs, proposals |
| `code_version` | Git commit SHA | Runs, audit events |
| `config_hash` / `framework_version` / `lens_versions` | SHA-256 / SemVer | Runs, snapshots |
| Event type IDs | `AUD.<DOMAIN>.<ACTION>` (§4) | Audit events |

This follows the ID-anchored traceability convention (plan 04 §3.1). Searching `01JB6X` finds everything one run touched. Searching `AUD.WATCHLIST.APPROVED` finds every approval you ever made.

---

## 4. Audit event taxonomy

| Domain | Event IDs | Emitted when |
|---|---|---|
| Run lifecycle | `AUD.RUN.START`, `AUD.RUN.END`, `AUD.RUN.ABORT`, `AUD.RUN.INVALIDATED` | Every job; invalidation is a human action with a reason |
| Data | `AUD.DATA.FETCH`, `AUD.DATA.FALLBACK_USED`, `AUD.DATA.VALIDATION_FAIL`, `AUD.DATA.CONFLICT`, `AUD.DATA.CORP_ACTION_APPLIED`, `AUD.DATA.RESTATEMENT_DETECTED` | Per source per run (aggregated counts; per-stock only on failure) |
| Scoring | `AUD.SCORE.COMPUTED` (batch), `AUD.VETO.TRIGGERED`, `AUD.VERDICT.CHANGED` | Verdict changes and vetoes per stock; computed scores per batch |
| LLM / agents | `AUD.LLM.CALL`, `AUD.LLM.VALIDATION_FAIL`, `AUD.LLM.CITATION_UNVERIFIED`, `AUD.LLM.BUDGET_STOP`, `AUD.LLM.INJECTION_SUSPECTED` | Every call (details in `llm_calls`) |
| Agent runs *(v1.0)* | `AUD.AGENT.START`, `AUD.AGENT.END` (status: ok / pending / failed), `AUD.AGENT.TURN_LIMIT`, `AUD.AGENT.PROPOSAL` | Every agent invocation; every proposal it writes |
| MCP *(v1.0)* | `AUD.MCP.TOOL_CALL` (tool ID, tier, client, args hash, result hash, latency), `AUD.MCP.TOOL_DENIED` (not on the allow-list, tier refused, masking refused), `AUD.MCP.RATE_LIMITED` | Every tool call, from agents and from your Claude sessions (details in `mcp_tool_calls`) |
| Signals and alerts | `AUD.SIGNAL.STATE_CHANGE`, `AUD.ALERT.SENT`, `AUD.ALERT.SUPPRESSED` (reason: dedupe / cool-down / dry-run / digest-batched / quiet-hours), `AUD.ALERT.DELIVERY_FAILED` | Every alert decision, **including the ones not sent** |
| Watchlist | `AUD.WATCHLIST.AUTO_ADDED`, `…AUTO_REMOVED`, `…SUGGESTED`, `…APPROVED`, `…REJECTED`, `…SNOOZED`, `…EXPIRED`, `…MANUAL_ADD`, `…MANUAL_REMOVE` | Plan 06 rules and every human decision |
| Holdings | `AUD.HOLDINGS.IMPORT`, `…LOT_ADDED`, `…LOT_EDITED`, `…SALE_RECORDED`, `…DELETED` | Every change, with before and after |
| Human judgement | `AUD.OVERRIDE.SET` / `…EXPIRED` (archetype, sector profile, verdict), `AUD.THESIS.CHANGED`, `AUD.JOURNAL.ENTRY` | Overrides need a reason and an expiry date |
| Change management | `AUD.CONFIG.CHANGED`, `AUD.PROMPT.PROMOTED`, `AUD.PROMPT.ROLLED_BACK` *(v0.8)*, `AUD.LENS.VERSION_BUMP`, `AUD.HISTORY.RESCORED`, `AUD.DEPLOY` | From CI on merge to main |
| UI and channel interactions *(v0.7)* | `AUD.ALERT.FEEDBACK` (useful / noise), `AUD.ALERT.MUTED`, `AUD.REVIEW.MARKED`, `AUD.BOT.COMMAND` | 👍/👎 and mute taps, "mark reviewed" in the review inbox, bot commands (plan 03 §4.3, plan 12 §5.1) |
| Security and platform | `AUD.ACCESS.UI_LOGIN`, `AUD.ACCESS.BOT_REJECTED` *(v0.7)*, `AUD.SECRET.ROTATED`, `AUD.BACKUP.COMPLETED`, `AUD.INTEGRITY.CHECK` | Hosted UI logins, messages to the bot from any chat other than the owner's, key rotations, backups, the daily chain check |

*(v0.7)* Every human action also records **`channel`** (`streamlit` | `telegram` | `cli`), so "approved from phone" and "approved at desk" are distinguishable. Telegram actions carry the id of the message they answered.

### 4.1 Audit record schema

```json
{
  "event_id": "01JB6XQ7…",            "event_type": "AUD.WATCHLIST.APPROVED",
  "ts_utc": "2026-12-03T14:05:11Z",    "trading_date_ist": "2026-12-03",
  "run_id": "01JB6X…",                 "step_id": null,
  "actor_type": "user",                "actor_id": "avinash",
  "entity_type": "watchlist_entry",    "entity_id": "wl_0192", "isin": "INE…",
  "action": "promote_system_to_my",
  "before": {"list": "system"},        "after": {"list": "my"},
  "reason": "Strong ROIIC; wait for pullback to 50 DMA",
  "evidence_ref": "snapshot:2026-11/INE….json#verdict",
  "code_version": "a91f3c2",           "config_hash": "sha256:…", "framework_version": "1.0.0",
  "prev_hash": "sha256:…",             "record_hash": "sha256:…"
}
```

### 4.2 Tamper evidence (cheap and effective)

1. **Append-only.** A Postgres trigger rejects `UPDATE` and `DELETE` on `audit_events`. RLS allows `INSERT` and `SELECT` only; even the app's service role can't rewrite history. Corrections are **new events** that reference the original.
2. **Hash chain.** `record_hash = sha256(prev_hash + canonical_json(record))`.
3. **Git anchoring.** Each day's chain head hash is committed to the repo (`audit/anchors/2026-12-03.txt`). Rewriting the database would then also need a git history rewrite, which is visible.
4. **Daily integrity check** (`AUD.INTEGRITY.CHECK`) verifies the chain and alerts ❌ on any break.

### 4.3 Reliability: the outbox pattern

Audit writes must never be lost when Supabase is unreachable. Every event is written first to a local **JSONL outbox** (`audit/outbox/<date>.jsonl`), then flushed to Postgres; a flush confirmation marks it synced. A run **can't complete as SUCCESS** while audit events remain unsynced; it ends as `SUCCESS_AUDIT_PENDING` and retries on the next job.

---

## 5. Step ledger and reproducibility

Every pipeline step runs inside a context manager, so no step can skip logging:

```python
with audited_step(
    ctx, "fetch_prices", source="yfinance"
) as step:  # AUD step start/end, timing, status
    frame = price_adapter.fetch(universe, asof=ctx.asof)
    step.record_output(rows=len(frame), sha256=frame_hash(frame))  # output hash → lineage
```

**`runs/<run_id>/manifest.json`** records:

- Trigger (cron, manual or event, plus who).
- As-of date, universe and tiers.
- Code SHA, config hash, framework and lens versions, prompt versions.
- Every step's status, duration and I/O hashes.
- Source as-of dates, data-quality summary.
- LLM tokens and cost, alerts sent and suppressed, audit chain head.

**Replay:** `python run.py replay <run_id>` checks out the recorded code SHA, loads the archived raw inputs (kept 24 months) and the recorded config, and re-runs. **Deterministic outputs must match the stored hashes.** LLM outputs are replayed from cache, not re-generated. A monthly CI job replays one random past run, as a determinism regression test.

---

## 6. Lineage and explainability ("Explain this verdict")

Each verdict stores a traversable chain:

```
Verdict: BUY (momentum-led)  [policy rule VP.matrix.fair_value×strong_momentum]
 ├─ Value score 58  [LENS.value@1.2.0]
 │    ├─ valuation 0.52 ← MET.value.pe_vs_5y_median = 0.91 ← pe_ttm 38.2 (screener, asof 2026-11-28, raw sha256:…)
 │    │                                               ← median_5y 42.1 (derived from prices + eps_ttm series)
 │    └─ governance 0.70 ← MET.gov.promoter_pledge_pct = 0 (NSE shareholding Q2FY27, filed 2026-10-19)
 ├─ Momentum score 81  [LENS.momentum@1.1.0] ← RS pct 88 vs NIFTY MIDCAP 150 … signals M01, M12
 ├─ Qualitative 3.8/5 (confidence only)  [agent:qualitative@1.3.0, prompt QUAL.v7, trace lf_…]
 │    └─ citations: concall Q2FY27 (exact quote verified in BSE-filed transcript p.6) …
 └─ Regime: Risk-On (VIX 12.4, breadth 61%)
```

- **CLI:** `python run.py explain POLYCAB --run 2026-11` prints this tree.
- **Streamlit:** "Explain" button on each Stock Detail page.
- **Report:** §14 "Data quality & sources" and the footer carry `run_id` and a short lineage summary.

---

## 7. LLM and agent governance

| Control | Implementation |
|---|---|
| **Prompt registry** | `src/prompts/*.yaml` with ID + SemVer (`QUAL.v7`); every call logs the prompt ID/version, model ID and parameters |
| **Promotion gate** | A new prompt or model version must pass the **golden eval set** (e.g. 10 frozen concalls with expected ratings, citations and guidance extraction) before `AUD.PROMPT.PROMOTED`; results stored with the promotion event |
| **Output validation** | Pydantic schema; failures are logged (`AUD.LLM.VALIDATION_FAIL`) and retried at most N times, then the item is marked "qualitative pending" |
| **Grounding** | Every rating needs a citation; guidance numbers are verified against the filed transcript; unverified claims are flagged ⚠️ (`AUD.LLM.CITATION_UNVERIFIED`) |
| **Numbers firewall** | LLM outputs can never feed a score (enforced by types: the lenses accept no LLM-sourced fields; a contract test enforces it) |
| **Prompt-injection defence** | Concall transcripts, news and filings are **untrusted data**. Content is returned by MCP tools only in an `untrusted_content` field with provenance, and wrapped as data with instructions to ignore any embedded directives; *(v1.0)* agents have **no state-changing tools**: only propose, notify and job-request tools, which take IDs and enums rather than text (plan 15 AG-03, AG-06); suspicious patterns ("ignore previous instructions", URLs asking for actions) are flagged (`AUD.LLM.INJECTION_SUSPECTED`) |
| **Privacy** | Holdings and quantities are never sent to an LLM, except the minimal fields for the thesis check (no account details) |
| **Cost control** | Per-run token budget with a hard stop (`AUD.LLM.BUDGET_STOP`); cost per run in the manifest and the monthly message |
| **Tracing** | Langfuse traces linked by `trace_id` ↔ `llm_calls` row ↔ `run_id`; traces exported monthly to the store (free-tier retention may be limited) |
| **Agent cards** | `docs/agents/<agent>.md`: purpose, inputs, **allowed MCP tools and tiers**, model and prompt pins, `max_turns`, token budget, eval results, known failure modes |
| **Tool permission tiers** *(v1.0)* | R read · P propose · N notify · J job request (plan 15 §4.2). Tiers are checked by the server on every call; an agent's allow-list is in `config/agents.yaml` and reviewed like a prompt (PR only) |
| **Runtime hardening** *(v1.0)* | Claude Agent SDK built-in tools disabled; non-bypass permission mode; stdio transport only (ADR-011, ADR-012); a contract test fails the build otherwise |
| **Proposal lifecycle** *(v1.0)* | `proposed → approved / rejected / expired`, decided only by you in Streamlit, Telegram or the CLI; the decision event references the proposal and the agent run that made it |

---

## 8. Model governance (scoring logic = "models")

A lightweight version of model-risk-management practice (e.g. the ideas in the US Federal Reserve's SR 11-7 guidance), scaled to a personal system:

| Control | Implementation |
|---|---|
| **Model inventory** (`model_inventory` table + `docs/MODELS.md`, generated) | Every lens, agent and verdict policy: ID, version, status (`active` / `informational` / `retired`), owner, last validation date, last calibration result, known limitations |
| **Model cards** | `docs/lenses/<lens>.md`: intended use, not-intended use (e.g. "value lens isn't valid for loss-making companies"), inputs, assumptions, limitations |
| **Change control** | Weight, threshold, policy and prompt changes go **only through a PR** to `main` (even solo): branch protection + required CI checks (tests, golden, contract, catalogues, replay) + a PR checklist ("why", expected impact, framework version bump, ADR if significant) |
| **Impact preview** | CI posts a "re-score diff" on config PRs: how many verdicts would change across the last 3 months if merged |
| **Re-scoring** | After merge, `rescore` runs with `AUD.HISTORY.RESCORED`; old and new histories are both kept (history is versioned, not overwritten) |
| **Ongoing monitoring** | Score and verdict **distribution drift** month over month (a sudden shift in the share of BUYs usually means a bug or a data issue); calibration (F17) |
| **Overrides** | You can override archetype, sector profile or verdict with a **required reason and expiry**; overrides are listed in every monthly summary until they expire |
| **AI-assisted code changes** | Commits from AI coding assistants carry a trailer (e.g. `Co-Authored-By:`) and go through the same PR checks; the PR template includes "AI-generated sections reviewed" |

---

## 9. Data governance

| Control | Implementation |
|---|---|
| **Source registry** (`sources` table + `docs/SOURCES.md`) | source_id, tier (T1–T3), data types, access method, **terms-of-use note**, refresh cadence, last successful fetch, 30-day failure rate |
| **Data-quality SLAs** | e.g. price coverage ≥ 99% of universe, fundamentals freshness ≤ 1 quarter + 60 days; breaches → alert + `AUD.DATA.*` |
| **Quality scorecard** | Per run: coverage, conflicts, fallbacks used, validation failures; shown in the manifest and monthly summary |
| **Retention** | See §11; raw inputs 24 months for replay |
| **Backups** | Weekly `pg_dump` of Supabase → **encrypted** (age) → stored in a private location; monthly restore test in CI; `AUD.BACKUP.COMPLETED` |
| **Classification** | `public` (market data), `personal` (reports), `sensitive` (holdings, journal, tax); *(v0.8)* `restricted` (CAS identifiers: PAN, name, address, DP/client IDs: never persisted, never logged, never sent to an LLM, plan 13 P6); sensitive fields encrypted at rest and masked in logs |

---

## 10. Logging standards (operational)

- **Structured only:** structlog JSON; required keys `ts, level, run_id, step_id, event, isin?, lens_id?, metric_id?, signal_id?, source?, latency_ms?`.
- **Levels:** `DEBUG` (local only), `INFO` (step start/end, counts), `WARNING` (fallback used, data conflict), `ERROR` (step failed, recoverable), `CRITICAL` (run abort).
- **Redaction:** a processor masks secrets, tokens, holdings quantities and account IDs. A unit test feeds known secrets and asserts they're masked.
- **No PII in logs:** ISINs and symbols are fine; quantities, costs and account names are masked.
- **Sampling:** per-stock INFO logs are summarised at batch level for Tier B (500 stocks), and detailed only on warnings or errors.
- **Shipping:** GitHub Actions logs are kept 90 days by GitHub. The run summary, step ledger and audit events live in our store, so nothing important depends on GitHub's log retention.

---

## 11. Retention summary

| Record | Retention | Where |
|---|---|---|
| Operational logs | 90 days | Files / GitHub Actions |
| Step ledger, run manifests | 3 years | Supabase + `runs/` in repo |
| **Audit trail** | **Indefinite** (append-only, small) | Supabase + JSONL outbox archive + daily git anchors |
| Snapshots, reports, HISTORY | Indefinite | Git + OneDrive |
| Raw source inputs | 24 months (replay window) | Parquet / object storage |
| LLM traces | 12 months detailed; summaries indefinite | Langfuse → exported `llm_calls` |
| Alerts log (incl. suppressed) | 3 years | Supabase |
| Backups | 12 weekly + 12 monthly | Encrypted archive |

---

## 12. Governance cadence and reporting

| Rhythm | Review | Output |
|---|---|---|
| **Every run** | Automatic: integrity check, audit completeness test (every run has START/END, every verdict change has an audit event), DQ scorecard | **Governance line in the monthly Telegram message:** "🛡 Integrity ✅ · DQ 97% · 2 fallbacks · 0 overrides active · LLM ₹180 · config changes: PR #12" |
| **Monthly** | Exceptions: invalidated runs, suppressed-alert sample, overrides nearing expiry, open DQ breaches | Governance section in the segment summary |
| **Quarterly** | Model review (inventory, calibration, drift, limitations), prompt eval results, **access and secrets review** (rotate keys), source terms-of-use review, backup restore evidence | `governance/reviews/2027-Q1.md` (template-generated, you sign off) |
| **Annually** | Tax rates, SEBI/AMFI definitions, framework review, retention clean-up | Framework version bump if needed |

**Streamlit "Audit & Governance" page** (Phase 4 minimal, Phase 6 full):

- Run timeline, with a drill-down into the step ledger.
- Audit log search by any ID (run, ISIN, event type, actor).
- "Explain verdict" lineage viewer.
- Overrides list, config change history (linked PRs).
- Alert log including suppressed alerts ("why didn't I get alerted?").
- Model inventory.

---

## 13. Data model additions (Supabase; complements plan 05 §3.4)

| Table | Key columns | Notes |
|---|---|---|
| `audit_events` | event_id, event_type, ts_utc, trading_date_ist, run_id, step_id, actor_type, actor_id, entity_type, entity_id, isin, action, before, after, reason, evidence_ref, code_version, config_hash, framework_version, prev_hash, record_hash | **Append-only** (trigger + RLS); hash-chained |
| `run_steps` | step_id, run_id, name, seq, started_at, ended_at, status, input_hashes, output_hashes, rows_in, rows_out, error | Step ledger |
| `runs` (extended) | + trigger_type, triggered_by, code_version, prompt_versions, dq_score, llm_tokens, llm_cost_inr, audit_chain_head, status (incl. `SUCCESS_AUDIT_PENDING`, `INVALIDATED`) | |
| `llm_calls` | call_id, run_id, trace_id, agent_id, prompt_id, prompt_version, model_id, params, input_doc_hashes, output_hash, validation_status, citations_verified, tokens_in, tokens_out, cost_inr, latency_ms | |
| `alerts_log` | alert_id, run_id, isin, signal_or_event_id, severity, channel, decision (`sent` / `suppressed`), suppression_reason, payload_hash, delivery_status, provider_msg_id | |
| `verdict_explanations` | run_id, isin, verdict, policy_rule_id, lens_refs, metric_refs, citations | Lineage tree |
| `overrides` | override_id, isin, field, value, reason, set_by, set_at, expires_at, status | |
| `model_inventory` | model_id, kind (lens/agent/policy), version, status, validated_on, calibration_ref, limitations | |
| `config_versions` | config_hash, git_sha, pr_ref, changed_files, merged_at, rescore_ref | |
| `sources` | source_id, tier, data_types, access_method, tos_note, cadence, last_success_at, failure_rate_30d | |
| `mcp_tool_calls` *(v1.0)* | mcp_call_id, run_id, agent_run_id, client (`agent:<id>` / `claude:desktop` / `claude:code`), tool_id, tier, args_hash, result_hash, masked, status, latency_ms | Append-only |
| `proposals` *(v1.0)* | proposal_id, kind (watchlist / thesis_flag / journal), isin, payload, reason, evidence_refs, agent_run_id, status, decided_by, decided_at, expires_at | The only table agents write to besides the two queues below |
| `notify_queue` / `job_requests` *(v1.0)* | item_id, agent_run_id, template_id or job kind, isin, severity, dedupe_key, status | Drained by the notifier (routing per ADR-008) and the job runner (daily cap) |

---

## 14. Code structure and standards

```
src/audit/
├── context.py      ← RunContext (run_id, asof, code_version, config_hash, actor) — passed everywhere
├── events.py       ← event type IDs (AUD.*) as enums + Pydantic AuditEvent model
├── emit.py         ← audit.emit(...) → outbox → Postgres; hash chaining
├── steps.py        ← audited_step() context manager + @audited decorator
├── lineage.py      ← metric/verdict lineage capture + explain() tree
├── integrity.py    ← chain verification, git anchoring, completeness tests
└── redact.py       ← structlog processor for masking
```

**Rules** (added to CLAUDE.md / AGENTS.md):

1. Every service method that **changes state** calls `audit.emit` (enforced by a unit-test sweep over the service layer).
2. Every pipeline step is wrapped in `audited_step`.
3. The UI never writes directly; it goes through services, which audit (ADR-006).
4. No `print()`; only structlog.
5. New event types need an ID in `events.py` and appear in the generated `docs/AUDIT_EVENTS.md`.
6. *(v1.0)* Every MCP tool is wrapped by the server's audit middleware (`AUD.MCP.TOOL_CALL`); no tool can be registered without a tier and an ID (plan 15 §4.4).

---

## 15. Architecture decision: ADR-007

- **Decision:** a single append-only, hash-chained `audit_events` store (Postgres, with a JSONL outbox and daily git anchoring), separate from operational logs. A step ledger + run manifests for reproducibility, lineage captured at metric level, and LLM governance through a prompt registry with an eval gate.
- **Alternatives considered:**
  - Logs only: not queryable, not tamper-evident, and lost after 90 days.
  - Full event sourcing of all state: too heavy for this scale.
  - External audit SaaS: cost, and holdings privacy.
- **Consequences:**
  - ➕ Every verdict, alert and change can be explained and replayed; cheap tamper evidence.
  - ➖ A small write overhead; audit wiring is needed in every service (mitigated by the context manager and tests).

---

## 16. Rollout by phase

Phase placement of the governance deliverables lives in **plan 09** (the governance line in each phase), and their tests in **plan 14** (L4, L6).
