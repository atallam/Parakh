---
title: Agentic & MCP Architecture — Parakh
version: 1.2 (D27: agents run on an orchestrator: AGENT.orchestrator plans, a code dispatcher executes, new §5b, AG-09/AG-10, AGENT.portfolio_analyst, case files, ADR-014; Curator parked by D26; v1.1: scaffold note: parakh profile done; v1.0: first version: MCP-first agent layer, Claude Agent SDK runtime, local stdio transport — plan 13 D20–D22)
date: 2026-09-27
owner: Avinash Tallam
parent: 00_MASTER_PLAN.md
owns: the agent-facing design — principles AG-01…AG-10, the orchestrator and dispatcher (§5b), the `parakh-mcp` server (toolsets, resources, prompts, permission tiers), the agent roster, the agent runtime contract (`AgentRunner`), transport and hosting, and the full text of ADR-010…012 and ADR-014. Other docs link here instead of restating it (README fact owners)
related: 03 (jobs and notification routing) · 04 (ADR index, repo layout, ID conventions) · 05 §4 (holdings privacy) · 06 (watchlist approvals) · 07 (FR-26/27, NFR-15) · 08 (F24, F25) · 09 (phase placement) · 10 §7 (LLM and agent governance, `AUD.MCP.*` / `AUD.AGENT.*`) · 12 §1, §9 (Claude as a surface) · 14 (tests L2, L5, L7)
conventions: tools `TOOL.<toolset>.<name>` · agents `AGENT.<name>` · principles `AG-nn` · resources `parakh://…`
---

# Agentic and MCP Architecture

## 0. In plain terms

Parakh does its maths in ordinary, testable Python, the same as before. What changes is **how anything intelligent reaches it.**

- Everything Parakh knows and can do is exposed through **one MCP server, `parakh-mcp`**, as a set of well-described tools: "get this stock's snapshot", "what changed this month", "explain this verdict", "propose adding this stock to the watchlist".
- **AI agents** (built on the Claude Agent SDK) use only those tools. They read, reason, write narrative and **propose**. They never compute a score, never change your holdings, theses or watchlists directly, and never pick who gets alerted.
- **You** can use the same tools from Claude Desktop or Claude Code on your PC: "why did HDFCBANK drop to HOLD?", "what needs my attention this month?". Nothing new to learn; it's a conversation.
- For now the server runs **only on your PC and inside the scheduled GitHub jobs**. It isn't reachable from the internet (D22). Remote access stays a conditional later candidate, decided at the M1 review.
- **The agents work under an orchestrator** (D27). `AGENT.orchestrator` looks at what changed across your holdings, decides which specialist agents are worth running on which stock, and hands the plan to a small piece of ordinary code (the dispatcher) that checks it against the rules and runs it. The specialists read, reason and propose; the orchestrator plans and summarises. Scores and verdicts are still computed by plain code first (§5b).

---

## 1. What changes, and what doesn't

| Stays exactly as it is | Changes |
|---|---|
| **The LLM never produces a number that feeds a score** (NFR-02, the numbers firewall in 10 §7) | MCP is the **only** way an agent touches data or state (AG-01) |
| Lenses, metric and signal registries, verdict policy: deterministic Python (04 §1) | Agents run on the **Claude Agent SDK** behind an `AgentRunner` interface (ADR-011), not LangGraph |
| The monthly scoring run and the daily watchers are **workflows** (fixed steps in code), fully replayable (10 §5) | Agents do the judgement work around the workflows: review, qualitative reading, counter-arguments, event triage, watchlist curation (§5) |
| Human approval for My Watchlist, holdings and theses (06, 05, D13) | Agents can **propose** those changes; proposals land in the same review inbox and Telegram buttons you already have |
| Services are the contract (ADR-006); Streamlit, Telegram and CLI call services | MCP becomes a **fourth surface over the same services**, with the same view models |
| Audit of every step and change (ADR-007) | Every tool call and agent run is audited too (`AUD.MCP.*`, `AUD.AGENT.*`, 10 §4) |
| Notification routing, de-duplication, cool-downs, masking (03, ADR-008) | Enforced **inside** the `notify.*` tools, so an agent can't get around them (AG-05) |
| — | The Claude push lane for the monthly narrative review is replaced by the Monthly Reviewer agent's output on Telegram + email (ADR-008 amended, §5) |
| Agents are triggered by fixed rules, one job per agent | An **orchestrator** plans the judgement work per run and a **dispatcher** executes the plan under the same allow-lists, budgets and audit; a linear fallback mode keeps the rules-based path (§5b, ADR-014) |
| Agents cover the universe (Tier A, B, C) | Agents cover the **coverage set** (your holdings) only; the Watchlist Curator is parked (plan 17, D26) |

---

## 2. Principles

| ID | Principle | What it means in practice |
|---|---|---|
| **AG-01** | **Tools are the only door** | Agents get no filesystem, shell, web or database access. Their allowed tools are `mcp__parakh__*` only, set per agent (§6.2) |
| **AG-02** | **Workflows where the path is known, agents where judgement is needed** | Scoring, watchers, rendering and publishing are code. An agent is used only where reading, weighing or writing prose is the job. *Which* judgement work is worth doing on a given run is itself a judgement, and belongs to the orchestrator (AG-09) |
| **AG-03** | **Agents propose; you decide** | Tools that would change your state are `propose_*` tools. They write a proposal row and nothing else. Approval happens in Streamlit, Telegram or the CLI, never through MCP |
| **AG-04** | **Deterministic under the hood** | Every tool is a thin wrapper over a service. The same call through MCP, the CLI or Streamlit returns the same numbers (tested at L2, plan 14) |
| **AG-05** | **Policy lives in the server** | Routing, de-duplication, cool-downs, masking, rate limits and budgets are enforced by the tool, never trusted to the agent's instructions |
| **AG-06** | **Untrusted content stays data** | Transcripts, filings and news come back in an `untrusted_content` field with provenance. Tools that act (notify, jobs) accept only IDs and enums, never free text, so injected text can't reach a message or trigger an action |
| **AG-07** | **Private by default** | Holdings come back masked (weights and %, no quantities or ₹) unless the caller is the owner's local client and asks for detail. CAS data is never reachable through any tool (P6) |
| **AG-08** | **Bounded and observable** | Every agent has a turn limit, a token budget, a pinned model and prompt version, and a trace. Running out means "pending", not "guess" |
| **AG-09** | **Agents are planned, then dispatched** | The orchestrator never calls a specialist directly. It returns a `RunPlan` (a Pydantic object) and the dispatcher validates it against the registry, the coverage set, the facts in `what_changed` and the budgets, then runs it. A plan is data: it is audited, replayable and testable with `FakeRunner` |
| **AG-10** | **Untrusted text stays at the leaves** | Documents (transcripts, filings, news) enter only the specialists that must read them. The orchestrator sees structured, schema-validated specialist outputs and snapshot facts, never raw document text, so injected text cannot steer the plan |

---

## 3. Architecture

```
  CLIENTS                                                     SURFACES THAT DON'T USE MCP
  ─────────────────────────────────────────────                (they call services directly)
  Agents (Claude Agent SDK, via AgentRunner)                   ─ Streamlit app (ADR-006)
   AGENT.monthly_reviewer   AGENT.qualitative                  ─ Telegram bot + listener
   AGENT.devils_advocate    AGENT.event_triage                 ─ CLI (parakh …)
   AGENT.portfolio_analyst   AGENT.watchlist_curator (parked, D26)
   AGENT.orchestrator ──► RunPlan ──► dispatcher (code) ──► the specialists above (§5b)
  You, interactively: Claude Desktop · Claude Code (stdio)
                 │  MCP (stdio, local only — ADR-012)
                 ▼
  ┌────────────────────────── parakh-mcp (src/mcp/) ──────────────────────────┐
  │ reports.*  analytics.*  data.*  portfolio.*  notify.*  jobs.*  audit.*   │
  │ resources parakh://…   prompts /monthly-review /explain /deep-dive       │
  │ ── per-call: permission tier check · masking · budget · AUD.MCP.* ──     │
  └──────────────────────────────────┬────────────────────────────────────────┘
                                     ▼
          services/ (the contract, ADR-006) ── view_models.py
                                     ▼
   lenses · registries · verdict policy · storage (Supabase/DuckDB) · notifier
                                     ▲
   WORKFLOWS (code): monthly run · daily momentum watcher · daily event watcher
```

**Where each job's agents run:**

| Job (plan 03) | Workflow part (code) | Agent part |
|---|---|---|
| Monthly Analyst | Fetch → validate → metrics → lenses → policy → render → publish | After publish, the Orchestrator reads `what_changed` and writes a `RunPlan`; the dispatcher runs the specialists it chose (Qualitative per holding with a new transcript or a thesis flag, Devil's Advocate on a verdict change, Portfolio Analyst on the whole book); the Monthly Reviewer then writes the narrative review from the case files |
| Daily Momentum Watcher | Unchanged, no agent | — |
| Daily Event Watcher | Parse filings → match rules (E-codes) → de-duplicate | Event Triage reads new filings the rules flagged, summarises them, and may request a single-stock refresh or queue a 🔴/🟡 alert through `notify.*`. On a day with more than one flagged filing or any High-severity event, the orchestrator plans the triage; otherwise the job runs it directly |
| Ad hoc | — | You, from Claude Desktop or Claude Code |

---

## 4. The `parakh-mcp` server

### 4.1 Implementation

- Python, the official MCP Python SDK (FastMCP style), in `src/mcp/` (layout in 04 §3.3).
- One server process with **namespaced toolsets**. Splitting into several servers is possible later without changing tool names.
- Each tool is a 5–20 line wrapper: validate input (Pydantic) → call one service → return a view model. **No business logic in `src/mcp/`**, enforced by the same layering lint as `app/` (plan 14 L0).
- Tool inputs and outputs are Pydantic models from `src/services/view_models.py`, so MCP, Streamlit and Telegram can't disagree (UX-02).
- Outputs are sized for a model's context: lists are paginated, long text is summarised with a pointer to the full resource, and every response carries `asof`, `run_id` and `framework_version`.
- Database access uses a dedicated role, `parakh_mcp`: `SELECT` on the read models, `INSERT` only on `proposals`, `notify_queue`, `job_requests` and the audit outbox. It can't update or delete anything.

### 4.2 Toolsets

Permission tiers: **R** read-only · **P** propose (writes a proposal only) · **N** notify (queues through routing policy) · **J** job request (bounded, rate-limited).

| Tool | Tier | What it returns or does |
|---|---|---|
| `reports.what_changed(period?, cap?)` | R | Verdict changes, new signals, red flags, thesis status changes, pending proposals — owned stocks first |
| `reports.get_stock(symbol_or_isin, period?)` | R | The Stock Detail view model: TL;DR, verdict (prev → now), evidence bullets, action box, scores, events |
| `reports.segment_summary(cap, period?)` | R | Ranked table (paginated), regime, holdings section (masked) |
| `reports.get_history(isin, metrics?, months?)` | R | Time series from `history.csv` / `metric_values` |
| `analytics.explain_verdict(isin, period?)` | R | The lineage tree from `explain` (10 §6) |
| `analytics.evaluate_lens(isin, lens_id, overrides?)` | R | A **what-if** re-score with hypothetical inputs, clearly labelled `what_if: true` and never stored as a verdict |
| `analytics.list_catalogue(kind)` | R | Metric, signal, rule or lens catalogue (the generated METRICS/SIGNALS/RULES docs) |
| `data.get_prices(isin, from, to)` | R | Adjusted OHLCV with source and as-of stamps |
| `data.get_fundamentals(isin, metrics?, as_of?)` | R | Point-in-time values (`reported_on ≤ as_of`) |
| `data.get_document(isin, type, period)` | R | Transcript, annual-report or filing text in `untrusted_content`, with source URL and SHA-256 (AG-06) |
| `data.quality(run_id?)` | R | DQ scorecard and cross-source conflicts |
| `portfolio.positions(detail?)` | R | Owned stocks with weight, P&L %, LTCG days. `detail: true` (quantities, ₹) only for the owner's local interactive client (AG-07) |
| `portfolio.get_thesis(isin)` | R | Structured thesis (05 §2.4) and current status |
| `portfolio.pending_approvals()` | R | Open proposals and suggestions |
| `portfolio.propose_watchlist(action, isin, reason, evidence_refs)` | P | Add, remove or promote proposal → the Watchlist Review page and Telegram cards (06 §5) |
| `portfolio.propose_thesis_flag(isin, metric_or_condition, status, evidence_refs)` | P | `FLAG.thesis_review` proposal; BROKEN still needs a metric breaker or you (D13) |
| `portfolio.propose_journal_entry(isin, text)` | P | Draft decision-journal entry for you to confirm |
| `notify.queue(kind, isin?, event_id?, severity, template_id, vars)` | N | Queues a message. `template_id` and `vars` are enums and IDs; text is rendered from the plan 12 §6 templates, with ADR-008 routing, de-duplication, cool-downs and masking applied |
| `jobs.request_refresh(isin, reason_code)` | J | Asks for a single-stock deterministic re-run (value + qualitative). At most 5 per day, and never during a monthly run |
| `audit.get_run(run_id)` · `audit.search(filters)` | R | Run manifest, step ledger, audit events (masked) |
| `reports.get_case_file(isin, period?)` | R | The case file for one holding: verdict, evidence, specialist outputs with their status (ok or pending), portfolio context, open proposals (§5b) |
| `insights.get_v1(period?)` | R | The masked `insights.v1` records Parakh publishes (plan 18 §3.2); always masked, for every client |
| `audit.get_run_plan(run_id)` | R | The orchestrator's `RunPlan`, the dispatcher's accept or reject notes, and each task's outcome |

**Not exposed through MCP, on purpose:** approving or rejecting anything, editing holdings or theses, CAS import, config or weight changes, prompt promotion, publishing, deleting. Those stay with you in Streamlit, Telegram or the CLI (AG-03).

### 4.3 Resources and prompts

| Kind | Name | Use |
|---|---|---|
| Resource | `parakh://stock/{isin}/snapshot/{period}` | The canonical JSON snapshot (masked) |
| Resource | `parakh://stock/{isin}/report/{period}` | The Markdown report |
| Resource | `parakh://segment/{cap}/summary/{period}` | Segment summary |
| Resource | `parakh://plan/{doc}` | These plan docs, so Claude Code can load the owner doc for a task |
| Prompt | `/monthly-review` | "What needs my attention this month?" — calls `what_changed`, then drills into owned stocks |
| Prompt | `/explain {symbol}` | Lineage walk-through of the latest verdict in plain words |
| Prompt | `/deep-dive {symbol}` | Report + history + thesis + devil's advocate, as a conversation |
| Prompt | `/thesis-check {symbol}` | Walks each thesis condition against the latest data |

### 4.4 Tool contract rules

1. Every tool has a stable ID (`TOOL.reports.what_changed`), a docstring written for a model (what it's for, when not to use it, units, IDs it returns), and MCP annotations (`readOnlyHint`, `destructiveHint: false`, `idempotentHint`, `openWorldHint: false`).
2. Tool schemas are versioned per toolset (SemVer). A breaking change bumps the major version and appears in `CHANGELOG.md`.
3. `docs/TOOLS.md` is generated from the registry in CI, like METRICS/SIGNALS/RULES (04 §3.2).
4. New lenses need no new tool: `analytics.evaluate_lens` and `reports.get_stock` pick them up from the lens registry, so the 5-file recipe (04 §1.3) stays at 5 files.

---

## 5. Agent roster

| Agent | Feature | Trigger | Tools (allow-list) | Can write | Output |
|---|---|---|---|---|---|
| **`AGENT.qualitative`** (Qualitative Analyst) | F06 | Scheduled by the orchestrator for a holding with a new transcript or a thesis flag; event refresh on a new transcript | `data.get_document`, `data.get_fundamentals`, `portfolio.get_thesis`, `reports.get_history`, `portfolio.propose_thesis_flag` | P | Pydantic-validated scorecard, guidance records, exact-quote citations, thesis assessments. **Confidence ±1 level only** (AC-F06.1) |
| **`AGENT.devils_advocate`** | F07 | Scheduled by the orchestrator on a verdict change or a new ADD / EXIT on a holding | `reports.get_stock`, `analytics.explain_verdict`, `data.get_document`, `reports.get_history` | — | 3 counter-points with citations or metric refs; can't change the verdict |
| **`AGENT.monthly_reviewer`** | F25 | Last step of an orchestrated run; receives the case files | `reports.*`, `analytics.explain_verdict`, `portfolio.positions`, `portfolio.get_thesis`, `portfolio.pending_approvals`, `data.quality`, `notify.queue` | N | "Top 5 things to look at": a short Telegram message and a full section in the monthly email (replaces the Claude scheduled-task review of 03 §3C) |
| **`AGENT.event_triage`** | F25 | Daily Event Watcher, for filings its rules flagged; planned by the orchestrator on busy days | `data.get_document`, `reports.get_stock`, `portfolio.get_thesis`, `notify.queue`, `jobs.request_refresh` | N, J | A one-line summary per material filing and, where warranted, a refresh request or a queued 🔴/🟡 alert (severity capped by the E-code rule table in 03 §5b) |
| **`AGENT.watchlist_curator`** | F25 | **Parked by D26** (`agents.watchlist_curator.enabled: false`); returns only if discovery is re-enabled | `reports.segment_summary`, `reports.get_stock`, `portfolio.pending_approvals`, `portfolio.propose_watchlist` | P | Watchlist proposals with reasons and evidence, on top of the rule-based suggestions in 06 §3. Capacity limits and minimum stays still apply |
| **`AGENT.orchestrator`** (Orchestrator) | F28 | After the monthly publish step; the daily event batch on busy days; a thesis status change; `parakh agents run` | `reports.what_changed`, `reports.get_stock`, `analytics.explain_verdict`, `portfolio.positions` (masked), `portfolio.pending_approvals`, `data.quality`, `audit.get_run`. **No document, notify or job tools** | — | A validated `RunPlan` (what to run, on which holding, why, with what budget, and which holdings it skipped and why), then a `Synthesis` of the specialists' outputs: the top items, conflicts between specialists, and which proposals to raise |
| **`AGENT.portfolio_analyst`** (Portfolio Analyst) | F29 | Scheduled by the orchestrator once per monthly run, and when a weight limit is breached | `portfolio.positions` (masked), `reports.get_stock`, `reports.get_history`, `analytics.explain_verdict`, `portfolio.propose_journal_entry` | P | Allocation context for the whole book: sector weights against your targets and limits, concentration (HHI, top 5), correlation clusters, tax-timing proximity. It writes context and proposals only; sizing refinements that change a verdict are a deterministic policy row, not this agent (plan 18 §12 item 1) |
| **You** (Claude Desktop / Claude Code) | F24 | Whenever you ask | All R tools; P tools with the host's confirmation prompt | P | Conversation |

Every agent has an **agent card** (`docs/agents/<agent>.md`, 10 §7) and an entry in the model inventory.

---

## 5b. The orchestrator and the dispatcher (ADR-014, D27)

### The pattern: orchestrator-workers with a code dispatcher

```
 snapshot + what_changed (deterministic, already published)
              │
              ▼
   AGENT.orchestrator  ── reads facts only (no documents, no notify, no jobs)
              │  returns RunPlan  (Pydantic)
              ▼
   DISPATCHER (plain code)  ── validates → runs tasks in dependency order, in parallel where independent
        │        │        │        │
        ▼        ▼        ▼        ▼
   qualitative  devils_    event_    portfolio_      each: own allow-list, budget, prompt pin,
   (per holding) advocate  triage    analyst         output schema, audit; documents stay here
        │        │        │        │
        └────────┴────┬───┴────────┘
                      ▼
   CASE FILE assembler (plain code)  ── merges snapshot + specialist outputs per holding
                      ▼
   AGENT.orchestrator (second turn)  ── Synthesis: top items, conflicts, proposals to raise
                      ▼
   AGENT.monthly_reviewer  ── writes the Telegram and email text from the case files
                      ▼
   publish: reports, case files, insights.v1 (plan 18), notify.queue (routing applies)
```

### What each part owns

| Part | Is | Decides | Cannot |
|---|---|---|---|
| Spine (plan 03, 04) | Code | Every score, verdict, signal and alert rule | Be changed by any agent |
| Orchestrator | Agent | Which holdings need which specialist this run, in what order, with what share of the budget; which holdings can be skipped as quiet; which conflicts to flag | Call a specialist directly, read a document, send a message, request a refresh, approve anything, or change a number |
| Dispatcher | Code | Whether a plan is acceptable, and how it is executed | Invent work the plan did not contain |
| Specialists | Agents | How to do their one job well | Use tools outside their allow-list, or see another specialist's raw inputs |

### The `RunPlan` and what the dispatcher checks

```python
class PlanTask(BaseModel):
    task_id: str
    agent_id: Literal["AGENT.qualitative", "AGENT.devils_advocate", "AGENT.event_triage",
                      "AGENT.portfolio_analyst", "AGENT.monthly_reviewer"]
    isin: str | None                       # None only for whole-book tasks
    reason_code: Literal["VERDICT_CHANGED", "NEW_TRANSCRIPT", "THESIS_FLAG", "HIGH_SEVERITY_EVENT",
                         "WEIGHT_BREACH", "LTCG_NEAR", "REVIEW_DUE", "SCHEDULED"]
    depends_on: list[str] = []
    budget_tokens: int

class RunPlan(BaseModel):
    run_id: str
    trigger: Literal["MONTHLY", "EVENTS", "THESIS_CHANGE", "MANUAL"]
    tasks: list[PlanTask]
    skipped: list[SkippedHolding]          # isin + reason: every coverage-set holding is in a task or here
    rationale: str                         # at most 600 characters
```

The dispatcher rejects a task (and records `AUD.AGENT.PLAN_REJECTED`) unless all of these hold:
1. `agent_id` is registered and enabled in `config/agents.yaml`; the task cannot add, widen or change tools.
2. The ISIN is in the coverage set (D26).
3. The `reason_code` is backed by a fact the dispatcher can look up (for example `NEW_TRANSCRIPT` needs a document hash not yet analysed; `VERDICT_CHANGED` needs a change in `what_changed`). The orchestrator cannot invent work.
4. The task graph is acyclic, within the task cap, and the budgets fit the run budget.
5. Every coverage-set holding appears in `tasks` or `skipped`, so a missed holding is visible rather than silent.

### Case files

A **case file** is the merged, per-holding record of one run: the snapshot (verdict, scores, evidence), each specialist's validated output with its status (`ok` or `pending`), the portfolio context, and open proposals. It is assembled by code, stored (`case_files`), shown in Stock Detail, and is the source of `insights.v1` (plan 18). A specialist that fails leaves its slot `pending`; the case file never guesses.

### Triggers and modes

| Trigger | Orchestrated when | Otherwise |
|---|---|---|
| Monthly publish | `agents.orchestrator.enabled` | Linear mode: the rule-triggered per-agent steps that already exist |
| Daily event batch | More than one flagged filing, or any High severity | `AGENT.event_triage` runs directly on the flagged filing |
| Thesis status change | WATCH or BROKEN on a holding | The existing alert and Home inbox item |
| `parakh agents run` | Always | n/a |

`agents.orchestrator.dry_run: true` (the default until promoted) writes the plan, the case files and the synthesis to `logs/agents_shadow.md` only. `agents.orchestrator.fallback: linear` runs the old path if the orchestrator fails or the plan is rejected as a whole, and sends a ⚠️.

### Budgets and failure policy

- A run budget is set in config. The orchestrator's two turns get a fixed slice; the rest is split across tasks by the plan, capped per agent by `config/agents.yaml`. The dispatcher enforces the caps, not the model.
- A quiet month should produce a small plan: holdings with no trigger get no LLM task. Cost therefore follows what changed, not the number of holdings.
- A failed or over-budget specialist becomes `pending` for that holding, counts toward the P4 alert, and the run continues.
- Results are cached by ISIN, document hash and prompt pin (AC-F06.3), so re-running a plan costs nothing for unchanged inputs.

### Tests and promotion

Defined in plan 14 (L7 and L2): plan-quality evals on recorded `what_changed` fixtures (a quiet month yields a minimal plan; a verdict change schedules a devil's-advocate task; a new transcript schedules a qualitative task; a thesis flag takes priority), rejection tests (unregistered agent, ISIN outside the coverage set, unbacked reason code, cycle, budget overrun, missing holding), an injection test (hostile text in a specialist output cannot change the plan), and determinism of dispatch order. Promotion from shadow to live needs two shadow monthly runs in which you judged the plans right and the case files useful.

---

## 6. Agent runtime: the Claude Agent SDK (ADR-011)

### 6.1 The `AgentRunner` interface

Agents never import the SDK directly. They go through one small interface, so a different runtime (for example LangGraph) could be swapped in by writing one adapter:

```python
# src/agents/runtime/base.py
class AgentSpec(BaseModel):
    agent_id: str  # "AGENT.qualitative"
    version: str  # SemVer; stored in llm_calls and the model inventory
    prompt_id: str  # "QUAL.v7" — pinned in config/prompts.yaml (P3)
    model_id: str  # pinned in config/agents.yaml
    allowed_tools: list[str]  # "mcp__parakh__data_get_document", … (AG-01)
    max_turns: int  # the hard max_iterations (SCAIX standard)
    token_budget: int  # per invocation; the run budget still applies on top
    output_model: type[BaseModel]  # Pydantic schema the final answer must satisfy


class AgentRunner(Protocol):
    async def run(self, spec: AgentSpec, task: AgentTask, ctx: RunContext) -> AgentResult: ...


# src/agents/runtime/claude_sdk.py  → ClaudeSDKRunner (production)
# tests/fakes/agent_runner.py      → FakeRunner (recorded trajectories; CI never calls a model)
```

### 6.2 Required settings for every agent

| Setting | Value | Why |
|---|---|---|
| Allowed tools | Only that agent's `mcp__parakh__*` list | AG-01. The SDK includes Claude Code's built-in tools (shell, file edit, web fetch); none may be enabled. A contract test fails the build if one is |
| Permission mode | Default, never a bypass mode | Tool permissions must be checked |
| MCP servers | `parakh-mcp` over stdio only | ADR-012 |
| `max_turns` | Per agent, in `config/agents.yaml` | Hard loop limit |
| Model | Pinned model ID in config | Reproducibility; model changes pass the L7 eval gate (10 §7) |
| System prompt | Loaded from `src/prompts/` by pinned ID | Prompts versioned like code; rollback by pin (P3) |
| Final output | Validated against `output_model`; on failure, one repair turn, then "pending" | Pydantic validation rule |
| Hooks | Pre/Post tool-use hooks → structlog, `AUD.MCP.TOOL_CALL`, Langfuse span | Observability without LangChain integration |
| Retries | Tenacity around `run()` for transport and overload errors (429/529), then "pending" | SCAIX retry standard; P5 |
| Auth | `ANTHROPIC_API_KEY` from `.env` locally and AWS SSM in Actions (ADR-009) | Unattended runs bill to the API key, not your Claude subscription |
| Cost | Read from the SDK result; written to `llm_calls` and the run manifest | Cost per run (PRD §5) |

### 6.3 Known trade-offs of the SDK

- **Claude-only.** Recorded as a deviation from the SCAIX stack (LangGraph) in ADR-011; the `AgentRunner` interface keeps it reversible.
- **It carries the Claude Code runtime.** Heavier than a plain API call, and the built-in tools must be switched off (§6.2). The Phase 0.5 spike confirms it installs and runs on a GitHub-hosted runner.
- **A young API.** Pin the version in `uv.lock`; upgrades go through a PR with the L5 and L7 suites.
- **The scaffold.** `aiscaffold.py` / `stack_config.yaml` keep LangGraph as the SCAIX default; the `parakh` profile drops it and generates `mcp/toolsets` and `agents/runtime`, matching 04 §3.3 (plan 13 §4.4).

---

## 7. Transport and hosting (ADR-012)

| Client | How it connects | Where the server runs |
|---|---|---|
| Agents in scheduled jobs | The job spawns `parakh-mcp` as a stdio subprocess | Inside the GitHub Actions runner (or the Task Scheduler fallback). Never listening on a network port |
| You in Claude Desktop | `claude_desktop_config.json` entry launching `C:\dev\parakh\.venv\Scripts\python.exe -m parakh.mcp` | Your PC, with `.env` via `PARAKH_ENV_FILE` (D19) |
| You in Claude Code | `.mcp.json` in the repo | Your PC |
| claude.ai web or phone | **Not available** while D22 stands | — |

**Revisit (reminder set for Phase 5, before v1.0):** remote access over Streamable HTTP, if you want Ask Parakh on your phone or in claude.ai. It would need: a small host (e.g. the Render setup from WealthLens), OAuth in front of the server, a remote-safe toolset (R tools only, always masked, no P/N/J tiers at first), rate limits, and a new security review (10 §12). ADR-012 lists the triggers.

---

## 8. Trust boundaries and safety

| Risk | Control |
|---|---|
| Prompt injection in a transcript or filing | AG-06: content returned only as `untrusted_content`; action tools take IDs and enums; injection patterns flagged (`AUD.LLM.INJECTION_SUSPECTED`); adversarial fixtures in the L7 set (plan 14 §4.6) |
| An agent changing your state | AG-03: no approve, edit or delete tools exist; `propose_*` writes a proposal only; the `parakh_mcp` DB role can't update or delete |
| Alert spam from an agent | AG-05: `notify.queue` applies ADR-008 routing, de-duplication, cool-downs and a per-agent daily cap; severity can't exceed the rule table's value for that event |
| Runaway loops or cost | `max_turns`, per-agent and per-run token budgets, `jobs.request_refresh` daily cap; budget stop → "pending" + P4 alert |
| Holdings or PII leakage | AG-07: masked by default; `detail: true` refused for agents; CAS never reachable; redaction applies to tool outputs and logs (10 §10) |
| Agents drifting from their job | Allow-list per agent; `AUD.MCP.TOOL_DENIED` on any refused call; agent cards; L7 trajectory evals |
| MCP and CLI disagreeing | AG-04 equivalence test at L2 (plan 14) |
| The orchestrator over-spends or over-reaches | The dispatcher, not the model, enforces the task cap, budgets and the reason-code facts; it plans on facts and structured outputs only (AG-09, AG-10); a rejected plan falls back to linear mode with a ⚠️ |
| One specialist's bad output misleads another | Specialists share nothing directly; the case-file assembler merges validated schemas, and the orchestrator flags conflicts instead of resolving them |

---

## 9. Audit, tests and delivery

- **Audit events and tables:** `AUD.MCP.*` and `AUD.AGENT.*` events and the `mcp_tool_calls` and `proposals` tables are defined in **plan 10** (§4, §7, §13).
- **Tests:** tool contract and schema snapshots, the MCP-vs-CLI equivalence test, the "no built-in tools" test, agent trajectory evals with `FakeRunner`, and the MCP Inspector smoke check are defined in **plan 14** (L0, L2, L5, L7).
- The orchestrator's plan evals, rejection tests and injection test are in **plan 14** (L7, L2, §4.6).
- **Phase placement** of every item in this doc lives only in **plan 09**.
- **Features and acceptance criteria:** F24 (MCP server) and F25 (agent roster) in **plan 08**.

---

## 10. Architecture decisions

### ADR-010: MCP as the agent-facing interface over services

- **Status:** Accepted, 2026-09-27 (plan 13 D20)
- **Context:** you want Parakh to be agentic-forward. The existing plan had agents as nodes inside the pipeline with private "tools" (P2), and an MCP server only as an optional Phase 6 add-on (old plan 12 §9). ADR-006 had already made `services/` the single contract for every surface.
- **Decision:** one MCP server, `parakh-mcp`, exposes the services as namespaced toolsets (§4). It is the **only** way agents reach data or state, and the same server serves you interactively. Scoring and watchers remain code workflows (AG-02). State changes by agents are proposals only (AG-03).
- **Alternatives considered:**
  - Keep agents as pipeline nodes with private tools: works, but every new agent or client re-implements access and guardrails.
  - Let an agent orchestrate the monthly run end to end: loses replay determinism and makes verdicts harder to explain (10 §5). *(Amended by ADR-014: an orchestrator now plans the **judgement work** after the deterministic run has published; scoring stays code.)*
  - Several MCP servers from day one: cleaner separation, but more processes and config for a solo build; namespaced toolsets give most of the benefit and can be split later.
- **Consequences:**
  - ➕ One set of guardrails for every agent and for Claude; new agents are mostly a prompt, an allow-list and an output schema.
  - ➕ You get "Ask Parakh" in Claude Desktop from the first read-only tools, long before Phase 6.
  - ➖ An extra layer to test and version (tool schemas); mitigated by thin wrappers and generated `docs/TOOLS.md`.
  - ➖ An estimated 4–6 hours before M1 for the server skeleton, audit wrapper and first read-only tools (estimate).

### ADR-011: Agent runtime — Claude Agent SDK behind `AgentRunner`

- **Status:** Accepted, 2026-09-27 (plan 13 D21). **A recorded deviation** from the SCAIX stack default (LangGraph).
- **Context:** agents are now MCP clients. The runtime must support MCP natively, tool allow-lists, turn limits, hooks for audit, and structured outputs.
- **Decision:** use the Claude Agent SDK (Python) for all agents, only through the `AgentRunner` interface (§6.1), with the settings in §6.2.
- **Alternatives considered:**
  - LangGraph with MCP adapters: model-agnostic and matches the SCAIX stack; more glue code for MCP, and graph orchestration isn't needed because the workflows are plain code.
  - Plain Anthropic API tool loop: lightest, but hand-builds what the SDK provides (MCP client, hooks, permissions, cost reporting).
- **Consequences:**
  - ➕ Native MCP, allow-lists, hooks and cost reporting; least code.
  - ➖ Claude-only; built-in tools must be disabled; a young API to pin (§6.3).
  - **Revisit when:** you need a non-Claude model for an agent, the SDK can't run on the scheduled runner, or an SDK change breaks the L5/L7 suites twice in a quarter. The swap is one adapter (`ClaudeSDKRunner` → another `AgentRunner`).

### ADR-012: MCP transport — local stdio only (for now)

- **Status:** Accepted, 2026-09-27 (plan 13 D22). Revisit in Phase 5, before v1.0.
- **Decision:** `parakh-mcp` runs only as a stdio subprocess, on your PC (Claude Desktop, Claude Code) and inside scheduled job runners. It never listens on a network port.
- **Alternatives considered:** Streamable HTTP on a host behind OAuth, which enables phone and claude.ai access but exposes a holdings-aware service to the internet and adds hosting, auth and a security review.
- **Consequences:**
  - ➕ No attack surface, no hosting cost, no auth to build.
  - ➖ No Ask Parakh from your phone or claude.ai; the Claude scheduled-task push lane (which runs in the cloud) can't reach the server, so the monthly narrative review moves to the Monthly Reviewer agent in GitHub Actions (ADR-008 amended).
  - **Revisit triggers:** you want Ask Parakh away from your PC; a hosted UI goes behind a login anyway (ADR-006 revisit); or a second user appears.

### ADR-014: Agents run on an orchestrator, planned then dispatched

- **Status:** Accepted 2026-10-14 (plan 13 D27). Amends ADR-010 narrowly.
- **Context:** you asked for the agents to run on an orchestrator. The agents so far were independent steps triggered by fixed rules, which spends LLM effort whether or not a holding changed and leaves no one to notice when two specialists disagree. After D26 the coverage is a dozen holdings, where deciding *what is worth a closer look this month* is the valuable judgement.
- **Decision:** an orchestrator agent reads facts (the snapshot and `what_changed`), returns a validated `RunPlan`, and a code dispatcher runs the plan through the existing specialists. A case-file assembler merges their outputs and the orchestrator synthesises them. The deterministic spine, the numbers firewall and propose-only writes are unchanged. Documents never reach the orchestrator.
- **Alternatives considered:**
  - SDK-native subagents (the orchestrator calling specialists through the SDK's built-in delegation tool): simplest to write, but it would enable a built-in tool that AG-01 forbids, move budget and allow-list enforcement into model behaviour, and make plans harder to audit and replay. It stays possible later behind `AgentRunner`.
  - A LangGraph supervisor graph: model-agnostic, but more glue code and a second runtime, against ADR-011.
  - Keep independent rule-triggered agents: cheapest to build, but no triage across holdings, no conflict handling, and spend that does not follow what changed.
  - Let the orchestrator run the whole monthly pipeline: rejected again, for replay determinism (ADR-010).
- **Consequences:**
  - ➕ Spend follows what changed; conflicts are flagged; one place to see why each agent ran (the plan is audited).
  - ➕ New specialists are added by registering them; the orchestrator's choices stay bounded by the dispatcher.
  - ➖ An extra layer (plan schema, dispatcher, case files, evals); an estimated 12 to 16 hours (plan 09 R6). Mitigated by linear mode, which stays as the fallback and is what M2 relies on.
  - ➖ One more prompt to evaluate and pin; covered by the L7 plan evals.
  - **Revisit when:** the plan is accepted unchanged for three straight months with little skipped (then the rules could replace the model), or SDK-native subagents can enforce allow-lists and budgets outside the model.

*Personal analytical framework; not investment advice.*
