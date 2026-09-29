---
title: PRD — Parakh (Stock Analysis Framework)
version: 1.9 (non-goal: sell-side research products; FR-04/FR-05 cover sector profiles and limited history; FR-28 consensus context as backlog — plan 13 D23/D24; v1.8: agentic, MCP-first: G9, US-17/18, FR-26/27, NFR-15; FR-12/16 and §9–§10 updated; FR-20 no longer lists ask-Claude — plan 15, D20–D22; v1.7: decision pointer drops the D-range; v1.6: FR-25 thesis tracking → F23; v1.5: NFR-14 service levels moved here from plan 13 — 07 owns every numeric target; v1.4: §12 now points to plan 13; release criteria reference UAT-5 in plan 14; v1.3: baseline locked — decisions resolved in §12 and plan 13; tier Production; v1.2: UI/UX design system and notification channels — US-14/15/16, FR-23/24, NFR-13, §8 rewritten; v1.1: audit, logging & governance — G8, US-13, FR-21/22, NFR-11/12)
date: 2026-09-24
owner: Avinash Tallam (product owner, sole user)
status: Baseline v1.0 LOCKED (2026-09-24) — plan 13
tier: Production (confirmed 2026-09-24, plan 13 D2)
source_plans: 00–06 in FRAMEWORK/
companion_docs: 08_FEATURE_SPEC.md (features & acceptance criteria) · 09_PHASED_ROLLOUT_PLAN.md (delivery) · 10_AUDIT_LOGGING_GOVERNANCE.md (audit & governance design) · 12_UI_UX_DESIGN.md (UI/UX design) · 13_PLAN_BASELINE_V1.md (decisions) · 14_TEST_AND_UAT_PLAN.md (tests & UAT) · README.md (start here)
---

# Product Requirements Document: Parakh

## 1. Summary

A personal, automated **equity research system for Indian stocks (NSE)**. Every month it scores every stock in a chosen market-cap segment through independent **investing-style lenses** (Value and Momentum first), adds **LLM-assisted qualitative analysis** for the stocks that matter, keeps a **per-stock history** for trend analysis, and produces graded, explainable verdicts. Between monthly runs, **daily watchers** detect momentum-pattern changes and material corporate events, and notify the owner only when something changes. A **two-list watchlist** keeps the focus set fresh with human approval, and a lightweight **Streamlit app** handles reviews and holdings.

**Usage boundary:** personal analysis only. Not investment advice; not for commercial or public distribution (public buy/sell calls may fall under SEBI's Research Analyst regulations).

---

## 2. Problem statement

| Today | Pain |
|---|---|
| Stock research is manual and ad hoc, with no consistent method across stocks | Inconsistent decisions; hard to compare stocks or see what changed |
| No memory of past analysis | Trends (valuation re-rating, ROCE drift, momentum stage) are invisible; theses erode silently |
| Value and momentum views get mixed | Contradictory signals are averaged into mush or ignored |
| Price-pattern changes and corporate events (pledges, auditor exits, results) are noticed late | Missed entries, late exits, avoidable losses |
| The watchlist goes stale | Good ideas surfaced by screens never get deep analysis; dead ideas take attention |
| Owned positions aren't linked to analysis | Verdicts ignore position size, cost basis and capital-gains timing |

---

## 3. Goals and non-goals

### 3.1 Goals

| ID | Goal |
|---|---|
| G1 | A **repeatable, explainable** monthly analysis for every stock in a selected cap (Large / Mid / Small), with each style scored separately |
| G2 | **Longitudinal memory:** per-stock history supporting month-over-month, quarter-over-quarter and year-over-year trend analysis and a thesis check |
| G3 | **Hands-off operation:** scheduled runs, one notification per run, alerts only on state changes |
| G4 | **Ownership-aware** output: holdings, quantities, lots, P&L, tax timing reflected in verdicts and alerts |
| G5 | **Extensible:** add a new investing style as a plug-in (about 5 files) without touching the platform |
| G6 | **Maintainable and searchable** code, with ID-anchored traceability from plan to code to report |
| G7 | **Measurable:** calibration of scores, signals and watchlist sources against forward returns |
| G9 | **Agentic by design, safely:** every capability is available to AI agents and to Claude through one MCP server; agents review, read, triage and propose, but never compute scores or change the owner's state (plan 15) |
| G8 | **Auditable and governed end to end:** every step, decision, alert (sent *or suppressed*) and change is recorded with who/what/when/why, inputs, code and config; any verdict can be explained and replayed |

### 3.2 Non-goals (v1)

- ❌ Automatic order placement or broker trading integration.
- ❌ Intraday or tick-level signals (end-of-day resolution only; see plan 03 §6).
- ❌ Multi-user or commercial product, public publishing of recommendations.
- ❌ Non-Indian markets (the architecture shouldn't block US equities later).
- ❌ Derivatives strategy analysis (F&O data used only as a momentum confirmation input).
- ❌ Portfolio optimisation beyond concentration checks and position-size suggestions.
- ❌ Sell-side research products: own earnings forecasts, 12-month price targets, formal ratings (plan 13 D23). Parakh is a systematic engine held to institutional rigour, not a broker note.

---

## 4. User and context

| | |
|---|---|
| **Primary user** | Avinash: experienced professional investing in Indian equities and mutual funds; comfortable with Python; prefers a UX-first, multi-source, agentic design |
| **Usage pattern** | Monthly review (~30–60 min); glances at phone alerts on trading days; occasional deep dive into a stock |
| **Environments** | Windows PC (code in `C:\dev\parakh`, reports in OneDrive), GitHub (private repo), Telegram on phone, Supabase (dedicated `parakh` project), AWS SSM (secrets), Claude |

### Key user stories

| ID | As the owner, I want… | So that… |
|---|---|---|
| US-01 | to run analysis for one cap segment or all caps | I can focus on the segment I care about |
| US-02 | every stock in the cap scored, with deep dives only where they matter | I see the whole field without drowning in reports |
| US-03 | separate Value and Momentum verdicts plus one combined, explainable verdict | I understand *why* and where the styles disagree |
| US-04 | a per-stock history I can compare over time | I can spot re-ratings, quality drift and stage changes |
| US-05 | to mark what I own, with quantities and buy lots | verdicts become ADD / HOLD / TRIM / EXIT with tax context |
| US-06 | one notification when the monthly run finishes | I know when to review, without checking |
| US-07 | to be alerted when a momentum pattern changes or a material event happens | I act in time, without noise |
| US-08 | the watchlist to refresh itself, with my approval for my own list | good ideas get in and stale ones get out, under my control |
| US-09 | to approve suggestions and edit holdings in a simple UI | I don't have to edit YAML |
| US-10 | concall insights taken from filed transcripts and checked against my thesis | qualitative views are grounded, cited and relevant to why I own the stock |
| US-11 | to add a new investing style later without rebuilding | the system grows with my thinking |
| US-12 | to see whether the scores and signals actually worked | I trust, tune or drop them based on evidence |
| US-13 | to trace any verdict back to its source numbers, and see every change made by me, the system or an agent | I can trust, debug and defend every decision ("why BUY in March?", "why no alert?") |
| US-14 | to open the app and see only what changed since my last review, owned stocks first | the monthly review fits in an hour |
| US-15 | to approve suggestions and mark alerts useful or noise from my phone in one tap | I act in the moment, and the system learns which alerts matter |
| US-16 | to share a stock view as a recommendation without exposing my holdings | I can share ideas safely, with the personal-use disclaimer |
| US-17 | to ask Claude about my stocks and reports in plain words ("why did HDFCBANK move to HOLD?", "what needs my attention?") | I get answers grounded in Parakh's own numbers, without opening files |
| US-18 | AI agents to do the reading and first-pass judgement (monthly review, filings, counter-arguments, watchlist ideas) and bring me proposals | my review time goes to decisions, and nothing changes without my approval |

---

## 5. Success metrics

| Metric | Target | Measured by |
|---|---|---|
| Unattended monthly runs | ≥ 11 of 12 months complete without manual intervention | `runs` table |
| Run duration (full mid-cap universe, 150 stocks) | < 20 min | `runs` table |
| Alert precision (owner-judged "useful") | ≥ 70% after tuning | 👍/👎 buttons on alerts, captured from the first live alerts (plan 03 §4.3, plan 12 UX-13) |
| Duplicate or false-repeat alerts | 0 per month | De-duplication tests + logs |
| Data-quality blocks | < 5% of stocks per run carry a Low-confidence data warning | `data_quality` blocks |
| Owner review time per month | ≤ 60 min | Review-inbox timestamps: first open → all reviewed (plan 12 §5.1) |
| Calibration: top vs bottom score quintile | Positive 12-month forward spread (value), 3–6-month (momentum) | Quarterly calibration report |
| LLM cost per monthly run | Within the configured budget (hard stop) | Langfuse / token logs |

---

## 6. Scope: functional requirements

Detailed acceptance criteria are in **08_FEATURE_SPEC.md** (feature IDs in brackets).

| ID | Requirement | Priority | Feature |
|---|---|---|---|
| FR-01 | Classify stocks into Large / Mid / Small using AMFI lists; handle semi-annual migrations while keeping history | Must | F01 |
| FR-02 | Ingest prices, fundamentals, filings, concalls and macro data from multiple sources, with fallback, cross-validation, source trust tiers and as-of stamps | Must | F02 |
| FR-03 | Manage holdings at lot level (import from broker/CAS, CLI, UI); derive P&L, weight, holding period and capital-gains timing | Must | F03 |
| FR-04 | Value lens: relative valuation, quality, balance sheet, growth, governance, intrinsic-value range, MoS, vetoes, archetypes; *(v1.9)* sector profiles for every pilot archetype (bank, airline/lease-heavy, conglomerate SOTP, order-book, capital-market intermediary, new-age) and limited-history classes (plan 01 §3) | Must | F04 |
| FR-05 | Momentum lens: cap- and sector-benchmarked RS, volatility-adjusted momentum, trend structure, stages, signal catalogue, regime filter; *(v1.9)* minimum-history rules for young listings (plan 02 §3.9) | Must | F05 |
| FR-06 | Combine lenses through a configurable verdict policy (matrix, vetoes, hysteresis, confidence) | Must | F08 |
| FR-07 | Per-stock monthly report (Markdown) + canonical JSON snapshot + history CSV + HISTORY.md | Must | F09 |
| FR-08 | Segment summary: holdings first, opportunities, full ranked universe, regime, changes | Must | F10 |
| FR-09 | Scheduled monthly run with a completion notification and failure alerts | Must | F11 |
| FR-10 | Daily end-of-day momentum watcher with state diffing, confirmation, de-duplication and severity routing | Must | F12 |
| FR-11 | Daily event watcher for filings (results/concalls, insider trades, pledges, auditor/KMP exits, ratings, surveillance lists) | Should | F13 |
| FR-12 | Qualitative agent (Claude Agent SDK, MCP tools only) on BSE-filed transcripts (via Screener's Concalls list), thesis-aware, with exact-quote citations; the LLM can only flag thesis breaks | Should | F06 |
| FR-13 | Two-list watchlist auto-curation with approvals | Should | F14 |
| FR-14 | Streamlit app: review inbox (home), watchlist review, holdings editor with thesis form, stock detail, dashboard | Should | F15 |
| FR-15 | Market-context layer (valuation bands, VIX, flows, breadth) feeding regime and MoS | Should | F16 |
| FR-16 | Devil's-advocate agent for every BUY/SELL | Could | F07 |
| FR-17 | Calibration: backtests, signal-outcome tracking, watchlist scorecard, decision journal | Should | F17 |
| FR-18 | Lens plug-in framework with scaffolding command and contract tests | Must | F18 |
| FR-19 | Observability: run log, structured logs, heartbeat, LLM tracing | Must | F19 |
| FR-21 | Audit trail: append-only, hash-chained audit events for every run step, decision, alert (incl. suppressed), human action and change; step ledger, run manifests, replay; verdict lineage (`explain`) | Must | F21 |
| FR-22 | Governance: model inventory and cards, PR-only config/prompt changes with impact preview, prompt eval gate, overrides with reason and expiry, source registry, DQ SLAs, retention, encrypted backups, quarterly reviews | Must (core) / Should (reviews, dashboards) | F21 |
| FR-23 | Cross-surface design system: one token file and component set for reports, Telegram and Streamlit; owned vs non-owned vocabulary; tri-state checks (unknown ≠ clean); privacy view and share export | Must (tokens, tri-state, masking) / Should (components, share export) | F22 |
| FR-24 | Two-way notifications: Telegram buttons (approve / reject / snooze, useful / noise, mute) and read-only commands, all audited; routing per ADR-008 | Should | F11 |
| FR-25 | Thesis tracking: a structured thesis per stock with status INTACT / WATCH / BROKEN from metric checks and concall evidence (the AI only flags), a timeline, and alerts | Must (core) / Should (concall-driven) | F23 |
| FR-26 | MCP server `parakh-mcp`: read, propose, notify and job-request toolsets over the services; resources and prompts; every call audited; masking by default; no approve, edit or delete tools (plan 15 §4) | Must (read toolsets) / Should (propose, notify, jobs) | F24 |
| FR-27 | Agent roster on the Claude Agent SDK behind `AgentRunner`: Monthly Reviewer, Event Triage and Watchlist Curator, plus F06/F07 migrated to MCP tools; allow-listed tools, turn and token limits, Pydantic outputs (plan 15 §5–6) | Should | F25 (F06, F07) |
| FR-28 *(v1.9)* | Consensus and results context: forward P/E on consensus estimates where coverage exists, results-day note vs consensus, reverse-DCF sensitivity grid, key-debate block (agent-drafted, owner-confirmed); no own forecasts | Could (backlog; decided at the M1 review) | F26 |
| FR-20 | Future: concall Q&A (RAG), animated pages (React), additional lenses, remote MCP access, own forecast models for up to 5 holdings (only if missed after 3 live months, D23) | Won't (v1) | F20 |

---

## 7. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Reproducibility | Every snapshot stores run_id, framework and lens versions, config hash and source as-of dates; any past verdict can be explained |
| NFR-02 | Determinism | All scores come from deterministic Python; **the LLM never produces a number used in a score**; LLM at temperature 0 with cached outputs |
| NFR-03 | Data integrity | ISIN-keyed; corporate-action adjusted; point-in-time fundamentals (`reported_on`); survivorship-safe |
| NFR-04 | Reliability | Idempotent runs; retries with backoff; failure alerts; weekly heartbeat; holiday-aware |
| NFR-05 | Security and privacy | Private repo; secrets in AWS SSM via GitHub OIDC (ADR-009) / `.env` locally; PAN, names, addresses and DP/client IDs from CAS never stored, logged or sent to an LLM; holdings encrypted (sops/age) and RLS in Supabase; UI never public; notifications and share exports mask quantities and ₹ amounts by default; the bot answers only the owner's chat |
| NFR-06 | Maintainability | Plan 04 §3 standards: ID-anchored traceability, docstrings with formula/pitfalls, unit-suffixed names, ruff + pyright + pre-commit, generated catalogues, ADRs, CLAUDE.md/AGENTS.md |
| NFR-07 | Performance | Full mid-cap run < 20 min; daily watcher < 5 min; UI pages < 2 s with caching |
| NFR-08 | Cost | Free tiers by default; LLM token budget per run with a hard stop; LLM only for Tier A |
| NFR-09 | Compliance | Respect data-source terms of use; prefer exports and APIs over scraping; personal-use disclaimer on every report |
| NFR-10 | Portability | Storage behind a repository interface (DuckDB ↔ Supabase); UI behind a service layer (ADR-006) |
| NFR-11 | Auditability | 100% of runs have START/END events; 100% of state changes and verdict changes have an audit event; the audit store is append-only and tamper-evident (hash chain + daily git anchor); audit writes are never lost (outbox) |
| NFR-12 | Retention | Logs 90 days · step ledger 3 years · audit trail indefinite · raw inputs 24 months · LLM traces 12 months (summaries indefinite) — plan 10 §11 |
| NFR-13 | Usability | Pages render from precomputed view models with no network or LLM calls; every page region shows data, "N/A" or an explicit error with a next step; every status uses colour + icon + word (plan 12) |
| NFR-15 | Agent safety and efficiency | 100% of MCP tool calls audited (`AUD.MCP.TOOL_CALL`); 0 agent writes outside `proposals`, `notify_queue` and `job_requests`; 0 built-in SDK tools enabled; read tools respond in < 2 s at p95 on the pilot; each agent within its `max_turns` and token budget, with a budget stop ending as "pending", never a guess (plan 15 §6, §8) |
| NFR-14 | Service levels | Monthly Telegram summary by 12:00 IST on run day · daily watcher message (when there's a change) by 19:30 IST on trading days · failure alert within 5 min of the failing step. Page speed and run time are NFR-07; run reliability is in §5. Measured in the run manifest and the Sunday heartbeat (plan 13 P8) |

---

## 8. User experience principles

The full set, with the design system and components, is in **plan 12** (IDs `UX-01`…`UX-14`). The ones that shape requirements:

1. **Open on what changed (UX-01):** Streamlit Home is a review inbox, owned stocks first, with "mark reviewed".
2. **One snapshot, many depths (UX-02):** Telegram line → card → report, all from the same view model, so surfaces never disagree.
3. **Explain every verdict (UX-03):** TL;DR, ≤ 4 evidence bullets (thesis → qualitative → valuation/momentum → position), score attribution, bull/base/bear cases.
4. **Owned first, owned verbs (UX-04):** ADD / HOLD / TRIM / EXIT for positions; verdict names for everything else.
5. **Unknown ≠ clean (UX-05):** every check shows ✅ clean, ⚠️ flagged or ❔ couldn't check.
6. **Honest uncertainty (UX-06):** confidence levels, data-freshness stamps, "N/A" instead of forced numbers.
7. **Signal over noise (UX-07):** one monthly message; daily messages only on change; High severity immediate, everything else in the digest; one aggregated nudge instead of a per-row nag.
8. **Human in control (UX-08):** the system proposes and you decide (My Watchlist, holdings, thesis); the thesis is captured when you add a holding or approve a watchlist entry.
9. **Fast and without dead ends (UX-09, UX-10):** no network or LLM calls while a page renders; every error names the step, the reason and the next action.
10. **Private by default, shareable on purpose (UX-11):** amounts masked in notifications; privacy view; share export with the disclaimer.
11. **Readable anywhere (UX-12):** Markdown in OneDrive/VS Code/Obsidian, Telegram on phone, Streamlit for actions; colour + icon + word; Indian number formats.
12. **Learn from use (UX-13):** 👍/👎 on alerts and cards feeds alert precision and calibration.
13. **Say who wrote it (UX-14):** agent-written text is marked 🤖 with the agent's name; proposals always look like suggestions, never decisions.

---

## 9. Solution overview

Architecture: plan 00 §7 and plan 04 §1. Data layer (multi-source adapters) → Feature store and metric registry → Lenses (Value, Momentum; plug-ins) → Verdict policy → Renderers (MD/JSON/CSV) → Storage (Parquet/DuckDB + Supabase) → Notifier (Telegram primary; email; optional ntfy; WhatsApp deferred — ADR-008) → Streamlit app (via services and one design system, plan 12). It runs on GitHub Actions (monthly, daily watch, daily events). *(v1.8)* Around these workflows sits the agent layer (plan 15): one MCP server, `parakh-mcp`, over the services, and agents on the Claude Agent SDK (Qualitative Analyst, Devil's Advocate, Monthly Reviewer, Event Triage, Watchlist Curator) that reach Parakh only through it. The owner uses the same server from Claude Desktop and Claude Code. Transport is local stdio only (ADR-012).

---

## 10. Dependencies

| Dependency | Used for | Risk |
|---|---|---|
| yfinance, NSE/BSE data, broker APIs | Prices | NSE may block cloud IPs (spike in Phase 0.5) |
| Screener.in export, exchange XBRL filings | Fundamentals | Manual export effort; XBRL parsing complexity |
| BSE-filed transcripts (via Screener's Concalls list) | Concall analysis | Page layout or redirect changes → provider chain, validator and manual upload (no silent skip) |
| casparser (MIT) | CAS parsing | Statement format changes → pinned version + a redacted golden CAS fixture |
| AWS SSM Parameter Store | Secrets for scheduled runs | Account setup; fallback documented in ADR-009 |
| AMFI, niftyindices.com | Cap lists, constituents | Format changes |
| Anthropic API (Claude) + Claude Agent SDK | All agents (plan 15 §5) | Cost, rate limits; SDK API changes (pinned version, ADR-011) |
| MCP Python SDK | `parakh-mcp` server | Spec and SDK changes (pinned version; tool contract tests) |
| GitHub Actions, Supabase, Telegram | Runtime, storage, notifications | Free-tier limits |

---

## 11. Risks and mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Unreliable free fundamentals data for Indian stocks | High | High | Multi-source + trust tiers + XBRL cross-check; confidence downgrade instead of guessing |
| NSE access blocked from GitHub runners | Medium | Medium | yfinance/broker fallback; self-hosted runner on the PC for NSE steps |
| Over-fitted weights give false confidence | High | Medium | Walk-forward validation; parameter cap; calibration reports |
| Alert fatigue | Medium | Medium | State-change-only alerts, confirmation, cool-downs, digest batching, shadow mode before go-live |
| LLM hallucination in qualitative views | Medium | Medium | Citations required; transcript verification; LLM never feeds scores |
| Scope creep (many lenses, UI polish) | Medium | High | Phased rollout with exit gates (09); Could/Won't items deferred |
| Behavioural misuse (treating verdicts as certainty) | High | Medium | Confidence, bull/bear cases, devil's advocate, decision journal |
| An agent acts on injected text or oversteps its job | High | Low | Tools are the only door; propose-only writes; action tools take IDs, not text; allow-lists; audit of every call (plan 15 §8) |

---

## 12. Decisions

All decisions are logged in **plan 13 §2**. This section used to list them; it now points there so there's one source.

---

## 13. Release criteria (v1.0 = end of Phase 4)

- [ ] 3 consecutive monthly runs completed unattended, with notifications
- [ ] Daily and event watchers live for ≥ 4 weeks with zero duplicate alerts
- [ ] Full universe of ≥ 1 cap scored; Tier A deep dives for holdings + both watchlists
- [ ] Holdings reflected in verdicts, alerts and the segment summary
- [ ] Watchlist review completed via the Streamlit page at least once
- [ ] One monthly review done end to end from the review inbox; AppTest, tri-state and redaction tests green (plan 14 L5/L6)
- [ ] **UAT-5 signed** (plan 14 §7): all of the above verified in a recorded session; 0 open S1/S2
- [ ] Golden tests and lens contract tests green in CI; catalogues generated
- [ ] Owner sign-off on report quality for 10 sampled stocks
- [ ] Audit completeness test green for all runs; hash-chain integrity check green for 30 consecutive days
- [ ] `explain` produces a full lineage tree for any verdict; one historical run replayed successfully
- [ ] First quarterly governance review signed off
- [ ] Every agent run and MCP tool call in the last 3 monthly runs is audited; the "no built-in tools" and MCP-vs-CLI equivalence tests are green (plan 14)
- [ ] Remote MCP access (ADR-012) reviewed and either kept local or given its own ADR
