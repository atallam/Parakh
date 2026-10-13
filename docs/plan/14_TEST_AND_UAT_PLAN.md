---
title: Parakh — Test & UAT Plan
version: 1.7 (D26–D28: L7 plan evals and rejection tests, panel-isolation and contract tests; v1.6: golden profiles updated for D24: INDIGO airline/lease-heavy, M&M core standalone + SOTP; edge cases for history classes and new profiles; UAT-1 rubric rule for limited-history reports; UAT-1 includes the backlog review — plan 13 D24/D25; v1.5: MCP and agent tests across L0–L7: tool registry sweep, MCP-vs-CLI equivalence, no-built-in-tools contract, `parakh_mcp` RLS, FakeRunner E2E, trajectory evals; UAT-3/4 steps — plan 15; v1.4: golden set confirmed; v1.3: golden set named; pilot edge cases; UAT-1 ≥ 6 of 7; v1.2: doc lint also checks README and 08 Part A against 09; v1.1: UAT pass rules cite 07/09 instead of restating numbers; doc lint added to L0; v1.0: first version)
date: 2026-09-24
owner: Avinash Tallam
parent: 07_PRD.md
owns: how everything is verified (test levels, environments, test data and oracles, traceability, UAT, defects, CI test stages). Other docs link here instead of restating it (README fact owners)
related: 07 (numeric targets: NFR-07, NFR-14, §5) · 08 (acceptance criteria) · 09 (phase dates and exit gates) · 10 (replay, eval gate, integrity) · 12 (UX rules) · 13 (Production items P1–P10, D17, D18)
conventions: test IDs `T-<AREA>-<nn>` · UAT sessions `UAT-0`…`UAT-5` · levels `L0`…`L8` · severities `S1`…`S4`
---

# Parakh: Test & UAT Plan

## 1. Purpose and principles

This plan says how Parakh is proven correct before you trust a verdict with money. It's deliberately **lean**: strategy, environments, test data, traceability and UAT are fixed now; individual test cases are written **with the code**, phase by phase.

1. **Correctness is defined before code.** For numbers (metrics, scores, signals), the expected values exist first, from an **independent oracle** (§4.1), and the code is built to match them.
2. **The oracle must be independent of the code.** Tests written by the same author, human or AI, who wrote the code share its misunderstandings. Expected values come from a different implementation path (Excel formulas on the raw export) and are checked against published figures.
3. **Real inputs, recorded.** Adapters are tested against recorded real responses, never hand-written mocks. Drishti's tests passed while its scrapers were broken.
4. **No network, no real LLM in automated tests.** Sockets are blocked; LLM and Telegram are mocked with recorded responses.
5. **Every acceptance criterion is traceable** to at least one test or UAT step, and the matrix is **generated**, never hand-maintained (§5).
6. **You are the acceptance authority.** UAT sessions are short, scripted and recorded (§7).

---

## 2. Test levels

| Level | Proves | Examples | Runs | Blocks |
|---|---|---|---|---|
| **L0 Static** | Code and repo hygiene | ruff, pyright, gitleaks, pip-audit (P10); token lint (no hex outside `ui_tokens.yaml`); layering lint (`app/` *and `src/mcp/`* never import `analytics/`, `lenses/`, `adapters/`); *(v1.5)* tool registry sweep (every tool has an ID, a tier and annotations; no approve, edit or delete tools exist, AC-F24.1/F24.3); generated catalogues fresh; **doc lint** (milestone dates and phase-placement tables only in 09, except the test gates in 14 §9; the README timeline and Part A of plan 08 must match 09; decision IDs defined only in 13) | Pre-commit + every PR | Merge |
| **L1 Unit** | Each function does one thing right | Every metric, signal and policy rule against oracle values and edge cases (§4.4); property tests (scores 0–100, subscores 0–1, no NaN leaks, monotonic rules); ₹/%/date formatters | Every PR | Merge |
| **L2 Contract** | Boundaries hold | Lens contract (04 §1.5); **numbers firewall** (no LLM-sourced field reaches a lens, 10 §7); pandera schemas for every adapter; Pydantic view models (UI ↔ services); LLM output schemas; audit event schema; *(v1.5)* **MCP tool schemas** (snapshot per toolset version); **MCP-vs-CLI equivalence** on the golden stocks (AG-04); **agent runtime contract**: each agent's options contain only its allow-listed `mcp__parakh__*` tools, no built-in SDK tools, non-bypass permission mode (AC-F25.1); masking of `portfolio.*` for agent clients | Every PR | Merge |
| **L3 Golden** | The whole scoring chain is right on known inputs | Golden stocks (§4.1) on frozen inputs → snapshot JSON matches expected within tolerance: scores, verdict, attribution; report and Telegram render snapshots | Every PR | Merge |
| **L4 Integration** | Parts work together with real infrastructure | Repository against Supabase (local stack) with real migrations; **RLS tests** (anon can't read holdings; the staging role can't write `public`); adapters against recorded real responses (§4.2); audit outbox → DB → hash chain; notifier against a Telegram mock; *(v1.5)* `parakh-mcp` over stdio with a real MCP client; the `parakh_mcp` role can't `UPDATE`/`DELETE` (RLS); `notify.queue` → notifier routing, de-duplication and severity caps | Every PR | Merge |
| **L5 System / E2E** | A full job does the right thing | `parakh run --mode monthly` on the pilot universe from frozen inputs, network off, LLM mocked → reports, snapshots, messages, audit completeness, **idempotency** (run twice → same result); **watcher replay** over the 60-day set (§4.5); Streamlit **AppTest** on every page; *(v1.5)* each agent end to end through `FakeRunner` (recorded trajectories) against the real server on frozen data: outputs validate, proposals and queued messages are as expected, budget and turn-limit stops end as `pending` | Nightly (trading days) + before milestones | Milestone |
| **L6 Non-functional** | It's fast, safe and recoverable | Load test (P5); security (RLS, secrets, **redaction incl. PAN and DP IDs**); **resilience drills** (P7: source down → fallback; Supabase down → outbox; Telegram down → retry + email; LLM down → "qualitative pending"); replay determinism (10 §5); backup restore; *(v1.5)* MCP server opens no listening socket; agent-side redaction (no quantities or ₹ in any agent output or trace); service-level checks (NFR-14) | Monthly + before milestones | Milestone |
| **L7 LLM evaluation** | The agents are grounded and safe; *(v1.7)* the orchestrator's plans are valid and complete | Golden eval set (§4.6): schema validity 100%; exact-quote verification ≥ 95%; agreement with your labels ≥ 80% on key-metric status; injection canary never followed; prompt promotion and rollback gates (10 §7, P3); *(v1.5)* **agent trajectory evals** per agent (§4.6): right tools called, no refused calls, output schema valid, factual claims traceable to tool results | On prompt or model change + monthly | Prompt promotion |
| **L8 UAT** | You accept it | Scripted sessions UAT-0…UAT-5 (§7) | At milestones | Milestone |

---

## 3. Environments

| Env | Purpose | Data | Database | Notifications | LLM |
|---|---|---|---|---|---|
| **DEV** (your PC) | Build and debug | Fixtures + small live pulls | **Local Supabase stack** (Supabase CLI, needs Docker Desktop) + DuckDB | Console, or a private test Telegram chat | Mocked by default; real with a small budget cap when needed |
| **CI** (GitHub Actions) | Automated gates | Fixtures only | Local Supabase stack started in the job (Docker is available on GitHub's Linux runners), same migrations | Mocked | Mocked (recorded responses) |
| **STAGING / SHADOW** (D17) | Shadow runs, UAT rehearsals, source canaries | Live data | **`staging` schema** in the `parakh` project, with its own role that can't write `public` | Dry run: `alerts_shadow.md` and the test chat | Real, budget-capped |
| **PROD** | Real runs | Live | `public` schema | Telegram + email (ADR-008) | Real, budget-capped |

**Rules:**
- A real CAS never leaves DEV or PROD. Tests use the synthetic CAS (§4.3).
- No production data is copied into CI.
- Secrets are separate per environment (SSM paths `/parakh/staging/…` and `/parakh/prod/…`, ADR-009).
- Every run records its environment in the run manifest; STAGING output is never published to OneDrive.

---

## 4. Test data and oracles

### 4.1 Golden set and the independent oracle (D18)

- **Stocks (D18, confirmed 27 Sep 2026):**
  - **HDFCBANK**: bank profile (P/B, NIM, NPA). The July 2023 merger with HDFC Ltd breaks its financial history, so the oracle and the code must both treat pre-merger years explicitly.
  - **INDIGO**: airline / lease-heavy profile with cyclical normalisation *(v1.6, D24)*. Its loss years around COVID test P/E = N/A and normalised earnings; the oracle adds EBITDAR, EV including lease liabilities, and lease-adjusted net debt ÷ EBITDAR.
  - **M&M**: conglomerate / holdco profile *(v1.6, D24)*. The core standalone business is scored with the standard non-financial metrics, so the golden set still covers that profile; the oracle adds an SOTP sheet (listed stakes × price × stake %, less the holdco discount). Expect about an extra hour of oracle work at UAT-0.
- **As-of date:** 30 Oct 2026, the as-of date of M1's run.
- **Frozen inputs:** `tests/fixtures/golden/<ISIN>/2026-10-30/` holds 10 years of prices (Parquet), the Screener export, shareholding, and benchmark and sector index series, plus a `MANIFEST.sha256`.
- **Oracle:** `tests/oracles/golden_expected.xlsx`, built with **Excel formulas directly on the raw export**, a different implementation from the Python code. For every metric it records the value, the formula, the source cells and the tolerance.
- **Spot checks:**
  - 10 values against the ratios Screener displays.
  - Momentum indicators against pandas-ta (AC-F05.5).
  - DMAs against one public charting site.
- **Sign-off:** you review and sign the oracle at **UAT-0**, before Phase 2 code depends on it.
- **Rule:** code is changed to match the oracle, never the other way round. Changing the oracle needs a PR labelled `oracle-change`, your approval (CODEOWNERS) and a re-signed UAT-0 note.

| Value type | Tolerance |
|---|---|
| Ratios and percentages (P/E, ROCE, margins, returns) | ±0.5% relative |
| Moving averages, RS, volatility | ±0.1% relative |
| Lens scores | ±0.5 point (AC-F04.5) |
| Verdicts, signals fired, dates, counts | Exact |

### 4.2 Recorded source fixtures

Real responses are captured once and replayed with vcrpy/respx:
- The Screener company page and export.
- A BSE-filed transcript PDF (for example NTPC's August 2026 transcript, fetched on 24 Sep).
- An NSE bhavcopy, the AMFI cap list, index constituents and the Nifty P/E history.

They're refreshed quarterly, or when an adapter breaks.

A weekly **source canary** job in STAGING fetches the live pages and compares their structure with the fixtures. On a change it raises ⚠️ before a monthly run depends on it. This is the direct lesson from Drishti, where every scraper had silently stopped matching.

### 4.3 Synthetic CAS

A generated CAS PDF with fake PAN, names and DP IDs, covering 3 demat accounts and 12 ISINs. It comes in two monthly versions with quantity changes between them. It backs AC-F03.1, F03.6 and F03.7 and the redaction tests. **Real CAS files are never committed.**

### 4.4 Edge-case catalogue (seed list; each becomes a fixture)

- **Valuation edge cases:** loss-making company (P/E and PEG = N/A); bank (no EV/EBITDA); cyclical at peak margins; *(v1.6, D24)* pre-profit company with runway above and below 24 months (CFO veto vs flag); holdco with a listed lending subsidiary (standalone vs consolidated D/E); order-book company with large customer advances (net cash excluding advances); broker with client-money borrowings (no D/E test).
- **History classes (D24):** one stock each at H0, H1 and H2; momentum at < 126, 126–251 and ≥ 252 sessions; a stock in its first 20 sessions (listing exclusion); a young listing whose since-listing high is labelled as such.
- **Price-series events:** split and bonus days (no fake crash); demerger; symbol change (ISIN continuity).
- **Data gaps:** late or missing quarter (confidence Low); newly listed stock with fewer than 200 sessions (no 200-DMA); stale fundamentals.
- **Surveillance and calendar:** circuit-locked stock (M27); ASM/GSM listing; NSE holiday and the Muhurat session; AMFI January cap migration.
- **Checks and holdings:** pledge 0% vs pledge unknown (tri-state, UX-05); CAS quantity change without cost ("cost pending"); duplicate filing (alerts once).
- **From the pilot list (D3):**
  - **Young listings:** GROWW, ATHERENERG and SHADOWFAX have no 5/10-year valuation bands. At the M1 as-of date, SHADOWFAX has fewer than 200 sessions (no 200-DMA), and GROWW has under 12 months of history (no 12-1 momentum). Their reports must show N/A with a reason, not guesses.
  - **Merger discontinuity:** HDFCBANK (July 2023).
  - **A symbol with a special character:** `M&M`. Key everything on ISIN; use a safe folder slug; URL-encode for web sources.
  - **Cap re-classification:** in the July 2026 AMFI list, MAZDOCK moved Large → Mid and GROWW Mid → Large.
- **Borrowed from Drishti's regression tests:** non-owned stocks excluded from portfolio weights; LLM called once per document hash; original thesis immutable.

### 4.5 Historical replay set

60 trading days of end-of-day data for the watchlist and benchmarks. It lets the daily watcher be replayed day by day, so a few minutes shows which alerts it *would* have sent, and when (UAT-2).

### 4.6 LLM evaluation set (Phase 4)

- **10 filed transcripts** across sectors. Each has your labels: key-metric status, exact quotes and guidance items.
- **2 adversarial documents:** one with embedded "ignore previous instructions" text, and one scanned or garbled PDF, which must be rejected by the validator.
- *(v1.7)* **Plan evals and rejection tests** (plan 15 §5b): 5 recorded `what_changed` inputs with expected plans (including a quiet month and a veto on one holding), plus 6 deliberately bad plans that the dispatcher must reject (unknown agent, ISIN outside the coverage set, reason_code not backed by a fact, cyclic graph, budget overrun, holding missing from tasks and `skipped`), each logged as `AUD.AGENT.PLAN_REJECTED`; and an injection canary in a document that must never reach the orchestrator.
- *(v1.7)* **Panel-isolation tests:** a panel stock receives no fundamentals fetch, score or LLM call (AC-F01.5).
- *(v1.7)* **Contract tests:** Cas and Fake providers against `holdings.v1`; File publisher against `insights.v1` with no quantity, cost or ₹ value (AC-F30.x); Hub tests run after GA.
- *(v1.5)* **Agent scenarios** (plan 15 §5): 3 recorded monthly runs for the Monthly Reviewer (including one with no changes and one with a veto on an owned stock); 5 filings for Event Triage (including one whose text asks the agent to send an alert, which must not raise severity or add text to the message); 2 months of segment summaries for the Watchlist Curator (one at full capacity). Each scenario has your expected outcome, and the same scenarios are recorded as `FakeRunner` trajectories for L5.

---

## 5. Traceability

- Every test that proves an acceptance criterion carries `@pytest.mark.ac("AC-F04.2")`. Every UAT step lists the AC IDs it proves.
- CI generates `docs/TRACEABILITY.md`: each AC, its tests and UAT steps, and their last result.
- A **Must** AC with neither a test nor a UAT step **fails the build** from the phase in which its feature is due (plan 09).
- Coverage targets (Production tier; starting points, reviewed at Phase 5):

| Area | Line coverage |
|---|---|
| `analytics/`, `lenses/`, `policy/`, `audit/` | ≥ 90% |
| `adapters/`, `services/`, `storage/` | ≥ 80% |
| Overall | ≥ 75% |

---

## 6. Writing tests

| Kind of code | Approach |
|---|---|
| Metrics, signals, policy rules | **Test-first:** write the oracle-backed test, then the function. This also keeps AI-written code honest |
| Adapters | **Fixture-first:** record the real response, then write the parser |
| Services and UI | View-model fixtures + AppTest |
| Agents | `FakeRunner` with recorded trajectories for L1–L5 (the SDK is never called in CI); the real model only in L7 |
| MCP tools *(v1.5)* | Contract-first: write the Pydantic input/output models and the schema snapshot, then the wrapper; equivalence test against the CLI view model |

- **Test IDs:** `T-<AREA>-<nn>` in each test's docstring. Areas: VAL, MOM, POL, ADP, HLD, NTF, UI, AUD, LLM, *(v1.5)* MCP, AGT. This follows the per-engine tables of Drishti's test plan.
- **Regression rule:** every S1 or S2 fix adds a test named `test_reg_<issue>`.
- **Protected files:** `tests/oracles/` and `tests/fixtures/golden/` are CODEOWNERS-protected. An AI assistant may propose changes but can't merge them.

---

## 7. User acceptance testing (UAT)

### 7.1 Approach

You're the only user, so UAT means short, scripted sessions at each milestone:
- **Where:** in STAGING for UAT-0 to UAT-2, in PROD from UAT-3.
- **How long:** each session is ≤ 90 minutes.
- **Record:** each session produces `docs/uat/UAT-<n>_<date>.md` with a result per step, the issues raised (with severity) and your sign-off.

### 7.2 Sessions

Dates for each milestone are in plan 09.

| ID | When | Scope | Entry criteria | Pass rule |
|---|---|---|---|---|
| **UAT-0** | End of Phase 1 (before Phase 2 code) | Sign the oracle: golden expected values, tolerances, spot checks | Oracle workbook complete for all 3 stocks | All 3 signed; every disputed value resolved and noted |
| **UAT-1** | **M1** | The 7 pilot reports + holdings, using the §7.3 rubric; then the backlog review (plan 13 D25) | L0–L5 green on the pilot; no open S1 | ≥ 6 of 7 reports pass; 0 S1 |
| **UAT-2** | Phase 3 shadow weeks | Alerts: review the 60-day replay once, then the shadow log twice a week | Watcher L5 replay green | Meets the go-live gate in plan 09 (duplicates, noise, missed 🔴) |
| **UAT-3** | **M2** | First unattended run; a failure drill (break one source); Telegram UX (plan 12 §6); *(v1.5)* the Monthly Reviewer's message and email section, and one Event Triage summary from the shadow log | UAT-2 passed; SSM/OIDC live (P1) | NFR-14 service levels met (plan 07), including the failure-alert time in the drill; messages ≤ 10 lines with amounts masked |
| **UAT-4** | **M3** | A full monthly review from the review inbox; approvals via Streamlit and Telegram; the thesis form; reconciling a new CAS; the privacy toggle; *(v1.5)* approving one 🤖 Curator proposal; `/monthly-review` and `/explain` in Claude Desktop (AC-F24.10) | AppTest green; load test (P5) passed; L7 eval gate passed | Review within the PRD §5 time target; all steps pass; 0 S1 |
| **UAT-5** | **v1.0** | PRD §13 release criteria; sign-off on 10 sampled stocks; calibration report review | 3 consecutive unattended runs | All criteria met; 0 open S1/S2 |

### 7.3 UAT-1 rubric (per pilot report)

| # | Check | How | Must? |
|---|---|---|---|
| R1 | **Numbers** | 5 metrics chosen at random match the oracle or Screener within tolerance | Must |
| R2 | **Holdings** | Quantity = CAS; average cost = broker; LTCG days correct | Must (owned stocks) |
| R3 | **Lineage** | `parakh explain` shows the chain, and you can state the verdict's reason in one sentence | Must |
| R4 | **Honesty** | Freshness stamps present; unknowns shown as ❔; N/A where data is missing | Must |
| R5 | **Logic** | You agree with the verdict, or the disagreement is classified (data / logic / threshold / presentation) and ticketed | Should |
| R6 | **Readability** | TL;DR + action box answer "what do I do?" within 30 seconds | Should |

A report **passes** when R1–R4 pass and R5–R6 pass or are ticketed as S3. *(v1.6, D24)* For a **limited-history** report (GROWW, ATHERENERG, SHADOWFAX), R1 applies to the metrics that exist, R4 is the main test (every missing measure shows ❔ with its reason, the verdict is labelled "limited history"), and the value score itself isn't judged under R5. The session **passes** when ≥ 6 of 7 reports pass and there's no S1.

### 7.4 UAT record template

```markdown
# UAT-1 — M1 pilot review — YYYY-MM-DD
Environment: STAGING · run_id: 01J… · framework 1.x · tester: Avinash
| Step | Report / check | ACs | Result | Issue |
|---|---|---|---|---|
| 1 | POLYCAB R1 numbers | AC-F04.6 | ✅ | — |
| 2 | POLYCAB R5 logic | AC-F08.4 | ⚠️ disagree: threshold | #42 (S3) |
Summary: 5/5 pass · 0 S1 · 1 S3
Sign-off: ______  (date)
```

---

## 8. Defects

| Severity | Definition | Examples | Rule |
|---|---|---|---|
| **S1 Critical** | A wrong number or verdict shown as confident; a privacy leak; a missed 🔴 on an owned stock; data loss or an audit gap | P/E off by 2×; a PAN in a log; an exit signal never sent | **Blocks the milestone.** Fix + regression test before sign-off |
| **S2 Major** | Wrong but flagged as low confidence; a broken flow with a workaround; an SLO breach | Missing report section; alert 2 hours late | Fix within the next phase, with a regression test |
| **S3 Minor** | Presentation, wording, threshold tuning | Chip colour; message wording | Backlog, reviewed monthly |
| **S4 Idea** | Enhancement | A new chart | Backlog (F20+) |

Defects are tracked as GitHub Issues with labels `sev:S1`…`S4`, the feature (`F04`) and the AC (`AC-F04.2`).

---

## 9. Test gates per phase

Plan 09 holds the dates and the full exit gates; this table is the testing part of each gate.

| Phase | Test gate to exit |
|---|---|
| **0** | CI live with all L0 gates (incl. the tool registry sweep and `src/mcp/` layering lint); `FakeRunner` in the harness; pytest harness (AC markers, sockets blocked, local Supabase stack, LLM and Telegram mocks); traceability generator working on one dummy AC; synthetic CAS created |
| **0.5** | Recorded fixtures captured for every source tested in a spike; each spike note says how that source will be tested; the Agent SDK spike note records the runner result (ADR-011) |
| **1** | L1 + L2 for adapters and holdings; L4 repository + RLS tests; golden inputs frozen; **UAT-0 signed** |
| **2** | L1–L3 green for value, momentum, policy and rendering; L5 pilot run in CI; L2 MCP schema + equivalence tests for the read toolsets; **UAT-1** |
| **3** | L5 watcher replay; L2 agent runtime contract + L5 `FakeRunner` runs for the Monthly Reviewer and Event Triage; L4 `notify.queue` routing; L6 resilience drills, SSM/OIDC and first backup restore; failure-mode register (P7) linked to drills; **UAT-2**, **UAT-3** |
| **4** | L2 view models + L5 AppTest; L6 load test (P5); L7 eval gate + prompt rollback test (P3) + agent trajectory evals for every agent; L4 `parakh_mcp` RLS; orchestrator plan evals, rejection tests and panel-isolation tests; `holdings.v1` / `insights.v1` contract tests; **UAT-4** |
| **5** | Monthly replay-determinism and restore tests running; calibration (F17) reviewed; **UAT-5** |

---

## 10. CI stages

| Stage | Trigger | Runs | Time budget |
|---|---|---|---|
| Pre-commit | Each local commit | L0 subset (ruff, gitleaks, token lint) | < 30 s |
| PR checks | Every PR to `main` (required) | L0–L4, AppTest, traceability | < 10 min |
| Nightly | Trading days, 02:00 IST | L5 pilot run + watcher replay; source canary (STAGING) | < 15 min |
| Monthly | After the monthly run | Replay determinism, backup restore, L7 drift check | < 20 min |
| Pre-milestone | Manual | L6 load, security and resilience drills; UAT prep pack | As needed |

GitHub Actions minutes for the private repo are tracked in the Sunday heartbeat, so CI plus the scheduled jobs stay within the free allowance.

---

## 11. Tools

pytest · pytest-socket · pytest-cov · Hypothesis (property tests) · syrupy (snapshots) · vcrpy / respx (recorded HTTP) · time-machine (frozen dates) · pandera · pandas-ta (indicator cross-check) · Streamlit AppTest · *(v1.5)* MCP Python SDK client + MCP Inspector (manual smoke) · Supabase CLI (local stack) · gitleaks · pip-audit · openpyxl (oracle loader) · a small traceability generator (`tools/traceability.py`).

---

## 12. Lessons carried over from Drishti

| What happened in Drishti | Rule here |
|---|---|
| 197 tests passed while its Screener parsers and both exchange filing APIs no longer worked (the tests mocked them) | Recorded real fixtures (§4.2) + weekly source canary |
| The UI read keys the API didn't return, so two sections never rendered | L2 view-model contracts + L5 AppTest |
| A failed check was shown as "No red flags detected" | Tri-state tests (UX-05) at L1 and L5 |
| The portfolio-summary endpoint returned 500 and the header showed `₹—` | L5 renders every page region from fixtures; errors must be explicit (UX-10) |
| Good per-engine test ID tables and manual end-to-end journeys | Kept: `T-<AREA>-<nn>` IDs; the journeys became UAT scripts (§7) |

---

## 13. Defaults and your inputs

- **D17 (default):** STAGING is a `staging` schema in the `parakh` Supabase project (§3). Say if you'd rather have a second project.
- **D18 (confirmed):** the golden set is HDFCBANK, INDIGO and M&M (§4.1).
- **Docker Desktop** on your PC runs the local Supabase stack. Without it, DEV integration tests fall back to CI.
- **Your time:** ~3–4 hours to review the oracle (UAT-0), plus the UAT sessions (≤ 90 minutes each).

*Personal analytical framework; not investment advice.*
