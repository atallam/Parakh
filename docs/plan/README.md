---
title: Parakh — on a page
date: 2026-09-28
status: Plan locked · build starts Mon 28 Sep 2026
---

# Parakh on a page

**Parakh** (परख, "to assay", the way a jeweller tests gold) is your personal system for judging NSE stocks. It's for your own use; not investment advice.

## What it does for you

- **A monthly report for every stock you follow.** Each gets a clear verdict (BUY, HOLD, REDUCE …, or ADD / TRIM / EXIT for stocks you own) and the reasons behind it.
- **Two separate views of each stock.** *Value* asks whether it's cheap and a good business. *Momentum* asks whether it's trending. They're never averaged into mush.
- **Alerts on Telegram only when something changes:** a breakout, a breakdown, a pledge, an auditor exit. No message means nothing changed.
- **It knows what you own** (from your CAS statement) **and why you own it** (a short thesis per stock), and tells you when that reason weakens.
- **A monthly "what changed" screen,** designed so your review takes about an hour.
- **New ideas surface on their own** through a self-curating watchlist, and nothing is added to *your* list without your approval.
- **AI helpers and "Ask Parakh".** AI agents do the first pass (a monthly "top 5" review, a line on why a new filing matters, reasoned watchlist ideas), and you can ask Claude on your PC about any stock. They read Parakh's numbers through one MCP server; they only suggest and never change a score or your lists.

## How it works

```
Market data + company financials + concall transcripts + your holdings
        ↓
   Value check      Momentum check      Concall reader (AI, quotes only)
        ↓                 ↓                    ↓
                One verdict, with reasons
        ↓
 Monthly report · Telegram alert · email archive · review app
        ↓                                  ↑
 AI helpers + Claude on your PC ── read through parakh-mcp, only suggest
        ↓
               You decide (it never trades)
```

## Timeline

| When | What you'll have |
|---|---|
| **Mon 28 Sep 2026** | Build starts (evenings and weekends, ~8–10 hrs/week) |
| **8 Nov 2026** · M1 | First reports on your 7 pilot stocks; you review them |
| **2 Dec 2026** · M2 | Runs by itself every month and every trading evening; alerts on Telegram |
| **2 Jan 2027** · M3 | Full stock universe, review app, watchlists, concall reading |
| **2 Feb 2027** · v1.0 | Three unattended months, calibrated and signed off |

## What you decided

- **Name:** Parakh, built to a production standard.
- **Stocks covered:** NSE Large, Mid and Nifty Smallcap 250.
- **Data:** company financials from your Screener.in export; concall transcripts from BSE filings.
- **Holdings:** read from your monthly CAS statement. Your PAN and account numbers are never stored.
- **Alerts and runs:** Telegram, plus an email archive; WhatsApp later only if needed. It runs on GitHub, so your laptop can be off. The code lives in `C:\dev\parakh`, and a readable copy of the reports lands in OneDrive.
- **Value hurdle:** a value BUY must be expected to beat **15% a year**.
- **Thesis breaks:** the AI can **flag** a broken thesis; only a measurable rule or you can mark it broken.
- **What Parakh is:** a systematic engine held to institutional rigour, not a broker note. No forecasts of its own, no price targets, no ratings; the right valuation method for each kind of company, and young listings shown honestly as "limited history".
- **Scope freeze:** from 28 Sep until the M1 review, new ideas go to the backlog only.
- **Agentic, MCP-first:** everything goes through one MCP server; agents run on the Claude Agent SDK and only propose; the server stays on your PC and in the scheduled jobs for now (revisited before v1.0).

## What you do

- **This weekend** (full checklist: 13 §8):
  - ✅ Tools installed; GitHub repo, Supabase project and Telegram bot created.
  - ✅ CAS statement and a Screener export (M&M) saved.
  - ✅ Pilot stocks picked (7) and test stocks confirmed (HDFCBANK, INDIGO, M&M).
  - ✅ Scaffold tool ready (`Stock Analysis\Parakh-scaffold`). Still to do: tell Claude whether you have an AWS account.
- **Monday evening:** about 2 hours with Claude to set up the project.
- **At each milestone:** a review session of at most 90 minutes. Claude brings the checklist.
- **Once live:** about 1 hour a month in the review screen, plus a glance at alerts.

## The only docs you need

| Doc | Why |
|---|---|
| **This page** | The whole picture |
| **08 Part A** | Every feature in plain English |
| **13** | Your decisions, if you want the detail |
| **09** | The detailed timeline |

Everything else is the builder's reference. Claude reads it and brings you the relevant part when a choice needs you.

---

<details>
<summary><b>For the builder (you can skip this)</b></summary>

### Reading paths

| You want to… | Read |
|---|---|
| Know what the product must do | **07** (PRD) → **08** (features: Part A plain, Part B acceptance criteria) |
| Build or use an agent or MCP tool | **15** → **08** F24/F25 → **10 §7** (governance) |
| Build feature F*xx* | **08** F*xx* → the plan doc named in its row → **14** for how it's tested |
| Review before a milestone | **14 §7** (UAT session and rubric) |
| Change a decision, weight or date | **13 §6** (change control) |

### Doc map: each fact has one owner

If a fact appears anywhere else, it's a link or an ID (e.g. "within NFR-07", "see 09"), not a restated value. **Edit it only in its owner.**

Derived copies are allowed only where the doc lint checks them against their owner: this page's timeline and 08 Part A's "First visible" column are both checked against 09. From Phase 0, the lint fails CI if milestone dates or phase-placement tables appear anywhere else, apart from the test gates in 14 §9 (plan 14 L0).

| Doc | Role | Owns (single source of truth for) |
|---|---|---|
| **README** | Entry point | The one-page summary, doc map, precedence rule |
| **13** Plan baseline | Decision log | **All decisions** (D1–D25), Production items P1–P10, change control, **the post-baseline changelog** (§9) |
| **09** Rollout | Delivery plan | **Dates, phases, milestones, exit gates, which features and Production items land in which phase** |
| **07** PRD | Requirements | Goals, user stories, FR/NFR, release criteria, **every numeric target** (NFR-07, NFR-14 service levels, §5 success metrics) |
| **08** Feature spec | Requirements detail | Part A: the plain-English feature list. Part B: features **F01–F26** and their **179 acceptance criteria** |
| **14** Test & UAT | Verification | **Test levels, environments, oracles, traceability, UAT sessions, defect severities** |
| **04** Engineering | Architecture | **ADR index (ADR-001…012)**, repo layout, code standards, lens plug-in contract |
| **00** Master plan | Overview design | Architecture, decision matrix, **data sources** (§7), **report template** (§8), folder layout (§4) |
| **01** Value · **02** Momentum | Method design | Metrics, weights, thresholds, signals, vetoes |
| **03** Automation & alerts | Method design | Jobs, schedules (times of day), watchers, **notification channels and routing** (ADR-008) |
| **05** Storage & holdings | Method design | Coverage tiers, holdings and CAS flow, **THESIS.md schema** (§2.4), data model |
| **06** Watchlist | Method design | Two-list rules, approvals |
| **10** Audit & governance | Method design | Audit events, lineage, LLM, model and data governance |
| **12** UI/UX | Method design | UX principles, design tokens, components, screens, Telegram UX |
| **15** Agentic & MCP | Method design | Agent principles (AG-), the `parakh-mcp` toolsets and permission tiers, agent roster, `AgentRunner`, transport, **ADR-010…012** full text |
| **archive/** | History | The v0.1 brief review and the Drishti review. Read-only |

### When two docs disagree

**13 → ADRs (index in 04) → 07/08 → 14 → topic docs (01–06, 10, 12, 15) → 00 → archive.** The higher one wins. Fix the lower one in the same change, and log it in 13 §9.

### Where the plan lives over time

| Period | Canonical copy | Copies |
|---|---|---|
| Until Phase 0 | OneDrive `Stock Analysis/FRAMEWORK/` | The claude.ai project "Stock Analysis" (kept in sync) |
| From Phase 0 | The repo, `C:\dev\parakh\docs\plan\` (changes by PR) | OneDrive FRAMEWORK/ and the claude.ai project become published copies |

### For Claude Code (and other AI assistants)

`CLAUDE.md` in the repo points here, and `.mcp.json` connects Claude Code to `parakh-mcp`, which also serves these docs as `parakh://plan/…` resources. Load **this page + the owner doc for the task**, not the whole set: roughly 45,000 words is too much context. Follow the precedence rule above.

### ID conventions

`D`/`P` decisions and Production items (13) · `F`/`AC-F` features and acceptance criteria (08) · `ADR-` (04) · `M`/`E` signals and events (02, 03) · `RULE.`/`MET.`/`LENS.` (04) · `AUD.` audit events (10) · `UX-`/`UI.` (12) · `AG-`/`TOOL.`/`AGENT.` (15) · `T-`/`UAT-`/`L0–L8`/`S1–S4` (14) · `SRC.`/`RM.`/`FLAG.` watchlist rules (06)

</details>
