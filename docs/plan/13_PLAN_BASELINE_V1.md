---
title: Parakh — Plan Baseline v1.0 (locked)
version: 1.24 (BL-01 done: AWS account ready, OIDC role and Parameter Store loader written; v1.23: Phase 3 built, §8.0d; v1.22: UAT-0 and UAT-1 added to the prep backlog as BL-05 and BL-06; v1.21: Phase 1 built and loaded, §8.0c; order book and offer-document financials move to the Phase 2 document work; pilot is 4 Large, 1 Mid, 2 Small by AMFI; v1.20: all Phase 0.5 spikes closed; BL-02/03/04 done; v1.19: Phase 0.5 spikes done, §8.0b; backlog BL-02…BL-04; v1.18: Phase 0 build done on branch phase-0, PR #1, CI green; docs/plan in the repo is now the canonical copy; v1.17: D10 amended: repo inside the OneDrive Stock Analysis folder, venv kept outside; Phase 0 scaffold done; v1.16: AWS account setup moved to the prep backlog as BL-01, not blocking until Phase 3; Phase 0 started 28 Sep; v1.15: D23 systematic engine, not sell-side research; D24 pilot sector profiles + limited history before M1; D25 scope freeze; v1.14: scaffold rebuilt with the parakh profile; v1.13: agentic, MCP-first: D20–D22, P2 reworded, §4.4 consequences, plan 15 added; v1.12: Telegram bot live; v1.11: Docker installed; v1.10: tools installed; v1.9: Python via uv; v1.8: week-1 prep progress; v1.7: D19 private files in OneDrive; v1.6: CAS saved; move out of OneDrive; v1.5: golden stocks confirmed; v1.4: pilot list and golden proposal; v1.3: readability pass: plain README, 08 Part A, F23; v1.2: one-owner pass: dates → 09, SLOs → 07 NFR-14, phase column removed; v1.1: docs restructured; plan 14 added; defaults D17/D18; §5 now points to 09)
date: 2026-09-24
owner: Avinash Tallam
status: LOCKED. This is the plan of record; changes follow §6
supersedes: the open-decision lists in 00 §10 and 07 §12 (now resolved here)
---

# Parakh: Plan Baseline v1.0

**Parakh** (परख, "to assay") is the personal stock analysis framework described in FRAMEWORK 00–14 (start with `README.md`). This document records every decision that closes the planning stage, what the **Production** tier adds, and how the plan changes as a result. From here, work starts on the dated rollout (09) on **Monday 28 September 2026**.

---

## 1. What "locked" means

- This document and FRAMEWORK 00–12 at the versions in §7 are the **plan of record**.
- The decisions in §2 are closed. Reopening one needs a changelog entry and, if it's significant, an ADR (§6).
- New ideas go to the backlog (F20+). **No new scope enters a phase after its first week** (09 §5).

---

## 2. Decision log (all open decisions closed on 2026-09-24; D17–D18 added in v1.1, D19 in v1.7, D20–D22 in v1.13, D23–D25 in v1.15)

| ID | Decision | Locked choice | Where it's applied |
|---|---|---|---|
| D1 | Name | **Parakh**: repo `parakh`, CLI `parakh` (alias of `python run.py`), Telegram bot "Parakh" | 00, 04, 07, 09 |
| D2 | Tier | **Production**: all 34 items of the SCAIX AI project checklist (§3) | 04, 07, 08, 09 |
| D3 | Pilot stocks (M1) | *(updated 27 Sep 2026)* **7 stocks**, grouped by the AMFI July 2026 list: **Large** INDIGO, M&M, HDFCBANK, GROWW · **Mid** MAZDOCK, ATHERENERG · **Small** SHADOWFAX. GROWW moved up to Large and MAZDOCK down to Mid in that list; ATHERENERG and SHADOWFAX are placed by market cap and confirmed from the AMFI file in Phase 1 | 09 Phase 0–2, 14 §7 |
| D4 | Fundamentals | **Screener.in export** (your account) as primary; exchange-filed XBRL results as the cross-check | 00 §7, 08 F02 |
| D5 | Notifications | **ADR-008 accepted**: Telegram primary (buttons + commands), email for the monthly archive, ~~Claude push for the narrative review~~ *(amended 27 Sep 2026, D22: the Monthly Reviewer agent's review goes to Telegram + email)*. ntfy not enabled (can be switched on later); **WhatsApp deferred** | 03 §4, 04 |
| D6 | Scheduler | **ADR-003 accepted**: GitHub Actions in a private repo; Windows Task Scheduler as fallback; a self-hosted runner on your PC if NSE blocks cloud IPs | 03 §2, 04 |
| D7 | Concall source | **Screener's Concalls list → BSE-filed transcript PDF** (verified working 2026-09-24), porting Drishti's extraction and validation pipeline; concall.in optional | 08 F06, 09 Phase 0.5, archive/11 §3 |
| D8 | Holdings source | **CAS statement (NSDL/CDSL)**, parsed locally; a one-time cost-basis seed, plus CLI entries for trades between statements (§4.1) | 05 §2, 08 F03 |
| D9 | Small-cap universe | **Nifty Smallcap 250 only** | 05 §1, 08 F01 |
| D10 | Repo location | *(amended 28 Sep 2026, your choice)* **`Stock Analysis\parakh`** inside the OneDrive folder (was `C:\dev\parakh`). The repo is a subfolder so `.env`, the CAS PDFs and FRAMEWORK stay out of git; the code finds `..\.env` itself. Accepted risk: OneDrive sync can lock or conflict files in `.git` during commits. Guard rails: the virtual environment lives **outside OneDrive** (`UV_PROJECT_ENVIRONMENT=C:\Users\atall\.venvs\parakh`), GitHub is the source of truth (push after each session), and if sync conflicts appear the repo moves back to `C:\dev\parakh`. Reports are published into the `Stock Analysis` folder | 04 §4 #11, 09 |
| D11 | Storage | **Supabase from Phase 1** for operational tables (dedicated `parakh` project); Parquet + DuckDB for prices and analytics, with Parquet kept in Supabase Storage for cloud runs (§4.2). ADR-004 amended | 04, 05 §3, 09 |
| D12 | Hurdle rate | **15%** expected CAGR for a value BUY | 01 §11, 08 F04 |
| D13 | Thesis | **Structured THESIS.md** (schema in plan 05 §2.4). The concall agent checks each call against it. **The LLM can only flag**; BROKEN needs a metric breaker or your confirmation | 08 F06/F09, 12 §5.3 |
| D14 | Timeline | **Start 28 Sep 2026** on the dated plan in 09 (M1 → M2 → M3 → v1.0), ~8–10 hrs/week | 09 |
| D15 | UI | ADR-006 (Streamlit, thin UI over services) + plan 12 design system | 04, 12 |
| D17 *(v1.1, default)* | Staging / shadow environment | A **`staging` schema in the `parakh` Supabase project**, with its own database role that can't write `public`. A second Supabase project only if a free slot exists or you move to Pro. *Default; change it if you disagree* | 14 §3 |
| D18 *(confirmed 27 Sep 2026)* | Golden test stocks | **HDFCBANK** (bank), **INDIGO** (cyclical), **M&M** (standard non-financial profile, standing in for a compounder). These are the only pilots with 10+ years of listed history. Frozen as of 30 Oct 2026 (M1's as-of date); expected values come from an independent Excel oracle that you sign (UAT-0) | 14 §4.1 |
| D19 *(27 Sep 2026)* | Where your private files live | The CAS PDFs (`Stock Analysis\FILES FOR ANALYSIS\`) and `.env` (`Stock Analysis\.env`) **stay in OneDrive**, by your choice. Accepted risk: both sync to Microsoft's cloud and to every device on your account, and the password sits beside the file it opens. Guard rails: the code reads both through configured paths (`PARAKH_ENV_FILE`, `cas.inbox_dir`), so neither is ever inside the repo (`.env` stays git-ignored and gitleaks still runs); the `Stock Analysis` folder is never shared as a whole, only single reports through the redacted `share` export; keep 2-step verification on your Microsoft account | 05 §4, P6 |
| D16 | Drishti | Outside Parakh's scope. Parakh reuses its code and ideas per the archived plan 11; the Drishti app's own future isn't decided here | archive/11 |
| D20 *(27 Sep 2026)* | Agentic design | **MCP-first (ADR-010).** One `parakh-mcp` server over the services is the only way agents reach data or state. Scoring and the watchers stay deterministic code workflows; agents do the judgement work (review, qualitative reading, counter-arguments, event triage, watchlist curation) and **only propose**. No approve, edit or delete tools | 15, 00 §7, 03, 04, 06, 07, 08 F24/F25, 09, 10, 12, 14 |
| D21 *(27 Sep 2026)* | Agent runtime | **Claude Agent SDK (ADR-011)**, only through the `AgentRunner` interface; built-in tools disabled; a recorded deviation from the SCAIX LangGraph default | 15 §6, 04 |
| D22 *(27 Sep 2026)* | MCP transport | **Local stdio only (ADR-012)**: on your PC (Claude Desktop, Claude Code) and inside job runners; no network listener. **Revisit in Phase 5, before v1.0** (reminder set) | 15 §7, 09 Phase 5 |
| D23 *(28 Sep 2026)* | What Parakh is | **A systematic engine held to institutional rigour, not a sell-side research product.** The same rules on observable data for every stock; the right valuation framework per sector; sourced numbers; honest unknowns. **Not built:** own earnings forecasts, 12-month price targets, formal ratings. The "what's priced in" answer is the reverse DCF and expected return vs the 15% hurdle (D12). Consensus and results context is backlog item **F26**; own forecasts for up to 5 holdings are a post-v1.0 option (F20), only if missed after 3 live months. Why: coverage maths (≈ 500 stocks, 8–10 h/week), consistency over narrative, and SEBI Research Analyst exposure | 00 §1, 07 §3.2, 08 F26/F20 |
| D24 *(28 Sep 2026)* | Pilot frameworks before M1 | **Correctness, not new scope.** Before M1, the value lens gets the profiles the pilot needs (airline/lease-heavy for INDIGO, conglomerate SOTP for M&M, order-book for MAZDOCK, capital-market intermediary for GROWW, new-age/pre-profit for ATHERENERG and SHADOWFAX) and both lenses get limited-history rules (history classes H0–H2; per-measure minimum sessions). A lens without enough history is **informational**, and the verdict says "limited history" | 01 §3, 02 §3.9, 00 §5, 08 F04/F05, 09 Phases 1–2, 14 §4 |
| D25 *(28 Sep 2026)* | Scope freeze | **From Mon 28 Sep 2026 until the M1 review, no new scope.** Every new idea becomes a backlog item (F20+ or a GitHub Issue). The backlog, including F26, is reviewed once, right after UAT-1. The test for any proposal: **does it change a decision I make with money, at the frequency I actually make it?** | §6, 09 §5, 14 §7.2 |

---

## 3. Production tier: checklist result and additions

The plan was checked against all 34 items of your AI project checklist (Production column).

**Result before this baseline: 26 / 34 covered (76%).** Already covered:
- **Structure and prompts:** prompt files versioned in `src/prompts/`; the LLM never produces a score number.
- **Reliability:** Tenacity retries, Pydantic validation, hard `max_iterations`, graceful degradation to "qualitative pending", per-run token budget.
- **Observability and audit:** Langfuse from day one, structured logs, cost per run, full audit trail with human review points.
- **Tests:** golden tests, mocked LLM in CI, contract tests.
- **Secrets:** `.env` locally, redaction processor.
- **Agentic design:** fallbacks and outbox, confidence levels, human-in-the-loop approvals.

**The 8 gaps, now closed in the plan:**

| # | Checklist item | Gap | Locked fix |
|---|---|---|---|
| P1 | AWS Secrets Manager / Parameter Store in production | The plan used GitHub Secrets | **AWS SSM Parameter Store (SecureString)**, read by GitHub Actions through **OIDC** (no long-lived AWS keys; GitHub stores only the role ARN); `.env` locally. **ADR-009.** If you'd rather not use AWS, the recorded deviation is GitHub *environment* secrets with required reviewers |
| P2 | Separate agents / tools / orchestration modules | Only `agents/` was named | *(Reworded in v1.13, D20/D21)* `src/agents/` (one module per agent + `runtime/` with `AgentRunner`), `src/mcp/` (the `parakh-mcp` toolsets: thin wrappers over services, permission tiers, no state-changing tools), `src/orchestration/` (the deterministic workflow per job) |
| P3 | Rollback strategy for prompt changes | Promotion gate existed, rollback didn't | Active prompt versions pinned in `config/prompts.yaml`. Rollback = a PR reverting the pin (`AUD.PROMPT.ROLLED_BACK`). LLM cache keyed by prompt version, so a rollback reuses old outputs at no token cost |
| P4 | Alerts for LLM failures / unexpected outputs | Events were logged, nothing alerted | Telegram ⚠️ at the end of a run if Pydantic validation failures > 10% of calls, any budget stop, any suspected prompt injection, or unverified citations > 20% |
| P5 | Load test for concurrent agent execution | Missing | Before the Phase 4 scale-up: a full-universe (~500 stocks) dry run with mocked LLM at the configured concurrency and throttled adapters. Pass = within the NFR-07 run-time target with no unhandled rate-limit errors. Plus a test that an Anthropic 429 or overload triggers backoff and then "qualitative pending" |
| P6 | Data-privacy controls before PII reaches a cloud model | New risk from D8 (CAS carries PAN, name, address, DP/client IDs) | CAS parsed **locally, in memory**. Only ISIN, quantity and an account alias are persisted. PAN, name, address and DP/client IDs are never stored or logged (hashed only if needed for de-duplication). CAS files never go to an LLM or to storage the app writes to (Supabase, GitHub); your own OneDrive copy is D19. The CAS password lives in the secret store. The redaction test adds PAN and DP-ID patterns |
| P7 | Failure modes documented before first deployment | Spread across 03/04/09 | `docs/FAILURE_MODES.md` before **M2** (the first unattended run is the first deployment): each failure (source down, NSE blocked, CAS late, Supabase paused, LLM outage, Telegram down, bad corporate action, token leak, verdict flip-flop) with detection, impact, mitigation and your action |
| P8 | SLA for latency and reliability | Run-time targets existed; delivery SLOs didn't | **SLOs** (below) monitored in the run manifest and the Sunday heartbeat |

**SLOs (P8)** are defined as **NFR-14 in plan 07**, alongside NFR-07 (page speed, run time) and the PRD §5 reliability metric.

**Two Production hygiene items beyond the checklist:**
- **P9, Supabase plan.** Use a dedicated `parakh` project on the Free plan, with the weekly encrypted `pg_dump` and monthly restore test from plan 10 (the Free plan has no backups of its own). Check your free project slots first, since the Free plan allows 2 active projects and WealthLens may be using them. Upgrade to Pro (from $25/month) if the database passes 400 MB, a restore test fails, or you want daily backups.
- **P10, CI security gates.** Secret scanning (gitleaks) and a dependency audit (pip-audit) as required checks on `main`, alongside the existing branch protection and PR-only change control.

**Result with this baseline: 34 / 34 items are designed in.** The build proves each one at the phase shown.

---

## 4. Consequences of the locked choices

### 4.1 Holdings from CAS (D8)

- **What CAS gives:** quantities per ISIN across all demat accounts. The open-source `casparser` (MIT) parses NSDL/CDSL statements into **holdings only, without transactions or cost**.
- **Filling the gap:**
  - **One-time seed (Phase 1):** a cost basis per lot, from your broker's tradebook or tax P&L export, or entered with `parakh holdings add`.
  - **Each new CAS:** Parakh compares quantities with the stored lots. Any change creates a "complete this trade" prompt (price and date) in Telegram and Streamlit. Until you fill it in, P&L and the LTCG timer show **cost pending** instead of a guess (UX-05).
- **Timing:** CAS arrives some days after month-end, so the monthly run on the 2nd uses the latest CAS plus any trades you've entered since. The next CAS reconciles them (`AUD.HOLDINGS.IMPORT`).
- **Later option (Phase 6):** fetch the CAS email from Gmail automatically.

### 4.2 Supabase from day one (D11)

- The `SupabaseRepository` is built in Phase 1, not Phase 4. `DuckDBRepository` stays for local analytics and tests.
- Operational tables live in Supabase from Phase 1: holdings, runs, snapshots, signals, events and audit. RLS is on from the start.
- Price history is Parquet in Supabase Storage (tens of MB for the full universe), queried with DuckDB in each run. This removes the "repo cache" question for GitHub Actions.
- Free projects pause after a week without activity. The trading-day jobs prevent that; the heartbeat also touches the database on Sundays.

### 4.3 Timeline

The Production tier, Supabase from day one and CAS import add an estimated **12–14 hours before M1** (Supabase schema, RLS and repository ~6 h; CAS import, PII rules and cost seed ~5 h; CI security gates ~2 h). These are estimates.

Every Production item that a *manual* run doesn't need has moved to Phases 3–4: SSM/OIDC, failure-mode register, SLOs, LLM alerts, load test and prompt rollback. That keeps the dates, but **M1 is now the tightest milestone**.

*(v1.15, D24)* The pilot profiles and limited-history rules add an estimated **6–8 hours before M1** (five profiles ~4 h, history rules in both lenses ~2 h, profile data inputs and the extra oracle work ~2 h). These are estimates. They aren't optional: without them, 3 of the 7 pilot reports can't pass UAT-1. If Phase 2 runs long, the slip rule below applies; profiles are not cut to protect the date.

### 4.4 Consequences of the agentic decisions (D20–D22)

- **Amended ADRs.** ADR-003: the monthly narrative review runs as the Monthly Reviewer agent inside the GitHub job, not as a Claude scheduled task (the cloud task can't reach a local-only server). ADR-008: the Claude push lane is retired; the review goes to Telegram and email, and agents send only through `notify.queue`.
- **Scaffold.** *(Done in v1.14)* The rebuilt `stack_config.yaml` keeps LangGraph as the SCAIX default, but its `parakh` profile drops it and generates `mcp/toolsets` and `agents/runtime`, matching 04 §3.3. `ClaudeSDKRunner` and `FakeRunner` come from the Phase 0.5 spike, not the scaffold.
- **Time.** About **4–6 extra hours before M1** (MCP skeleton, audit middleware, read-only tools, SDK spike; estimate). Only read-only tools are in scope for M1, and M1 doesn't depend on MCP; if Phase 0 or 2 slips, the read toolsets move to Phase 3 (09 §5).
- **Production checklist.** Still 34 / 34. P2 is reworded above; P4 now also counts agent turn-limit stops; P5's load test includes agents through `FakeRunner`; P6's privacy rules extend to tool outputs (05 §4).
- **Unchanged.** The numbers firewall (NFR-02), human approval (D13, ADR-005), the notification channels other than the Claude push lane, and every other decision.

**Pre-agreed slip rule (09 §5):** if Phase 1 slips by more than a week, M1 moves to the next month-end and later milestones slide one month-end each (dates in 09). No scope is cut to protect the date.

---

## 5. The plan at a glance

Dates, phase contents and exit gates live only in **plan 09**. The Production items (P1–P10) show their phase in the §3 table, and the test gates per phase are in **plan 14 §9**.

---

## 6. Change control after the lock

| Change | How |
|---|---|
| New idea | Backlog item (F20+ or a GitHub Issue); considered at the next phase boundary. *(D25)* **Until the M1 review, backlog only, with no exceptions**; the backlog is reviewed right after UAT-1, using the D25 test |
| Change to a locked decision (D1–D25) | Changelog entry in §9 + version bump of the affected docs + an ADR if architectural |
| Weights, thresholds, prompts | PR only, with CI impact preview (plan 10 §8) |
| Date slip | The slip rule in §4.3; no silent scope cuts |

---

## 7. Document set at baseline

| Doc | Version | Doc | Version |
|---|---|---|---|
| 00 Master plan | 1.0 | 07 PRD | 1.3 |
| 01 Value | 0.4 | 08 Feature spec | 1.3 |
| 02 Momentum | 0.3 | 09 Rollout | 1.3 |
| 03 Automation & alerts | 0.8 | 10 Audit & governance | 0.8 |
| 04 Engineering | 0.8 | 11 Drishti review | 1.2 |
| 05 Storage & holdings | 0.7 | 12 UI/UX design | 1.1 |
| 06 Watchlist | 0.5 | **13 Baseline (this)** | **1.0** |

---

## 8. Week 1 (Phase 0)

**You:**
1. ✅ *Done 27 Sep:* the pilot list of 7 stocks (D3).
2. ✅ *Done 27 Sep:* latest CAS PDF (NSDL, Aug 2026) saved and `CAS_PASSWORD` set in `.env`; checked that the password opens the file. Location: D19.
3. ✅ *Done 27 Sep:* Screener export for **M&M** saved in `FILES FOR ANALYSIS`. Format confirmed: Data Sheet v2.1, consolidated figures, 10 years FY17–FY26, 10 quarters to Jun 2026, 10 year-end prices. The file name is `M & M.xlsx`, so the adapter maps files by the COMPANY NAME cell, not the file name.
4. ✅ *Done 27 Sep:* Telegram bot **@Parakh_avinash_bot** created, group adds disabled; `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`; a test message reached your chat.
5. ✅ *Done 27 Sep:* Supabase project `parakh` created.
6. ✅ *Done 4 Oct (**BL-01**; account created, root MFA on, $1 budget, region Mumbai):* confirm you have an **AWS account** for SSM (P1), or accept the GitHub-environment-secrets deviation. Not a Phase 0 blocker: SSM/OIDC is only needed in Phase 3, before M2 (§4.3). Target: close it by the end of Phase 0 (4 Oct).
7. ✅ *Done 27 Sep:* the original **`aiscaffold.py` + `stack_config.yaml`** weren't on your PC, so Claude rebuilt them (v1.0.0) in `Stock Analysis\Parakh-scaffold\`. The `parakh` profile follows §4.4: no LangGraph, tools under `mcp/toolsets` (D20), an `agents/runtime` package for the `AgentRunner` (D21). Every tier's generated project passes ruff, pyright, pytest and the 34-item check. Monday: `uv run aiscaffold.py new parakh --path C:\dev\parakh`.
8. ✅ *Done 27 Sep:* golden stocks confirmed: HDFCBANK, INDIGO, M&M (D18).
9. ✅ *Done 27 Sep:* **Docker Desktop** installed (Docker 29.8.0, Compose v5.5.1), for the local Supabase test stack (plan 14 §3). The engine wasn't running at the check, so start Docker Desktop before Monday's session; `docker run --rm hello-world` confirms it.
10. ✅ *Decided 27 Sep:* the CAS and `.env` stay in OneDrive (D19). On Monday, Claude points the code at them (`PARAKH_ENV_FILE`, `cas.inbox_dir`).
11. ✅ *Done 27 Sep:* git 2.55, uv 0.12.19 and Python 3.12.14 (installed through uv; no separate installer or `py` launcher needed). One follow-up: `C:\Users\atall\.local\bin` isn't on PATH yet; `uv python update-shell` adds it, and Monday's session checks it before installing pre-commit.
12. ✅ *Done 27 Sep:* private GitHub repo `atallam/parakh` created.

**Me, once you say go** *(go given 28 Sep 2026; Phase 0 started)*: run the scaffold at tier Production into `C:\dev\parakh` and set up:
- `pyproject` / `uv.lock`, ruff, pyright, pre-commit, gitleaks, pip-audit.
- `CLAUDE.md` / `AGENTS.md`, ADR files 001–012.
- *(v1.13)* The `parakh-mcp` skeleton (tool registry with IDs and tiers, audit middleware), `AgentRunner` + `FakeRunner`, `config/agents.yaml`, `.mcp.json` (plan 15).
- Config schemas, `ui_tokens.yaml`, `RunContext` + audit sink.
- A CI pipeline where `parakh --help` passes all gates.

```powershell
# Repo bootstrap (PowerShell)
New-Item -ItemType Directory -Path C:\dev -Force | Out-Null
Set-Location C:\dev
git clone https://github.com/atallam/parakh.git   # after creating the private repo on GitHub
Set-Location C:\dev\parakh
```

---

### 8.0 Phase 0 status *(29 Sep 2026)*

Built on branch `phase-0` in `atallam/Parakh`, **pull request #1**. All four CI jobs pass (L0 static, L1–L5 tests, L4 database on the Supabase local stack, L0 security); 128 tests; SCAIX checklist 34 / 34.

| Exit-gate item (09 Phase 0, 14 §9) | Status |
|---|---|
| `run.py --help`, config validates (7 pilot ISINs, ISO 6166 check digits) | ✅ |
| Dummy run emits one `AUD.RUN.START` + one `AUD.RUN.END` (hash-chained) and a manifest | ✅ |
| Redaction test (PAN, DP/client IDs, CDSL BO IDs, holdings quantities and ₹ fields) | ✅ |
| L0: ruff, pyright, token lint, layering lint (`app/`, `src/parakh/mcp/`), tool registry sweep, doc lint, catalogues fresh, gitleaks, pip-audit | ✅ |
| Harness: AC markers + traceability (16 due ACs covered), sockets blocked, LLM mock, `FakeRunner`, synthetic CAS | ✅ |
| Supabase migration + seed + 16 pgTAP checks (append-only audit, `parakh_mcp` has no UPDATE/DELETE, RLS everywhere, staging can't write public) | ✅ |
| ADR-001…012 in `docs/adr/` | ✅ |
| Pre-commit and CI green on `main`, branch protection | ⏳ You: merge PR #1 and set branch protection (below) |

**Differences from the plan text, all recorded here:** the MCP Python SDK is on version 2 (`MCPServer`, not `FastMCP`); the synthetic CAS is JSON for now (a rendered PDF follows spike ⑦ once casparser's real output is known); `docs/plan/` in the repo is now the canonical copy of these docs (04 §3.3), with the OneDrive FRAMEWORK folder and the Claude project as mirrors.

**You, to close Phase 0:**
1. Review and merge PR #1, then `git pull` in `Stock Analysis\parakh`, `uv sync`, `uv run pre-commit install`, `uv run pytest`.
2. Branch protection on `main`: require a PR, code-owner review, and the four checks *L0 static*, *L1–L5 tests*, *L4 database (Supabase local stack)*, *L0 security (P10)* (P10).
3. ✅ BL-01 (AWS account): done 4 Oct.

### 8.0b Phase 0.5 status *(29 Sep 2026)*

All eight spikes ran, on branch `phase-0.5` (pull request #2, stacked on #1). Outcomes are in `docs/spikes/` (one note each). Exit gate: every spike has a written outcome, recorded fixtures exist for every source tested, and **no blocker remains for Phase 1**.

| Spike | Outcome |
|---|---|
| ① NSE/BSE from a GitHub runner | ✅ Archives and announcement/corporate-action APIs work; **no self-hosted runner needed** (ADR-003 stands) |
| ② Concall transcripts (D7) | ✅ 7/7 pilots via Screener → BSE PDF; MAZDOCK's latest calls have no filed transcript, so it's flagged stale |
| ③ Screener export + XBRL | ✅ Export parser kept; XBRL revenue ties to Screener exactly. ⚠️ NSE's XBRL feed stops at Dec 2024 (SEBI integrated filing) → Phase 1 task |
| ④ Corporate actions | ✅ Adjustment and gap checks work. ⚠️ **A split changes the ISIN** (MAZDOCK) → `isin_history` table (plan 05 v0.13, ADR-004 amended) |
| ⑤ Supabase + Parquet + DuckDB | ✅ All 5 probes on the Supabase stack; the audit outbox now syncs |
| ⑥ Telegram adapter | ✅ Built and tested; live send from your PC delivered on 29 Sep |
| ⑦ CAS parse | ✅ casparser 1.4.1 on your real CAS, locally; synthetic CAS now matches its shape |
| ⑧ Claude Agent SDK | ✅ Installs, connects to `parakh-mcp` and completes a real agent turn on the runner; the server's allow-list refused a call the config didn't permit (AG-05 proven) |

**Carried into Phase 1 (within existing tasks, no new scope):** ISIN history in the security master; an adapter for SEBI integrated-filing results; a Screener ↔ XBRL line-item map before reconciling profits; `casparser` as a dependency; market cap from adjusted shares.

### 8.0c Phase 1 status *(2 Oct 2026)*

Built on branch `phase-1` (pull request #4) and loaded into Supabase for the 7 pilots. **Not closed:** the golden freeze is dated 30 Oct 2026 (plan 14 §4.1) and UAT-0 follows it.

| Exit-gate item | Status |
|---|---|
| Prices: 10 years or since listing, exchange cross-check | ✅ 7 pilots, 45 Parquet files, lineage and DQ recorded |
| Fundamentals with lineage and filing dates; XBRL tie-out | ✅ 7 pilots; latest 4 quarters tie to exchange filings |
| Shareholding and pledge | ✅ 46 quarterly patterns from NSE filings; promoter % ties to the exchange summary |
| AMFI categories and index membership | ✅ Config equals AMFI for all 7 |
| D24 profile inputs found in filings | ✅ INDIGO lease liabilities and rentals; MAZDOCK contract liabilities; M&M's 7 listed stakes |
| Holdings: CAS import, cost seed, lots | ✅ Reconciles on settlement date; re-import is idempotent |
| AC-F02.1–5, AC-F03.1/.2/.4/.6/.7 | ✅ Tests in place and green |
| Governance: source registry, DQ scorecard, audit sync, encrypted backup | ✅ Scorecard 96.1% over 102 checks; first backup verified |
| Golden inputs frozen | ⏳ On 30 Oct 2026. The golden folder holds the parsed facts and the hash of each Screener export, not the export itself (source terms) |
| UAT-0 signed | ⏳ After the freeze |

**Findings recorded in the code and config:** a CAS and a broker report reconcile only on settlement date (T+1); NSE has two results feeds (to Dec 2024, and integrated filings after); shareholding XBRL has two taxonomies and its percentages use the SCRR share base; balance-sheet "described lines" (lease liabilities, contract liabilities) appear only in the March 2026 filing so far.

**Changes to the plan (within D24, no new scope):**
- **MAZDOCK order book and the offer-document financials of GROWW, ATHERENERG and SHADOWFAX move from Phase 1 to the Phase 2 document work** (decided 2 Oct 2026). Neither is in any exchange feed; both are PDFs, read with the concall and filing documents.
- **Pilot cap mix by AMFI (list to 30 Jun 2026): 4 Large (HDFCBANK, M&M, INDIGO, GROWW), 1 Mid (MAZDOCK), 2 Small (ATHERENERG, SHADOWFAX).** ATHERENERG is rank 260 (Small), not Mid; SHADOWFAX (rank 589) is outside the Nifty Smallcap 250.

### 8.0d Phase 3 status *(4 Oct 2026)*

Built on branch `phase-3`. **Not closed:** shadow mode has not started; it begins when you add the workflow secrets, apply the `alerts_log` migration and switch the workflows on.

| Exit-gate item | Status |
|---|---|
| Workflows: monthly, daily watch, daily events, digest, heartbeat, bot poll, integrity | ✅ Written and validated; not yet run on GitHub |
| Notifications: Telegram, email with `.ics`, ntfy, owner-only bot, signed buttons | ✅ Tests green on recorded responses and doubles |
| Momentum watcher, event watcher, shadow and replay modes | ✅ Real NSE responses in fixtures; replay sends nothing |
| Market context (flows, breadth), thesis alerts, `notify.queue`, `data.get_document` | ✅ Flows and breadth show N/A until enough history exists |
| Monthly Reviewer and Event Triage agents, cards, inventory | ✅ Shadow mode on |
| Failure modes, run counts, SLO breach flag in the heartbeat | ✅ |
| AC-F11, F12, F13, F19 (1, 2, 3, 5, 7), F23.4, F24.8, F25 (2, 3, 4, 7) | ✅ Tests marked and traceability check clean |
| AC-F24.4 | ⏳ Phase 4, with the portfolio toolset |
| Shadow weeks, UAT-2, UAT-3, M2 | ⏳ After the workflows are on |

**Changes to the plan (within scope, no new features):**
- **`jobs.request_refresh` stays in Phase 4.** In Phase 3 the event rules queue the refresh (at most 5 a day) and Event Triage only suggests one.
- **`data.get_document` serves only filings the event watcher has saved**, not arbitrary documents.
- **Reviewer and Triage tool lists exclude the portfolio and data-quality tools** until those exist; positions reach agents only as the masked weight and P&L.
- **Thesis status changes to WATCH or BROKEN** send their own alert (High for BROKEN, Medium for WATCH) and a Home inbox item.

### 8.1 Prep backlog

Setup tasks that are pending but don't block the current phase. Feature ideas still go to F20+ (D25).

| ID | Item | Needed by | Status |
|---|---|---|---|
| ~~BL-01~~ | ~~AWS account for SSM Parameter Store via GitHub OIDC (P1, ADR-009)~~ | Phase 3, before M2 (2 Dec 2026) | ✅ Done 4 Oct (account, root MFA, $1 budget, ap-south-1). Next, yours: the three steps in `docs/AWS_SETUP.md` (role stack, parameters, two GitHub variables) before the workflows are switched on |
| ~~BL-02~~ | ~~`TELEGRAM_CHAT_ID` missing from `.env`~~ | Spike ⑥; Phase 3 | ✅ Done 29 Sep (read from the bot, written to `.env`) |
| ~~BL-03~~ | ~~`ANTHROPIC_API_KEY` in `.env` and as a repo secret~~ | Spike ⑧; Phase 3 agents | ✅ Done 29 Sep |
| ~~BL-04~~ | ~~`SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env`~~ | Phase 1 | ✅ Done 29 Sep (secret key; `.env` comment lines fixed) |
| BL-05 | **UAT-0:** review the oracle workbook (`Stock Analysis\ORACLE\golden_expected.xlsx`): formulas in words, a few cells per stock, the COMPARE sheet; then sign. About 45 minutes. Record: `docs/uat/UAT-0_2026-10-03.md`. Also open: INDIGO lease inputs, M&M SOTP inputs, bank asset-quality inputs, momentum and DMA oracle on the frozen 30 Oct prices | Before the golden freeze (30 Oct 2026) and UAT-1 | Open; owner decisions on F1–F3 made 3 Oct; reminder runs daily until signed |
| BL-06 | **UAT-1:** review the 7 pilot reports against the plan 14 §7.3 rubric (R1–R6), then the D25 backlog review. Up to 90 minutes. Record: `docs/uat/UAT-1_<date>.md`. Starts after BL-05 and the open Phase 2 inputs | M1 (8 Nov 2026) | Open; reminder runs daily until signed |

---

## 9. Changes since the baseline

| Version | Date | Change |
|---|---|---|
| 1.24 | 2026-10-04 | **BL-01 done.** AWS account ready. Added the OIDC role template (`infra/aws/`), the Parameter Store loader (path `/parakh/prod`, set by the job) and `docs/AWS_SETUP.md`. The workflow secrets that shadow mode waits for (§8.0d) are the parameters in that guide. Version: 13 1.24 |
| 1.23 | 2026-10-04 | **Phase 3 built (§8.0d).** Shadow mode waits for the workflow secrets and the `alerts_log` migration. `jobs.request_refresh` stays in Phase 4; F24.4 moves with the portfolio toolset. Version: 13 1.23 |
| 1.22 | 2026-10-04 | UAT-0 (oracle sign-off) and UAT-1 (pilot report review) added to the prep backlog as BL-05 and BL-06, with a daily reminder until both are signed. Version: 13 1.22 |
| 1.21 | 2026-10-02 | **Phase 1 built and loaded (§8.0c).** Order book (MAZDOCK) and offer-document financials (young listings) move to the Phase 2 document work. Pilot cap mix by AMFI is 4 Large, 1 Mid, 2 Small. Golden folder keeps parsed facts and export hashes, not the Screener exports |
| 1.20 | 2026-09-29 | All Phase 0.5 spikes closed: Telegram live send delivered; a real agent turn on the runner; BL-02, BL-03, BL-04 done. Version: 13 1.20 |
| 1.19 | 2026-09-29 | **Phase 0.5 spikes done** (§8.0b, `docs/spikes/`): no self-hosted runner needed; `isin_history` added (plan 05 v0.13); NSE XBRL feed ends Dec 2024; backlog BL-02…BL-04 for keys. Versions: 05 0.13, 13 1.19 |
| 1.18 | 2026-09-29 | **Phase 0 built** (§8.0): PR #1 with CI green, 34/34 checklist. `docs/plan/` in the repo becomes the canonical copy. Version: 13 1.18 |
| 1.17 | 2026-09-28 | **D10 amended:** the repo lives at `Stock Analysis\parakh` in OneDrive, venv outside OneDrive. **Phase 0 scaffold done:** Production tier, 80 files, 34/34 checklist; ruff, pyright and 46 tests green; `parakh --help` and `parakh doctor` work; the `.env` is found one folder up. Versions: 09 1.11, 13 1.17 |
| 1.16 | 2026-09-28 | Phase 0 started. Week-1 item 6 (AWS account) moved to the new §8.1 prep backlog as **BL-01**; it doesn't block Phase 0–2 because SSM/OIDC is a Phase 3 item. Version: 13 1.16 |
| 1.15 | 2026-09-28 | **Scope and correctness.** D23: Parakh stays a systematic engine; own forecasts, price targets and ratings are out; consensus and results context becomes backlog item F26; own forecasts for ≤ 5 holdings join F20. D24: pilot sector profiles (plan 01 §3) and limited-history rules (plan 01 §3.1, plan 02 §3.9) move into Phases 1–2 before M1; golden-set profiles updated (INDIGO airline, M&M SOTP); 9 new ACs (AC-F04.7–12, AC-F05.7–9). D25: scope freeze until the M1 review. Versions: 00 1.5, 01 0.6, 02 0.5, 07 1.9, 08 1.8, 09 1.10, 13 1.15, 14 1.6, README |
| 1.14 | 2026-09-27 | Item 7 done: scaffold rebuilt (aiscaffold.py 1.0.0 + stack_config.yaml); the `parakh` profile applies §4.4 (no LangGraph, `mcp/toolsets`, `agents/runtime`). §4.4 and 15 §6.3 updated. Folder renamed to `Stock Analysis\Parakh-scaffold\` at your request. Versions: 13 1.14, 15 1.1, README |
| 1.13 | 2026-09-27 | **Agentic, MCP-first.** New **plan 15** (principles AG-01…08, `parakh-mcp` toolsets and tiers, agent roster, `AgentRunner`, transport, ADR-010…012). Decisions **D20** (MCP-first; scoring stays code; agents propose only), **D21** (Claude Agent SDK) and **D22** (local stdio; revisit in Phase 5). ADR-003 and ADR-008 amended (Monthly Reviewer agent replaces the Claude scheduled-task push). P2 reworded; §4.4 added. New features **F24** (MCP server) and **F25** (agent roster); FR-26/27, NFR-15, G9, US-17/18, UX-14. The Phase 6 MCP item is now core. Versions: 00 1.4, 03 1.0, 04 1.0, 05 0.12, 06 0.7, 07 1.8, 08 1.7, 09 1.9, 10 1.0, 12 1.4, 13 1.13, 14 1.5, 15 1.0, README |
| 1.12 | 2026-09-27 | Item 4 done: Telegram bot live, chat ID saved, test message delivered. Version: 13 1.12 |
| 1.11 | 2026-09-27 | Item 9 done: Docker Desktop installed (start it before Monday). Version: 13 1.11 |
| 1.10 | 2026-09-27 | Item 11 done: uv 0.12.19 and Python 3.12.14 installed. Version: 13 1.10 |
| 1.9 | 2026-09-27 | Item 11: git confirmed; Python 3.12 now comes through uv (`uv python install 3.12`) instead of a separate installer. Version: 13 1.9 |
| 1.8 | 2026-09-27 | **Prep progress.** Week-1 items 3 (Screener export, format confirmed), 5 (Supabase) and 12 (GitHub repo) done; item 11 (tools) awaiting a check. Version: 13 1.8 |
| 1.7 | 2026-09-27 | **D19: private files stay in OneDrive** (your choice, risk accepted, guard rails listed). P6 and 05 §4 reworded to match; week-1 item 10 closed. §6 now points to §9 for the changelog (was 00 §11); 00 and 07 point to §2 without a D-range, so they can't go stale. Versions: 00 1.3, 05 0.11, 07 1.7, 13 1.7 |
| 1.6 | 2026-09-27 | **CAS saved.** Week-1 item 2 done (password verified). New item 10: move the CAS PDF and `.env` out of OneDrive. Items 11–12 (tools, private repo) added so §8 is the complete prep list. 05 §4 now names the local locations. Versions: 05 0.10, 13 1.6 |
| 1.5 | 2026-09-27 | **Golden stocks confirmed.** D18 = HDFCBANK, INDIGO, M&M (was proposed in 1.4). 14 §4.1 and §13 and the golden-test task in 09 Phase 2 now point to D18. Versions: 09 1.8, 13 1.5, 14 1.4 |
| 1.4 | 2026-09-27 | **Pilot list received.** D3 = 7 stocks (4 Large, 2 Mid, 1 Small per AMFI July 2026); D18 proposed as HDFCBANK, INDIGO, M&M. M1 review becomes ≥ 6 of 7 reports; pilot edge cases added to 14 §4.4 (young listings, HDFC merger, `&` in a symbol, cap re-classification). Versions: 09 1.7, 13 1.4, 14 1.3 |
| 1.3 | 2026-09-25 | **Readability pass.** README rewritten as a plain one-page summary (builder material kept in a folded section). Plan 08 gains a plain-English Part A and new feature **F23 Thesis tracking** (FR-25), plus ACs for email + calendar file, Telegram commands, portfolio XIRR/drawdown, Obsidian links, watcher replay, source check, doc lint and traceability; F20 gains ask-Claude, Gmail CAS fetch, WhatsApp mirror and the governance dashboard. The doc lint now also checks that the README and 08 Part A match 09. Versions: 07 1.6, 08 1.6, 09 1.6, 13 1.3, 14 1.2 |
| 1.2 | 2026-09-24 | **One-owner pass completed.** Dates and phase placement only in 09 (Phase columns removed from 08, 12, 13); numeric targets only in 07 (SLO table moved to NFR-14; ACs and gates cite NFR-07/NFR-14/PRD §5); doc lint added to Phase 0 and plan 14 L0. Versions: 00 1.2, 05 0.9, 07 1.5, 08 1.5, 09 1.5, 12 1.3, 13 1.2, 14 1.1 |
| 1.1 | 2026-09-24 | Docs restructured around `README.md` with one owner per fact (decisions → 13, dates → 09, tests → 14). **Plan 14: Test & UAT plan** added. Defaults **D17** (staging schema) and **D18** (golden stocks) added. Contradictions with D10/D11 fixed in 00, 03, 06 and 09 (audit tables and backups now in Phase 1). THESIS.md schema moved to 05 §2.4; plan 11 and 00 §2 archived. Versions: 00 1.1, 01 0.5, 02 0.4, 03 0.9, 04 0.9, 05 0.8, 06 0.6, 07 1.4, 08 1.4, 09 1.4, 10 0.9, 12 1.2, 13 1.1, 14 1.0, archive/11 1.3; new README |

*Personal analytical framework; not investment advice.*
