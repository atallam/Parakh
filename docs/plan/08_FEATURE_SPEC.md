---
title: Feature Specification — Parakh
version: 1.8 (F04/F05 ACs for sector profiles and limited history; new backlog F26 consensus & results context; F20 adds own forecasts for ≤ 5 holdings — plan 13 D23/D24; v1.7: agentic, MCP-first: new F24 MCP server and F25 agent roster; F06/F07 run on the Claude Agent SDK through MCP tools; F11 narrative review by the Monthly Reviewer agent; F20 ask-Claude item replaced by remote MCP access — plan 15; v1.6: Part A plain-English overview; new F23 Thesis tracking; ACs for email + .ics, Telegram commands, portfolio XIRR/drawdown, Obsidian links, watcher replay, source check, doc lint, traceability; F20 later items; v1.5: Phase column removed from the catalogue — phases live in 09; ACs cite NFR-07/NFR-14 instead of restating numbers; v1.4: every AC traceable to tests or UAT steps — plan 14 §5; v1.3: baseline: CAS holdings, BSE-filed transcripts, thesis-aware agent, Production criteria in F19/F21 — plan 13; v1.2: F22 design system added; UI/UX criteria in F09, F11, F15, F17 — plan 12; v1.1: F21 audit, logging & governance)
date: 2026-09-24
parent: 07_PRD.md
rollout: 09_PHASED_ROLLOUT_PLAN.md
conventions: Feature IDs F01–F26 · acceptance criteria AC-Fxx.n · priorities MoSCoW · plan refs point to FRAMEWORK/00–14 · every AC is tagged in tests (`@pytest.mark.ac`) or UAT steps and tracked in the generated `docs/TRACEABILITY.md` (plan 14 §5)
---

# Feature Specification

This document lists **everything Parakh will do**.
- **Part A** is the plain-English overview. Read this part.
- **Part B** is the detailed specification with acceptance criteria, used for building and testing.

## Part A — Parakh's features in plain English

**When you'll first see each feature:**
- **Foundation:** built in the first weeks; you won't see it directly.
- **M1:** the first reports on your pilot stocks.
- **M2:** Parakh runs by itself and sends alerts.
- **M3:** the review app, watchlists and concall reading.
- **v1.0:** calibrated and signed off.
- **Later:** optional, after v1.0.

Dates are in the timeline (plan 09). A check in the build keeps this column in step with it.

### 1. Analysing stocks

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Value check** | Scores how cheap and how good a business is: price vs its own history and its sector, quality, debt, growth, governance. Gives a fair-value range and says whether it beats your 15% hurdle | M1 | F04 |
| **Momentum check** | Scores how strongly a stock is trending against the right index for its size, and spots breakouts and breakdowns | M1 | F05 |
| **Verdict** | Combines the two into one call (STRONG BUY … AVOID) with the top reasons, without flip-flopping near a threshold. For stocks you own it speaks in actions: ADD / HOLD / TRIM / EXIT | M1 | F08 |
| **Market mood** | Tags each segment Risk-On / Neutral / Risk-Off from valuations, volatility and fund flows, and gets stricter when the market is stretched | M1 → M2 | F16 |
| **Concall reader** | Reads each quarter's earnings-call transcript filed on BSE, checks it against your thesis and quotes management word for word. It never changes a score | M3 | F06 |
| **Devil's advocate** | For every BUY or SELL, argues the opposite case in three points | M3 | F07 |
| **AI helpers** ✨ | Agents that do the first pass for you: a monthly "top 5 things to look at" review, a one-line "why it matters" on new filings, and reasoned watchlist ideas. They only suggest; nothing changes without your approval | M2 → M3 | F25 |

### 2. Your portfolio

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Holdings** | Knows what you own from your CAS statement; tracks cost, profit and days until long-term tax status; asks you to fill in any trade it can't price | M1 → M3 | F03 |
| **Thesis tracking** ✨ | Keeps your "why I own this" for each stock and tells you when it's weakening or broken. Only a measurable condition or your confirmation can mark it broken | M1 → M3 | F23 |
| **Portfolio view** | Your holdings first; sector concentration; your returns (XIRR) vs the right index; worst drawdown | M1 → M3 | F10 |

### 3. Staying informed

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Monthly run and summary** | Runs by itself on the 2nd of each month and sends one Telegram summary. An email keeps the monthly archive, with a calendar file of upcoming results | M2 | F11 |
| **Daily momentum watch** | Every trading evening; messages you only when a signal genuinely changes (confirmed, not repeated) | M2 | F12 |
| **Daily event watch** | New results, promoter buying or selling, pledges, auditor or CFO exits, rating changes, surveillance lists | M2 | F13 |
| **Phone actions** ✨ | Tap to mark an alert useful or noise, mute it, or approve and reject suggestions; quick commands such as `/today` and `/stock POLYCAB` | M2 → M3 | F11 |

### 4. Finding new ideas

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Stock universe** | Every stock in each size segment (Large, Mid, Nifty Smallcap 250), kept current as AMFI reclassifies twice a year | M1 → M3 | F01 |
| **Segment ranking** | A ranked list of every stock in a segment, with the best ideas you don't yet own | M1 → M3 | F10 |
| **Watchlists** | Your own list (changes only with your approval) plus a system list that curates itself, with limits and minimum stays so it doesn't churn | M3 | F14 |

### 5. Reviewing and acting

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Stock reports** | One report per stock per month: a one-line summary, the verdict and why, an action box, charts and history. Also a **shareable version** that hides your holdings and adds the disclaimer | M1 | F09 |
| **Review app** ✨ | Home shows only what changed since your last review; approve suggestions, edit holdings and theses, open any stock | M3 | F15 |
| **Ask Parakh** ✨ | Ask Claude on your PC about your stocks in plain words ("why did HDFCBANK move to HOLD?", "what needs my attention?") and get answers from Parakh's own numbers | M1 → M3 | F24 |
| **Look and feel** ✨ | The same colours, words and icons everywhere; privacy mode hides amounts; "couldn't check" is never shown as "all clear" | Foundation → M3 | F22 |

### 6. Trust and safety (behind the scenes)

| Feature | What it does for you | First visible | ID |
|---|---|---|---|
| **Data collection** | Several sources with fallbacks, cross-checked; every number is stamped with its source and date | M1 | F02 |
| **Reliability** | Run logs, failure alerts, a Sunday "all healthy" message, service levels, a load test, and a weekly check that data sources haven't changed | Foundation → M2 | F19 |
| **Audit trail** | Records every decision and change; explains any verdict back to its source numbers; replays any past run; keeps secrets and personal data out of logs | Foundation → v1.0 | F21 |
| **Learning loop** | Checks whether scores and alerts actually worked, tracks how useful the alerts were, and keeps a decision journal | v1.0 | F17 |
| **Add-a-style kit** | Lets new investing styles plug in later without rework | Foundation | F18 |

### 7. Later (optional, after v1.0)

- Ask questions across quarters of concall transcripts.
- Ask Parakh from your phone or claude.ai, not just your PC (remote access; reviewed before v1.0).
- **Consensus and results context** (F26, decided at the M1 review): forward P/E on analysts' consensus, a results-day note vs consensus, a sensitivity grid on what's priced in, and a "key debate" box you confirm.
- Your own earnings forecasts for up to 5 holdings, only if you find you miss them after 3 live months.
- Animated dashboards, and a phone-friendly app behind a login.
- Fetch the CAS statement from Gmail automatically.
- A WhatsApp mirror of the Telegram alerts (only if needed).
- More investing styles: Quality, Dividend, Magic Formula, CAN SLIM and others.
- US stocks.

(F20.)

### Added during planning (✨ above, all now in Part B)

- CAS-based holdings with "complete this trade".
- **Thesis tracking** (F23).
- The **review app** Home screen.
- **Phone actions** and commands, plus the email archive with a calendar file.
- **Privacy mode and share export**, and "couldn't check" shown honestly.
- **Portfolio returns and drawdown** (ported from Drishti), and the concall reader using BSE-filed transcripts.
- The **source check**, **replay mode** for the watcher, the **doc lint** and the **traceability** check.
- *(v1.7)* **Ask Parakh** (F24) and the **AI helpers** (F25), from the agentic, MCP-first design (plan 15).
- **Later:** remote access to Ask Parakh, Gmail CAS fetch and the WhatsApp mirror.

---

## Part B — Detailed specification (for building and testing)

## Feature catalogue

Which phase builds each feature lives in **plan 09** (the Features row of each phase).

| ID | Feature | Priority | Depends on | Plan ref |
|---|---|---|---|---|
| F01 | Universe and cap classification | Must | F02 | 00 §4, 05 §1 |
| F02 | Multi-source data ingestion and validation | Must | — | 00 §7, 04 §4 |
| F03 | Holdings management (lots, P&L, tax timing) | Must | F02 | 05 §2, §4 |
| F04 | Value lens | Must | F02, F18 | 01 |
| F05 | Momentum lens | Must | F02, F18 | 02 |
| F06 | Qualitative agent (BSE-filed transcripts, thesis-aware, exact-quote citations) | Should | F02, F24 | 01 §6, 05 §2.4, 15 §5, archive/11 §3 |
| F07 | Devil's-advocate agent | Could | F06, F08, F24 | 04 §2, 15 §5 |
| F08 | Verdict policy engine | Must | F04, F05 | 00 §5 |
| F09 | Per-stock report, snapshot and history | Must | F08 | 00 §3, §8 |
| F10 | Segment summary and ranking | Must | F09, F03 | 05 §1 |
| F11 | Monthly scheduler and notifications (incl. two-way Telegram, ADR-008) | Must | F09, F10, F22 | 03 §2–4, 12 §6 |
| F12 | Daily momentum watcher | Must | F05 | 03 §5 |
| F13 | Daily event watcher | Should | F02 | 03 §5b |
| F14 | Watchlist auto-curation (two lists) | Should | F10, F12, F13 | 06 |
| F15 | Streamlit app (review inbox, watchlist review, holdings + thesis form, stock detail, dashboard) | Should | F03, F14, F22 | 04 §5 ADR-006, 12 |
| F16 | Market context and regime | Should | F02 | 00 §2b, 02 §5 |
| F17 | Calibration, scorecards and decision journal | Should | F09, F12, F14 | 04 §2, 06 §6 |
| F18 | Lens plug-in framework | Must | — | 04 §1 |
| F19 | Observability and reliability | Must | — | 03 §7, 04 §4 |
| F21 | Audit, logging and governance layer | Must (core) / Should (reviews, UI) | F19 | 10 |
| F22 | Design system and cross-surface presentation | Must (tokens, tri-state, masking) / Should (components, share export) | F09, F11, F15 | 12 |
| F23 | Thesis tracking *(v1.6)* | Must (thesis file, metric exit checks, status) / Should (concall assessments, heatmap) | F03, F06, F09 | 05 §2.4, 01 §6, 12 §5.3 |
| F24 | MCP server `parakh-mcp` *(v1.7)* | Must (read toolsets, audit, masking) / Should (propose, notify, jobs) | F09, F21 | 15 §4, §7, §8 |
| F25 | Agent roster and runtime *(v1.7)* | Should | F24, F11, F13, F14 | 15 §5, §6 |
| F26 | Consensus and results context *(v1.8, backlog)* | Could (decided at the M1 review) | F02, F09 | 00 §1 (D23) |
| F20 | Future: concall Q&A (RAG), remote MCP access, animated pages, new lenses, own forecasts (≤ 5 holdings) | Won't (v1) | F06, F15, F18, F24 | 05 §3.3, ADR-006, ADR-012 |

---

## F01: Universe and cap classification

**What:** builds the analysis universe per cap from AMFI rankings and index constituents, and tracks cap migrations.

**Behaviour**
- Large = AMFI 1–100, Mid = 101–250, Small = Nifty Smallcap 250 (default) or extended AMFI 251–1000 with a liquidity filter.
- Loads the semi-annual AMFI list (January/July) and point-in-time index membership.
- On migration: moves the folder, keeps history, logs a `cap_migration` event.

**Acceptance criteria**
- AC-F01.1: `run.py --cap mid` loads exactly the stocks classified Mid for the as-of date.
- AC-F01.2: A stock reclassified Mid → Large appears under `large_cap/` with its complete prior history and a migration note in HISTORY.md.
- AC-F01.3: Universe membership is reproducible for any past date (point-in-time).
- AC-F01.4: Securities are keyed by ISIN; symbol changes don't break history.

---

## F02: Multi-source data ingestion and validation

**What:** adapters for prices, fundamentals, filings, concalls and macro data, with fallbacks, reconciliation and trust tiers.

**Behaviour**
- One adapter per source returns **pandera-validated** frames; each value carries `source`, `tier` and `asof`.
- Primary → fallback order is set per data type (plan 00 §7 table).
- Cross-source checks (e.g. close price within 1%); conflicts are recorded in `data_quality`.
- Corporate actions applied (adjusted prices); fundamentals stored bitemporally (`period_end`, `reported_on`).
- Caching, throttling and retry with backoff; the terms-of-use note per source is respected.

**Acceptance criteria**
- AC-F02.1: If the primary price source fails, the fallback is used and the snapshot records it.
- AC-F02.2: A split or bonus doesn't create an artificial price drop in DMA or return series (tested on a known split).
- AC-F02.3: Scoring for as-of date D only sees fundamentals with `reported_on ≤ D`.
- AC-F02.4: Failed validation (e.g. negative price, a missing trading date) marks that stock's confidence Low with a warning; it isn't silently scored.
- AC-F02.5: Re-running the same day is served from the cache (no duplicate downloads).

---

## F03: Holdings management

**What:** records what you own at tax-lot level and feeds ownership context everywhere.

**Behaviour**
- Input *(locked, plan 13 D8)*: **CAS statement (NSDL/CDSL) as the quantity source of truth**, a one-time **cost-basis seed** (broker tradebook / tax P&L export, or CLI), and the CLI (`holdings add/sell/list/import`) for trades between statements; Streamlit editor from F15.
- Each new CAS is reconciled against stored lots; a quantity change creates a "complete this trade" prompt, and P&L shows **cost pending** until it's completed.
- Lots: ISIN, account, quantity, price, date, tags, target weight, thesis link. Sales are recorded as transactions and matched first-in, first-out.
- Derived: total quantity, average cost, market value, unrealised/realised P&L, weight, days to long-term status per lot, tax estimate if sold now (rates in config).
- Stored in Supabase with RLS from **Phase 1** (plan 13 D11); local files encrypted (sops/age). PAN, names, addresses and DP/client IDs from CAS are never stored (P6).

**Acceptance criteria**
- AC-F03.1: Importing a CAS yields, for every ISIN, a total quantity equal to the statement's; after the cost-basis seed, average cost matches the broker's figures.
- AC-F03.2: A partial sale reduces the oldest lots first and records realised P&L.
- AC-F03.3: Each owned stock's report shows 🟢 OWNED, quantity, P&L, weight and "LTCG in N days".
- AC-F03.4: The plaintext holdings file is never committed (pre-commit check).
- AC-F03.5: Owned stocks are always Tier A (deep dive).
- AC-F03.6 *(v1.3)*: A quantity change between two CAS statements creates exactly one "complete this trade" prompt; until it's completed, P&L and the LTCG timer show "cost pending", never a guessed cost.
- AC-F03.7 *(v1.3)*: With a synthetic CAS, no PAN, name, address or DP/client ID appears in the database, logs, audit events or any LLM input (redaction test).

---

## F04: Value lens

**What:** scores 0–100 on valuation, quality, balance sheet, growth and governance, plus an intrinsic-value range, MoS, vetoes and archetype.

**Behaviour:** as specified in plan 01, including:
- Sector profiles (banks, NBFCs, cyclicals and so on) and Lynch-style archetypes; *(v1.8)* airline/lease-heavy, conglomerate (SOTP), order-book, capital-market intermediary and new-age/pre-profit profiles, and history classes H0–H2 (plan 01 §3).
- Relative P/E (own history, sector), PEG on 3-year EPS CAGR with N/A rules.
- Reverse DCF, expected IRR vs the hurdle rate.
- Value-trap detector, veto list.
- DMAs used **only** in the Entry-Timing Overlay.

**Acceptance criteria**
- AC-F04.1: A bank is scored on P/B, ROA, NIM and NPA metrics, not EV/EBITDA or D/E.
- AC-F04.2: PEG shows N/A when 3-year EPS CAGR ≤ 0% or > 50%.
- AC-F04.3: Any veto (e.g. pledge above the cap limit) forces the value view to AVOID/SELL, whatever the score.
- AC-F04.4: The value score is unaffected by price vs 50/200 DMA (overlay only).
- AC-F04.5: Golden tests (1 bank, 1 cyclical, 1 compounder) reproduce the expected scores within ±0.5.
- AC-F04.6: Each metric in the snapshot lists its source and as-of date.
- AC-F04.7 *(v1.8)*: Each pilot stock is scored under the profile in plan 01 §3.2, and its snapshot records the profile and history class.
- AC-F04.8 *(v1.8)*: A metric without its minimum history shows ❔ N/A with the reason (e.g. "listed 11 months; needs 36"), is never scored as zero, and its weight re-normalises within the sub-score.
- AC-F04.9 *(v1.8)*: For an H0 or pre-profit stock, the value lens is marked informational, the verdict policy uses the Fair value row, confidence is Low, the report shows "limited history", and vetoes still apply.
- AC-F04.10 *(v1.8)*: INDIGO's leverage is lease-adjusted net debt ÷ EBITDAR, and it isn't failed on raw D/E.
- AC-F04.11 *(v1.8)*: M&M's intrinsic value includes an SOTP line: listed stakes at market value × stake %, less the configured holdco discount; its balance-sheet sub-score uses the standalone core business.
- AC-F04.12 *(v1.8)*: For a pre-profit company, "negative CFO in 3 of 5 years" is a flag while cash runway ≥ 24 months and a veto below it.

---

## F05: Momentum lens

**What:** scores 0–100 on RS vs cap and sector benchmarks, volatility-adjusted momentum, trend structure, 52-week-high proximity, volume/participation and earnings momentum; runs the signal catalogue M01–M30.

**Behaviour:** as specified in plan 02, including:
- Golden and Death Cross treated as confirmation signals.
- Trend Template (x/8), Weinstein stage.
- Dual momentum, residual momentum, rank buffer.
- Circuit-trap and surveillance vetoes.
- Regime filter per segment.

**Acceptance criteria**
- AC-F05.1: A mid-cap stock's RS is measured against Nifty Midcap 150 and its sector index.
- AC-F05.2: 12-1 momentum excludes the most recent month.
- AC-F05.3: In a Risk-Off regime, no momentum view exceeds WATCH.
- AC-F05.4: M27 (circuit trap) blocks a momentum BUY.
- AC-F05.5: Indicator values match a reference library (pandas-ta) within tolerance on test data.
- AC-F05.6: Each fired signal is recorded with its date, price and confirmation status.
- AC-F05.7 *(v1.8)*: The first 20 sessions after listing are excluded from volatility, 52-week high/low and base detection.
- AC-F05.8 *(v1.8)*: Each measure below its minimum sessions (plan 02 §3.9) shows ❔ N/A with its reason; 200-DMA signals (M06, M10, M11, M21, M24) never fire before the minimum; since-listing highs are labelled as such.
- AC-F05.9 *(v1.8)*: With fewer than 126 sessions, the momentum lens is informational and the verdict comes from vetoes only (WATCH at best); from 126 to 251 sessions, confidence is capped at Med and the Trend Template shows x/y.

---

## F06: Qualitative agent

**What:** `AGENT.qualitative`, a Claude Agent SDK agent (through `AgentRunner`, plan 15 §6) that reads documents only through `parakh-mcp` tools, producing a 1–5 scorecard (moat, management, concall tone, industry, event risk), a guidance record and a thesis-drift note.

**Behaviour**
- Sources *(locked, plan 13 D7)*: **BSE-filed transcript PDFs found via Screener's Concalls list** (extraction and validation ported from Drishti), annual reports, investor presentations, news; manual upload as fallback; concall.in optional.
- *(v1.3, D13)* **Thesis-aware:** when THESIS.md is structured, the agent assesses each key metric and exit condition. It **can only flag** (`FLAG.thesis_review`); BROKEN needs a metric-based breaker or your confirmation.
- Output is Pydantic-validated; every rating cites a source or reads "insufficient evidence".
- Guidance is stored as structured records for guidance-vs-delivery tracking; a QoQ tone diff is produced.
- Runs only for Tier A; outputs are cached by document hash; there's a token budget per run.
- A new transcript triggers an event-driven refresh (F13).

**Acceptance criteria**
- AC-F06.1: No qualitative output changes a numeric lens score; it only adjusts confidence (±1 level).
- AC-F06.2: A guidance number not found in the filed transcript is shown with ⚠️ "unverified".
- AC-F06.3: Re-running on unchanged documents makes zero new LLM calls (cache hit).
- AC-F06.4: The run stops cleanly when the token budget is reached, marking the remaining stocks "qualitative pending".
- AC-F06.5: Each LLM call is traced (agent, tokens, latency, success).
- AC-F06.6 *(v1.3)*: With a structured thesis, the output has exactly one assessment per key metric and per exit condition; an LLM-detected break never sets BROKEN on its own.
- AC-F06.7 *(v1.3)*: If the transcript route fails, the run records the failing stage and reason and offers manual upload; the stock is never silently skipped.
- AC-F06.8 *(v1.3, P4)*: A run with Pydantic validation failures > 10% of calls, any budget stop, any suspected injection, or unverified citations > 20% sends a Telegram ⚠️.
- AC-F06.10 *(v1.7)*: The agent's runtime options list only its allow-listed `mcp__parakh__*` tools; document text reaches it only as `untrusted_content`; a thesis break arrives as a `proposals` row (`FLAG.thesis_review`), never as a status change.
- AC-F06.9 *(v1.3, P3)*: Reverting a prompt pin in `config/prompts.yaml` restores that version's cached outputs with zero new LLM calls and emits `AUD.PROMPT.ROLLED_BACK`.

---

## F07: Devil's-advocate agent

**What:** for each BUY/SELL (or ADD/EXIT) verdict, argues the opposite case from the same evidence.

**Acceptance criteria**
- AC-F07.1: Every BUY/SELL report contains exactly 3 counter-points, each with a citation or metric reference.
- AC-F07.2: The agent can't change the verdict; its output is shown in the report and summary only.
- AC-F07.3: Runs only for verdict changes or new Tier A entries (cost control).
- AC-F07.4 *(v1.7)*: The agent has read-only (R-tier) MCP tools only; any other call is refused and logged `AUD.MCP.TOOL_DENIED`.

---

## F08: Verdict policy engine

**What:** combines lens results through the YAML decision matrix, with vetoes, hysteresis, regime caps, confidence and ownership-aware wording.

**Acceptance criteria**
- AC-F08.1: Value ≥ 70 and Momentum ≥ 70 with no veto gives STRONG BUY (not owned) / ADD (owned).
- AC-F08.2: A score moving within ±5 of a threshold doesn't flip the verdict (hysteresis).
- AC-F08.3: Adding a new lens with no policy row shows it as "informational" without changing verdicts.
- AC-F08.4: Each verdict change lists its top 3 drivers (score attribution).
- AC-F08.5: The policy is fully config-driven; a change bumps the framework version.

---

## F09: Per-stock report, snapshot and history

**What:** each run writes a canonical JSON snapshot, then renders the report (MD, template in plan 00 §8), appends to `history.csv` and regenerates `HISTORY.md`. It never touches `THESIS.md`.

**Acceptance criteria**
- AC-F09.1: The report contains every section of the template (TL;DR through Methodology), with "N/A" when a section has no data.
- AC-F09.2: Re-running a month overwrites that month's snapshot and history row without duplicating (idempotent).
- AC-F09.3: HISTORY.md shows ≥ 12 months of trend tables once available, plus auto trend flags.
- AC-F09.4: THESIS.md is never modified by the pipeline (test asserts file hash unchanged).
- AC-F09.5: Every snapshot includes the framework version, lens versions, config hash and run_id.
- AC-F09.6 *(v1.2)*: The report opens with TL;DR, verdict chip (prev → now), "What changed since last month" (≤ 4 bullets) and the action box; sections 4–15 are inside `<details>` blocks (plan 12 §7).
- AC-F09.7 *(v1.2)*: A check that couldn't run renders as ❔ UNKNOWN with the reason and last attempt, never as clean (UX-05).
- AC-F09.8 *(v1.2)*: `run.py share <SYMBOL>` produces a Markdown + PNG view with no quantity, ₹ value, ₹ P&L, sizing rationale or personal notes, and with the personal-use disclaimer (redaction test).
- AC-F09.9 *(v1.3, D13)*: THESIS.md front matter validates against the schema in plan 05 §2.4; the `original` block can't change after the first save (pre-commit hook).

---

## F10: Segment summary and ranking

**What:** a per-cap monthly summary: your holdings first, best opportunities not owned, the full ranked universe (also CSV/XLSX), regime and breadth, watchlist changes, red flags and a portfolio view.

**Acceptance criteria**
- AC-F10.1: The holdings section lists every owned stock in the cap with its action flags (e.g. "owned but SELL-rated").
- AC-F10.2: The ranked table includes every stock in the universe (Tier B included).
- AC-F10.3: Sector concentration and single-stock weight breaches are flagged against config limits.
- AC-F10.4: The CSV/XLSX export opens and sorts correctly in Excel.
- AC-F10.5 *(v1.6)*: The portfolio view shows XIRR per holding and overall against the cap-matched benchmark, maximum drawdown, and concentration (HHI and top-5 weight). The XIRR maths ported from Drishti is covered by unit tests against a hand-computed case.
- AC-F10.6 *(v1.6)*: Stocks in the segment summary are linked as `[[SYMBOL]]`, so Obsidian backlinks work across the report folder.

---

## F11: Monthly scheduler and notifications

**What:** a GitHub Actions monthly workflow (2nd of the month, 09:30 IST), a Telegram completion summary, failure alerts, and *(v1.7)* the narrative review by the Monthly Reviewer agent (F25). *(v1.2)* It also owns the notification layer for every job: the `Notifier` interface, channel adapters, routing per ADR-008 (plan 03 §4) and two-way Telegram actions.

**Acceptance criteria**
- AC-F11.1: The run uses the last trading day of the previous month as its as-of date.
- AC-F11.2: Exactly one completion message per run, with upgrades, downgrades, red flags, signals, watchlist review count and data warnings.
- AC-F11.3: Any failed step sends a ❌ message with the step name and error within the NFR-14 failure-alert time.
- AC-F11.4: The manual trigger (`workflow_dispatch`) produces an identical result for the same as-of date.
- AC-F11.5: Reports are published into the OneDrive cap folders (per the repo-location decision).
- AC-F11.6 *(v1.2)*: Every Telegram message is ≤ 10 lines, uses the plan 12 §3.2 vocabulary (emoji + word) and ends each item with an *Open ▸* link.
- AC-F11.7 *(v1.2)*: With the default `notify.include_amounts: false`, no quantity or ₹ amount appears in any notification (redaction test).
- AC-F11.8 *(v1.2)*: A button tap (useful / noise / mute / approve / reject / snooze) produces exactly one audit event with `channel=telegram`, applied by the next processing cycle (Phase 3) or within 1 minute (Phase 4 listener).
- AC-F11.9 *(v1.2)*: Messages from any chat other than the owner's are ignored and logged `AUD.ACCESS.BOT_REJECTED`; expired or tampered button tokens are rejected.
- AC-F11.10 *(v1.2)*: The heartbeat and Low-only digests are sent silently; 🔴 High alerts on owned stocks also go to the ntfy lane when it's enabled.
- AC-F11.11 *(v1.6)*: After each monthly run, one email arrives with the HTML segment summaries, links to the reports, and an `.ics` calendar file of the next 30 days' results dates, board meetings and ex-dates for owned and watchlist stocks.
- AC-F11.12 *(v1.6)*: The Telegram commands `/today`, `/stock <SYMBOL>`, `/pending`, `/status`, `/mute <1d>` and `/privacy on|off` answer only the owner, read from the latest snapshot, and are audited as `AUD.BOT.COMMAND`.

---

## F12: Daily momentum watcher

**What:** an end-of-day job (18:30 IST, trading days) recomputing momentum states and alerting only on confirmed transitions.

**Acceptance criteria**
- AC-F12.1: No message on days without a state change.
- AC-F12.2: A signal needing 2-close confirmation isn't sent on day 1.
- AC-F12.3: The same signal for the same stock isn't re-sent within the cool-down (10 trading days) unless it reverses.
- AC-F12.4: Exit and warning signals on owned stocks are sent immediately; entry signals on non-owned stocks go to the digest (unless High severity and top 10%).
- AC-F12.5: The job exits quietly on NSE holidays.
- AC-F12.6: It can run in **shadow mode** (logs only) via config.
- AC-F12.7 *(v1.6)*: **Replay mode** runs the watcher over the last N trading days from stored data, sends nothing, and outputs the alerts it *would* have sent, with dates (used in UAT-2, plan 14 §4.5).

---

## F13: Daily event watcher

**What:** a 19:00 IST job scanning exchange filings and rating actions: results/concall availability, insider trades, pledges, auditor/KMP exits, ratings, ASM/GSM, index inclusion, bulk/block deals, lock-in expiries.

**Acceptance criteria**
- AC-F13.1: Each filing triggers at most one alert (`events_seen` de-duplication).
- AC-F13.2: A new results/concall filing re-runs value + qualitative for that stock only, and sends a results digest.
- AC-F13.3: An auditor resignation on an owned stock is alerted 🔴 immediately and re-evaluates vetoes.
- AC-F13.4: Events are appended to the stock's history and signal log.

---

## F14: Watchlist auto-curation (two lists)

**What:** My Watchlist (approval-only) + System Watchlist (automatic, capacity-limited), with four add sources, removal rules, flags, promotions, urgent adds, suggestion expiry and an archive. Full detail in plan 06.

**Acceptance criteria**
- AC-F14.1: **Invariant:** no My Watchlist entry is ever removed without an approved suggestion.
- AC-F14.2: System Watchlist size never exceeds the capacity per cap.
- AC-F14.3: A System entry isn't removed before its minimum stay (2 cycles), except for a veto.
- AC-F14.4: A new candidate enters a full list only if it beats the weakest entry by ≥ 10 points.
- AC-F14.5: At most 3 urgent adds per cap per week.
- AC-F14.6: Pending suggestions expire after 30 days.
- AC-F14.7: Removed entries remain tracked in the archive for the scorecard.

---

## F15: Streamlit app

**What:** a local-first Streamlit app with pages Home (**review inbox**), Watchlist Review, Holdings (with the thesis form), Segment Dashboard, Stock Detail and Audit & Governance. It calls the service layer only (ADR-006) and is built from the plan 12 component library.

**Acceptance criteria**
- AC-F15.1: Approve, Reject and Snooze on a suggestion update the store and appear in the audit log.
- AC-F15.2: Adding a stock to My Watchlist requires a reason; ISIN lookup by name or symbol works.
- AC-F15.3: The holdings editor validates quantity > 0, price > 0, date ≤ today and a valid ISIN.
- AC-F15.4: Common pages load within the NFR-07 target (cached).
- AC-F15.5: The `app/` code doesn't import `analytics/`, `lenses/` or `adapters/` (lint check).
- AC-F15.6: It isn't reachable publicly; hosted mode requires login.
- AC-F15.7: At least one animated Plotly chart (e.g. an animated sector-rotation chart) on the Segment Dashboard (Phase 6).
- AC-F15.8 *(v1.2)*: Home lists every item since the last "Mark all reviewed", owned 🔴 first; marking items reviewed is audited (`AUD.REVIEW.MARKED`) and yields the review-time metric.
- AC-F15.9 *(v1.2)*: Adding a holding or approving a My Watchlist add opens the thesis form (4 fields, ≤ 5 metrics, ≤ 5 breakers); the original thesis can't be edited after the first save; skipping is allowed and counted in one Home banner.
- AC-F15.10 *(v1.2)*: Stock Detail shows sections in the plan 12 §5.2 order; the card, the detail page and Telegram show the same verdict for the same run (contract test).
- AC-F15.11 *(v1.2)*: With network access disabled, every page renders from fixtures (no network or LLM calls during render).
- AC-F15.12 *(v1.2)*: A Streamlit `AppTest` smoke test renders every page and every section from fixtures in CI.
- AC-F15.13 *(v1.2)*: The privacy toggle masks quantities, ₹ values and ₹ P&L on every page.

---

## F16: Market context and regime

**What:** a segment-level context layer (Nifty valuation bands, India VIX, FII/DII flows, breadth, A/D line, G-sec yield) feeding the regime tag, momentum caps and the value MoS uplift.

**Acceptance criteria**
- AC-F16.1: The regime is computed per segment (Large, Mid, Small), not only for Nifty 50.
- AC-F16.2: A market in its top valuation decile raises the required MoS by 5 percentage points.
- AC-F16.3: A VIX spike rule downgrades the regime one level.
- AC-F16.4: Regime history is shown in the segment summary.

---

## F17: Calibration, scorecards and decision journal

**What:**
- Price-only momentum backtest (point-in-time constituents, after costs and tax), walk-forward.
- Signal-outcome tracker (forward 1M/3M returns per signal).
- Score-quintile calibration.
- Watchlist scorecard.
- Decision journal with review reminders.

**Acceptance criteria**
- AC-F17.1: The backtest uses only constituents valid on each rebalance date (no survivorship).
- AC-F17.2: Backtest results report gross, after-cost and after-tax returns.
- AC-F17.3: The quarterly calibration report shows the forward-return spread of top vs bottom score quintiles per lens.
- AC-F17.4: Journal entries due for review appear in the monthly summary.
- AC-F17.5 *(v1.2)*: 👍/👎 feedback from Telegram and Streamlit is stored per alert and reported as alert precision per signal ID in the quarterly calibration report.

---

## F18: Lens plug-in framework

**What:** `Lens` base class, `LensResult` contract, lens and metric registries, `run.py new-lens <name>` scaffolding (5 files), contract tests, per-lens versioning and re-scoring.

**Acceptance criteria**
- AC-F18.1: `new-lens dividend` generates the lens, config, template partial, test and plan stub; the lens runs as "informational" without further wiring.
- AC-F18.2: Contract tests run automatically for every registered lens (score range, metric IDs exist, handles missing data, speed).
- AC-F18.3: `rescore --lens value --from 2026-01` recomputes history with the current lens version and records it.
- AC-F18.4: `docs/METRICS.md`, `SIGNALS.md` and `RULES.md` are regenerated in CI and fail the build if stale.

---

## F19: Observability and reliability

**What:**
- `runs` table and structlog with fixed keys; Langfuse LLM tracing.
- Failure alerts and a Sunday heartbeat.
- Holiday calendar; idempotency; token and runtime budgets.

**Acceptance criteria**
- AC-F19.1: Each run writes a summary (timings, counts, failures, token usage).
- AC-F19.2: The heartbeat reports the job success count for the week.
- AC-F19.3: Searching logs for a signal or rule ID (e.g. `M03`) returns every occurrence with run_id and ISIN.
- AC-F19.4: F19 covers *operational* observability; durable audit, lineage and governance are in **F21** (plan 10).
- AC-F19.5 *(v1.3, P8)*: The NFR-14 service levels (plan 07) are measured in every run manifest and reported in the Sunday heartbeat; a breach is flagged ⚠️.
- AC-F19.6 *(v1.3, P5)*: Before the Phase 4 scale-up, a full-universe dry run with mocked LLM at the configured concurrency completes within the NFR-07 run-time target with no unhandled rate-limit errors; an Anthropic 429 or overload leads to backoff and then "qualitative pending".
- AC-F19.7 *(v1.3, P7)*: `docs/FAILURE_MODES.md` exists before M2, and each entry names its detection, impact, mitigation and owner action.
- AC-F19.8 *(v1.6)*: A weekly **source check** in STAGING fetches each live source page, compares its structure with the recorded fixture, and raises ⚠️ on a change before a monthly run depends on it (plan 14 §4.2).

---

## F21: Audit, logging and governance layer

**What:** end-to-end auditability and governance (plan 10). It has four sub-layers (operational logs, step ledger + run manifests, append-only hash-chained audit trail, lineage/explainability), plus LLM governance, model governance, data governance, retention and review cadence.

**Behaviour**
- `RunContext` carries run_id, as-of date, code SHA, config hash and actor through every step; `audited_step` wraps every pipeline step.
- `audit.emit` records every state change and decision (`AUD.*` taxonomy), including **suppressed alerts** and **human actions** (approvals, holdings edits, thesis changes, overrides).
- Writes go through a JSONL outbox, then Postgres (append-only via trigger + RLS), with a hash chain and a daily git anchor.
- `run.py explain <symbol> --run <id>` shows the lineage from verdict to lens to metric to source value to raw input hash; `run.py replay <run_id>` reproduces a run.
- Prompt registry with an eval gate; model inventory and cards; PR-only config changes with a CI impact preview; overrides with a reason and expiry.
- A governance line in the monthly message; quarterly review template; Streamlit Audit & Governance page.

**Acceptance criteria**
- AC-F21.1: Every run has exactly one `AUD.RUN.START` and one terminal event (`END` / `ABORT`); the completeness test fails CI otherwise.
- AC-F21.2: Every service method that changes state emits an audit event with actor, before, after and reason (test sweep over the service layer).
- AC-F21.3: `UPDATE`/`DELETE` on `audit_events` is rejected by the database; corrections are new events referencing the original.
- AC-F21.4: Tampering with any audit record is detected by the daily integrity check and alerted ❌.
- AC-F21.5: With Supabase unreachable, no audit event is lost; the run ends `SUCCESS_AUDIT_PENDING` and the next job flushes the outbox.
- AC-F21.6: Every alert decision is logged in `alerts_log`, including suppressed ones with the reason (dedupe / cool-down / dry-run / digest / quiet hours).
- AC-F21.7: `explain` returns a complete lineage tree (policy rule, lens versions, metric IDs, source, as-of, raw hash, LLM citations) for any verdict in the last 24 months.
- AC-F21.8: `replay` of a past run reproduces all deterministic outputs (hash match); the monthly CI replay job is green.
- AC-F21.9: A prompt/model version can't be used in production without a passing eval result attached to `AUD.PROMPT.PROMOTED`.
- AC-F21.10: Config/weight/policy changes merged to main only via PR with green required checks; each produces `AUD.CONFIG.CHANGED` with the PR reference and a re-score diff.
- AC-F21.11: The log-redaction test proves secrets, account IDs and holdings quantities never appear in logs.
- AC-F21.12: Overrides require a reason and expiry and are listed in every monthly summary until they expire.
- AC-F21.13 *(v1.3, P1, P10)*: Scheduled runs read secrets from AWS SSM via OIDC and no long-lived cloud key is stored in GitHub (ADR-009); gitleaks and pip-audit are required checks on `main`.
- AC-F21.14 *(v1.6)*: The **doc lint** fails CI if milestone dates or phase-placement tables appear outside plan 09 (except the test gates in 14 §9), or if the README and Part A of this spec disagree with 09. Derived copies are allowed only when this check keeps them in step.
- AC-F21.15 *(v1.6)*: CI generates `docs/TRACEABILITY.md`, and a Must acceptance criterion with no test or UAT step fails the build from its feature's phase (plan 14 §5).

---

## F22: Design system and cross-surface presentation *(v1.2)*

**What:** one visual and verbal language for reports, Telegram, email and Streamlit (plan 12). It adopts Drishti's locked palette and component set (archived plan 11 §5), plus the fixes for Drishti's UX issues.

**Behaviour**
- `config/ui_tokens.yaml` is the only source of colours, icons and words; `src/render/format.py` formats ₹ (en-IN, L/Cr), %, pp, multiples and dates for every surface.
- Status vocabulary: 8 verdicts for non-owned stocks; ADD / HOLD / TRIM / EXIT for owned stocks (final mapping owned by the verdict policy, F08); thesis, concall, check and severity statuses.
- `app/ui/components.py` provides the `UI.*` components (plan 12 §4); reports and Telegram use the same tokens through their own renderers.
- Tri-state checks everywhere; privacy masking by default in notifications and share exports.

**Acceptance criteria**
- AC-F22.1: No hex colour appears outside `ui_tokens.yaml` (lint in CI).
- AC-F22.2: Every status on every surface is shown as colour + icon + word; a colour-blind simulation of the Component Gallery keeps every status distinguishable.
- AC-F22.3: The same status maps to the same token in the report, Telegram and Streamlit (snapshot tests over one fixture).
- AC-F22.4: The dev-only Component Gallery renders every `UI.*` component from fixtures without error (part of the AppTest suite).
- AC-F22.5: ₹ and number formatting is identical across surfaces for the same value (shared-formatter unit tests, including lakh/crore boundaries).

---

## F23: Thesis tracking *(v1.6)*

**What:** a structured "why I own this" for each stock (schema in plan 05 §2.4), with a status Parakh keeps current: **INTACT / WATCH / BROKEN / NOT SET**. It has a timeline of every change and a heatmap by quarter. It consolidates the thesis rules decided in plan 13 D13; the UI form is in F15 and the concall assessment in F06.

**Behaviour**
- THESIS.md lives in the repo and is written only by you, by hand or through the Streamlit form. The pipeline reads it and never writes it (AC-F09.4). The front matter is validated (AC-F09.9).
- **Metric exit conditions** (`check: metric`) are evaluated in Python on every run. When one is met, the status becomes BROKEN.
- **Concall evidence** (F06): a STRESSED metric sets WATCH and raises `FLAG.thesis_review`. An AI-detected exit condition sets WATCH and raises a 🔴 review item with the verbatim quote. **BROKEN only follows your confirmation**, recorded as an override with a reason.
- Every status change emits `AUD.THESIS.*` with the previous status, the new status, the source and the evidence. The timeline and heatmap are built from these events.
- The status feeds:
  - The report's Thesis check (§10 of the template).
  - Owned-stock wording (BROKEN leads to an EXIT suggestion).
  - The watchlist flag `FLAG.thesis_broken` (plan 06).
  - The Home inbox and Telegram.

**Acceptance criteria**
- AC-F23.1: A metric exit condition that is met sets BROKEN in the same run, with the metric value and rule as evidence.
- AC-F23.2: An AI-detected break never sets BROKEN on its own. It sets WATCH plus a review item with the exact quote, and BROKEN follows only your confirmation (audited).
- AC-F23.3: Every status change writes exactly one `AUD.THESIS` event, and the report's Thesis check and the Stock Detail timeline show the latest changes.
- AC-F23.4: A status change on an owned stock produces one Telegram alert (🟡 WATCH or 🔴 BROKEN) and one Home inbox item.
- AC-F23.5: A stock without a thesis shows NOT SET, is counted in a single Home banner, and still gets a verdict.
- AC-F23.6: The thesis heatmap shows each key metric's status for the last 4 quarters, built from audit history.
- AC-F23.7: When a thesis passes its `review_by` date, a "thesis review due" item appears in the Home inbox and the monthly summary.

---

## F24: MCP server `parakh-mcp` *(v1.7)*

**What:** one MCP server over the service layer (ADR-010), with namespaced toolsets (`reports`, `analytics`, `data`, `portfolio`, `notify`, `jobs`, `audit`), `parakh://` resources and prompts (`/monthly-review`, `/explain`, `/deep-dive`, `/thesis-check`). It's the only way agents reach Parakh, and you use it from Claude Desktop and Claude Code. Local stdio only (ADR-012). Design in plan 15 §4.

**Acceptance criteria**
- AC-F24.1: Every tool has a `TOOL.` ID, a permission tier (R/P/N/J), MCP annotations and Pydantic input and output models; `docs/TOOLS.md` is generated in CI; registering a tool without a tier or ID fails the build.
- AC-F24.2: For the golden stocks (D18), `reports.get_stock` and `analytics.explain_verdict` return exactly the values of the CLI and Streamlit view models for the same run (equivalence test, AG-04).
- AC-F24.3: No tool approves or rejects anything, edits holdings or theses, deletes, publishes or changes config (registry sweep test, AG-03).
- AC-F24.4: `portfolio.positions` never returns quantities, costs or ₹ values to an agent client; `detail: true` from an agent is refused and logged `AUD.MCP.TOOL_DENIED`.
- AC-F24.5: Every call writes exactly one `AUD.MCP.TOOL_CALL` (tool, tier, client, hashes, latency); the `parakh_mcp` database role can't `UPDATE` or `DELETE` any table (RLS test).
- AC-F24.6: The server never opens a listening network socket (test), and starts from Claude Desktop and Claude Code through the documented config.
- AC-F24.7: `data.get_document` returns document text only inside `untrusted_content`, with source URL and SHA-256.
- AC-F24.8: `notify.queue` applies ADR-008 routing, de-duplication, cool-downs and masking: queuing the same stock and event twice inside the cool-down sends one message and logs one `AUD.ALERT.SUPPRESSED`; a severity above the rule table's value is capped.
- AC-F24.9: Read tools meet the NFR-15 latency target on the pilot universe.
- AC-F24.10: In a UAT step, `/monthly-review` in Claude Desktop answers from the latest snapshot, and `/explain <SYMBOL>` matches `parakh explain`.

---

## F25: Agent roster and runtime *(v1.7)*

**What:** the agents of plan 15 §5 on the Claude Agent SDK behind the `AgentRunner` interface (ADR-011): Monthly Reviewer, Event Triage and Watchlist Curator, plus F06 and F07 running the same way. Every agent has an allow-list of MCP tools, a pinned model and prompt, `max_turns`, a token budget and a Pydantic output model.

**Acceptance criteria**
- AC-F25.1: Each agent's runtime options contain only its allow-listed `mcp__parakh__*` tools, no built-in SDK tools, and a non-bypass permission mode (contract test over `config/agents.yaml`).
- AC-F25.2: Reaching `max_turns` or the token budget ends the run as `pending` with `AUD.AGENT.TURN_LIMIT` or `AUD.LLM.BUDGET_STOP`, and counts toward the P4 LLM-failure alert.
- AC-F25.3: The Monthly Reviewer sends one Telegram message (≤ 10 lines, plan 12 §6) and one section in the monthly email, mentioning only stocks returned by `reports.what_changed`; if it fails, the monthly summary still goes out and says "review pending".
- AC-F25.4: Event Triage never raises a severity above the E-code rule, never suppresses a rule-based alert, and makes at most 5 `jobs.request_refresh` calls a day.
- AC-F25.5: Watchlist Curator proposals appear in Pending review marked 🤖 with a reason and evidence, respect capacity, minimum-stay and expiry rules (plan 06), and never change My Watchlist without your approval.
- AC-F25.6: CI runs agents only through `FakeRunner` with sockets blocked; a prompt or model change passes the L7 trajectory eval (plan 14) before promotion.
- AC-F25.7: Every agent has an agent card (`docs/agents/`) and a `model_inventory` row, and every run writes `AUD.AGENT.START` and `AUD.AGENT.END`.

---

## F26: Consensus and results context *(v1.8, backlog, plan 13 D23)*

**What:** the institutional-quality context that fits a systematic engine, without Parakh forecasting anything itself:
- **Forward P/E and EV/EBITDA on consensus** FY+1 and FY+2 estimates (T2 source, e.g. Trendlyne), with the number of analysts; **N/A below 3 analysts** (common for small caps).
- **Results-day note:** actual vs consensus and vs the last four quarters' run-rate, with the beat or miss split into revenue, margin and other income; attached to the event refresh (F13).
- **Sensitivity grid** on the reverse DCF: implied growth for a range of prices and costs of equity.
- **Key-debate block:** "the debate · the market's view · what the data says · what would change it", drafted by the qualitative agent and shown only after you confirm it (UX-14).

**Status:** backlog. Considered at the M1 review (UAT-1); if accepted, plan 09 places it and acceptance criteria are written then. **Out of scope in any case:** own forecasts, price targets, ratings (D23).

---

## F20: Future (v2+, not in v1 scope)

- **Concall Q&A agent:** pgvector over transcripts, with cited answers across quarters.
- **Animated pages:** FastAPI over the services + React/Framer Motion (ADR-006 revisit triggers).
- **New lenses:** Quality/Coffee-Can, Magic Formula, Dividend, CAN SLIM, Turnaround, Special Situations.
- **Hosted UI:** phone access behind a login.
- **US equities adapter.**
- *(v1.7)* **Remote MCP access:** Ask Parakh from the phone or claude.ai over Streamable HTTP + OAuth with a masked, read-only toolset, only if the ADR-012 review before v1.0 chooses it. *(The local MCP server itself is now F24.)*
- *(v1.8, D23)* **Own forecast models** for at most 5 high-conviction holdings: driver-based, your assumptions in YAML, the LLM only drafts assumptions for you to accept. Only if you find you miss them after 3 live months.
- *(v1.6)* **Gmail CAS fetch:** save the monthly CAS email attachment automatically.
- *(v1.6)* **WhatsApp mirror:** only if an ADR-008 revisit trigger fires (plan 03 §4.4).
- *(v1.6)* **Full Audit & Governance dashboard:** timeline, lineage viewer, search.
