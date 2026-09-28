---
title: Parakh — Master Plan (Stock Analysis Framework)
version: 1.5 (§1 scope boundary: a systematic engine, not a sell-side research product; §5 limited-history rule — plan 13 D23/D24; v1.4: §7 architecture is MCP-first: agents reach Parakh only through parakh-mcp, plan 15; v1.3: decision pointer drops the D-range; v1.2: changelog continues in 13 §9; v1.1: docs restructured: README index, one owner per fact, plan 14 test & UAT plan; §2 review archived; §4 fixed to D10; §9/§10 now pointers; v1.0: baseline locked)
date: 2026-09-24
owner: Avinash Tallam
scope: Indian equities (NSE), monthly per-stock reports + daily momentum watch
usage: Personal analysis only — not investment advice, not for commercial distribution
companion_docs:
  - 01_VALUE_INVESTING_PLAN.md
  - 02_MOMENTUM_INVESTING_PLAN.md
  - 03_AUTOMATION_AND_ALERTS_PLAN.md
  - 04_ENGINEERING_AND_EXTENSIBILITY.md
  - 05_STORAGE_UNIVERSE_AND_HOLDINGS.md
  - 06_WATCHLIST_MANAGEMENT.md
  - 07_PRD.md
  - 08_FEATURE_SPEC.md
  - 09_PHASED_ROLLOUT_PLAN.md
  - 10_AUDIT_LOGGING_GOVERNANCE.md
  - 12_UI_UX_DESIGN.md
  - 13_PLAN_BASELINE_V1.md
  - 14_TEST_AND_UAT_PLAN.md
  - 15_AGENTIC_AND_MCP_ARCHITECTURE.md
  - README.md (start here)
  - archive/ (history: 00_BRIEF_REVIEW_v0.1.md, 11_DRISHTI_REUSE_AND_UX.md)
---

# Parakh: Master Plan

> **Start with `README.md`.** It has the doc map, the reading paths and the rule for resolving conflicts. This plan is the overview design; decisions live in **plan 13**, dates in **plan 09**, tests in **plan 14**.

## 1. What we are building

A Python pipeline that runs **once a month** over a watchlist split by market cap (Large / Mid / Small), and for each stock:

1. Pulls price and fundamental data from **multiple sources**, with fallbacks.
2. Scores the stock on **two independent lenses**: Value (plan 01) and Momentum (plan 02).
3. Adds a **qualitative layer** (management, moat, concall tone, news) written by an LLM, with a citation for every claim.
4. Combines the lenses through a **decision matrix** (not an average) into a verdict: STRONG BUY / BUY / ACCUMULATE / HOLD / WATCH / REDUCE / SELL / AVOID.
5. Appends the snapshot to the stock's **history**, so trends can be compared month over month, quarter over quarter and year over year.
6. Writes a readable monthly report and sends **one notification** when the run finishes.

A separate, lightweight **daily end-of-day watcher** checks momentum state changes (such as a golden cross, a breakout or a 200 DMA breakdown) and alerts only when a state changes (plan 03).

**Agentic, MCP-first (plan 15).** Everything Parakh knows and can do is exposed through one MCP server, `parakh-mcp`. AI agents (Claude Agent SDK) use only those tools to review, read filings, argue the other side, triage events and propose watchlist or thesis changes. They never compute a score and never change your state directly. You can use the same tools from Claude Desktop or Claude Code: "why did HDFCBANK move to HOLD?".

**What Parakh is, and isn't (D23).** Parakh is a **systematic engine**: the same rules applied to observable data for every stock, month after month. It holds itself to institutional rigour (the right valuation framework for each sector, sourced numbers, honest unknowns), but it **does not produce sell-side research products**: no forecasts of its own, no 12-month price targets, no Overweight/Underweight ratings. Its "what's priced in" answer is the reverse DCF and the expected return against your 15% hurdle (plan 01 §2.6, §11). Consensus-based context is a backlog item (F26), and your own forecast models for a few holdings are a post-v1.0 option (F20).

You pick the cap segment at run time:

```powershell
python run.py --mode monthly --cap mid
python run.py --mode monthly --cap all
python run.py --mode watch   --cap small
```

---

## 2. Design rationale and usage boundary

The v0.1 review of your original brief is archived in `archive/00_BRIEF_REVIEW_v0.1.md`. It covers eight corrections, all now built into plans 01, 02 and §5:
- DMAs out of the value score.
- Relative (not absolute) P/E.
- PEG rules.
- Crosses treated as confirmation, not triggers.
- Cap-matched benchmarks.
- A daily watcher.
- A 2-D decision matrix instead of averaging.
- Graded verdicts with hysteresis.

**Regulatory note (India):** keeping this for personal use is fine. If you later *publish* stock-specific buy/sell calls (for example on LinkedIn), SEBI's Research Analyst regulations may apply. Get that checked before any public or commercial use.

---

## 2b. Cross-cutting layers added in the v0.2 gap review

Neither investing style covered these, but both need them:

| Layer | What it adds | Why it matters |
|---|---|---|
| **Market context** (segment level) | Nifty P/E and P/B vs 10-year bands, market-cap-to-GDP, India VIX, daily FII/DII net flows, 10-year G-sec yield, USD/INR, crude, RBI policy stance | A cheap stock in an expensive market carries market risk; momentum breaks down when VIX spikes and FIIs sell. Feeds the **regime tag** and a **market-level margin-of-safety** note |
| **Event and catalyst calendar** (per stock) | Next results date, board meetings, ex-dividend and record dates, AGM, buyback or QIP windows, index rebalancing dates (Nifty semi-annual, MSCI quarterly), IPO lock-in expiries, F&O ban list | Avoid acting days before results. Index inclusions and lock-in expiries drive large, predictable flows |
| **Position context** (per stock) | Held or not, quantity, average cost, unrealised P&L, portfolio weight, holding days, **days until long-term capital-gains status**, tax impact of selling now | A SELL on a stock that turns long-term in 3 weeks is a different decision. Source (locked, D8): CAS statement (NSDL/CDSL) plus a one-time cost-basis seed |
| **Earnings-revision momentum** | Results surprise vs consensus and vs the company's own run-rate, direction of analyst estimate revisions, guidance raised or cut (from BSE-filed concall transcripts, D7) | "Fundamental momentum" is one of the most reliable signals and links the two styles. It lives in plan 02 §3.8 and is fed by plan 01 |
| **Peer set** | 3–5 listed peers per stock (in `watchlist.yaml`, with an auto-suggested default from the sector) | Makes "vs sector" meaningful. Both lenses print a peer table |
| **Methodology versioning** | `framework_version` and a weights hash stored in every snapshot; re-scoring of history when weights change | Without it, a score change could come from a change to the rules rather than the stock, and the time series would silently break |
| **Audit, logging and governance** *(v0.6)* | run_id correlation on every record; step ledger + run manifests + replay; append-only hash-chained audit trail of every decision, alert (incl. suppressed) and human/system change; verdict lineage (`explain`); LLM, model and data governance; retention and review cadence | You can explain, reproduce and trust every verdict and change. See **plan 10** |

---

## 3. File format recommendation

**Short answer: use a hybrid.** Store the numbers in JSON and CSV, and generate Markdown from them for reading. Markdown alone makes a poor database, and JSON alone makes a poor report.

| Format | Strength | Weakness | Role here |
|---|---|---|---|
| **Markdown (+ YAML front matter)** | Readable, diff-friendly, works in OneDrive/VS Code/Obsidian, and ideal input for an LLM qualitative pass | Parsing numbers back out of prose tables is fragile | **Monthly report** and **HISTORY.md** trend view (generated, never hand-edited) |
| **JSON (Pydantic-validated)** | Exact, typed, versioned schema, easy for code and agents | Unpleasant to read for review | **Canonical monthly snapshot**, the source of truth |
| **CSV** | Opens in Excel, easy time-series and charting | Flat, with no nesting | **history.csv**: one row per month of key metrics, for trend analysis |
| Parquet + DuckDB → Supabase Postgres | Fast at scale; SQL across all stocks; holdings; signals | Needs a DB layer | **v0.3: the storage backbone** (from Phase 1). Full review in **plan 05 §3**; the md/json/csv files above become *rendered outputs* |

Principle: **one run writes JSON first; everything else is rendered from it.** You never have two sources of truth.

### Per-stock files

| File | Written by | Purpose |
|---|---|---|
| `snapshots/YYYY-MM.json` | Pipeline | Full canonical snapshot: every metric, score, signal and data-source stamp |
| `history.csv` | Pipeline (append) | Flat time series of about 40 key metrics for trend comparison |
| `reports/YYYY-MM.md` | Pipeline | Human report for that month |
| `HISTORY.md` | Pipeline (regenerated) | Rolling trend tables (last 12 or 24 months), score trajectory, verdict changes and trend flags |
| `THESIS.md` | **You** (the pipeline never overwrites it) | Your investment thesis, notes and overrides; the LLM reads it as context |

---

## 4. Folder structure (where things live)

Locked in plan 13 (D10): **the repo is the source of truth; OneDrive gets a published, read-only copy.**

```
C:\dev\parakh\  (git repo — full layout in plan 04 §3.3)
├── src/  app/  config/  tests/  docs/        ← code, configuration, tests, plans (docs/plan/ from Phase 0)
├── data/  state/                             ← caches and watcher state (git-ignored)
├── large_cap/                                ← generated outputs + your THESIS.md files
│   ├── _SEGMENT_SUMMARY/2026-09.md           ← cap-level dashboard (ranked table, regime, changes)
│   └── HDFCBANK/
│       ├── THESIS.md                         ← yours (edit here or via the Streamlit thesis form; plan 05 §2.4)
│       ├── HISTORY.md
│       ├── history.csv
│       ├── snapshots/2026-09.json
│       └── reports/2026-09.md
├── mid_cap/   (same layout)
└── small_cap/ (same layout)

OneDrive\…\Stock Analysis\  (published copy for reading on any device)
├── FRAMEWORK/        ← plan docs (canonical until Phase 0; a published copy afterwards)
├── large_cap/  mid_cap/  small_cap/          ← copied from the repo after each run
```

Edit THESIS.md only in the repo (or through the Streamlit form). **Edits made in the OneDrive copy are overwritten** at the next publish.

### Classifying stocks by cap

- Use **SEBI/AMFI** definitions: Large = ranks 1–100 by full market cap, Mid = 101–250, Small = 251 and below. AMFI republishes the list **every six months** (January and July).
- Each run checks the latest AMFI list. If a stock **migrates** (for example Mid → Large), the pipeline moves the folder, keeps the full history, and logs a `cap_migration` event in HISTORY.md. A migration is itself a signal: index inclusion drives passive flows.
- `watchlist.yaml` can pin a stock to a segment manually if you prefer.

---

## 5. Combining the lenses: decision matrix

Each lens produces a score from 0 to 100. **Red-flag vetoes** (governance, solvency, surveillance lists) override everything.

| Value ↓ / Momentum → | **Strong (≥ 70)** | **Neutral (45–70)** | **Weak (< 45)** |
|---|---|---|---|
| **High value (≥ 70)** | **STRONG BUY** — cheap *and* the market agrees | **BUY (staggered)** — build in 3–4 tranches | **WATCH / ACCUMULATE SLOWLY** — cheap but falling; check for a value trap |
| **Fair value (45–70)** | **BUY (momentum-led)** — with a trailing stop | **HOLD** | **REDUCE** |
| **Expensive (< 45)** | **MOMENTUM TRADE ONLY** — tight stop, no averaging down | **REDUCE** | **SELL / AVOID** |
| **Any + red-flag veto** | **AVOID** | **AVOID** | **SELL** |

Every verdict carries:

- **Confidence** (High / Med / Low), based on data completeness and whether the data sources agree.
- **Delta vs last month** (for example "HOLD → BUY, upgrade driven by P/E de-rating + RS turning up").
- **Hysteresis**: a verdict only changes when the score crosses the threshold by more than 5 points, so it doesn't flip-flop.
- **Market regime tag** from plan 02 (Risk-On / Neutral / Risk-Off). In a Risk-Off regime, momentum BUYs are capped at HOLD.
- **Limited history (D24):** when the value lens is informational (young listing, pre-profit company, or too little valuation data; plan 01 §3.1), the stock is placed in the **Fair value** row, its confidence is Low, and the verdict is labelled "limited history". When the momentum lens is informational too (fewer than 126 sessions; plan 02 §3.9), the verdict comes from vetoes only, WATCH at best.

---

## 6. Analysis types covered

| Type | What it means here | Where |
|---|---|---|
| **Fundamental** | Valuation, quality, balance sheet, growth, governance | Plan 01 |
| **Time series** | Month-over-month, quarter-over-quarter and year-over-year deltas; rolling trends; score trajectory; regime history | HISTORY.md; plans 01 and 02 |
| **Qualitative** | Moat, management and capital allocation, concall tone, industry tailwinds, news and event risk | Plan 01 §6 (LLM with citations, plus your THESIS.md) |
| **Technical / momentum** | Relative strength, trend structure, patterns, regime | Plan 02 |
| **Segment-level** | Ranked table of all stocks in the cap, sector concentration, what changed this month | `_SEGMENT_SUMMARY/` |

### Fundamentals refresh quarterly, prices monthly

Indian companies report quarterly: results are due within 45 days of quarter end (60 days for the audited Q4), and shareholding patterns within 21 days. In two out of three monthly runs, therefore, fundamentals won't change. Each report states **"Fundamentals as of Q1 FY27 (published YYYY-MM-DD)"**, and valuation moves in those months come from **price alone**. The report calls this out explicitly, because a re-rating without an earnings change is a different story from one backed by earnings.

---

## 7. Architecture (agentic, MCP-first, following your standards)

The full agent-facing design, including the tool catalogue, agent roster and ADR-010…012, lives in **plan 15**. The shape:

```
 WORKFLOWS (deterministic code)                          AGENTS (Claude Agent SDK, plan 15 §5)
 watchlist ─► Universe ─► Data (adapters, fallback,        Qualitative Analyst · Devil's Advocate
              validation, caching)                          Monthly Reviewer · Event Triage
                 │                                          Watchlist Curator
      ┌──────────┼───────────┐                              You, in Claude Desktop / Claude Code
      ▼          ▼           ▼                                          │
  Value      Momentum    [Qualitative step:                            │ MCP (stdio, local only)
  Scorer     Scorer       calls AGENT.qualitative] ◄───────────────────┤
  (pure Py)  (pure Py)         │ confidence ±1 only                    ▼
      └──────────┼───────────┘                          ┌───────── parakh-mcp ─────────┐
                 ▼                                      │ reports · analytics · data   │
        Verdict policy (rules, Python)                  │ portfolio (masked, propose)  │
                 ▼                                      │ notify (policy enforced)     │
  Report writer (Jinja2 → md) → History → Publish       │ jobs · audit                 │
                 ▼                                      └──────────────┬───────────────┘
        Notifier ◄── notify.queue ◄── agents                          ▼
                                                        services/ (ADR-006 contract)
```

**Design rules** (from your SCAIX coding standards, plus plan 15):

- **The LLM never produces a number that feeds a score.** All metrics and scores are deterministic Python. The LLM handles narrative, qualitative ratings and summaries only.
- **Tools are the only door (AG-01).** Agents reach data and state only through `parakh-mcp` tools; no shell, files, web or direct database access.
- **Workflows where the path is known, agents where judgement is needed (AG-02).** The monthly run and the watchers are code; agents do review, reading, counter-arguments, triage and curation.
- **Agents propose, you decide (AG-03).** No approve, edit or delete tools exist; `propose_*` tools feed the review inbox and Telegram buttons.
- **Policy lives in the server (AG-05).** Routing, de-duplication, cool-downs, masking and budgets are enforced by the tools.
- Prompts live in `src/prompts/*.yaml` and are versioned.
- Agents run through the `AgentRunner` interface with retry and backoff, Pydantic-validated outputs, a hard `max_turns` and a token budget (plan 15 §6).
- Structlog observability (`agent_name, tool_called, tokens, latency, success`) through SDK hooks, with Langfuse from day one.
- Golden-snapshot tests: 3 fixed stocks with frozen input data, where the expected scores must match an independent oracle (plan 14 §4.1). The LLM is mocked in CI (`FakeRunner`).
- Every metric in a snapshot records its **source and as-of date** (`"pe": {"value": 24.3, "source": "screener", "asof": "2026-09-23"}`).

### Data sources (multi-source, with fallbacks) — v0.2

Every source has a **trust tier**:

- **T1 (official):** the exchange, regulator or the company's own filing.
- **T2 (reputable aggregator).**
- **T3 (convenience, or LLM-derived).**

When sources disagree, the higher tier wins, and a disagreement above tolerance is written to `data_quality`.

**Prices, volumes and market data**

| Need | Primary | Fallback | Tier | Notes |
|---|---|---|---|---|
| Daily OHLCV (adjusted) | yfinance (`TICKER.NS`) | NSE bhavcopy (`jugaad-data` / `nselib`); broker historical-candle APIs (Upstox, Angel One SmartAPI, Dhan, Kite Connect; check each one's terms and pricing) | T2 / T1 | Cross-check the last close; flag >1% mismatch. A broker API is the most reliable long-term feed |
| Delivery %, bulk and block deals | NSE / BSE daily reports | — | T1 | Institutional-activity signals |
| F&O open interest, ban list | NSE F&O bhavcopy | — | T1 | Only for F&O stocks (about 200 names) |
| India VIX, index levels, index constituents | NSE / niftyindices.com | yfinance | T1 | Constituents are needed for percentile ranks and breadth |
| ASM / GSM surveillance lists, price bands | NSE / BSE surveillance pages | — | T1 | Daily; drives vetoes and circuit-trap flags |

**Fundamentals and filings**

| Need | Primary | Fallback | Tier | Notes |
|---|---|---|---|---|
| Financial statements (10-year) | **Screener.in export** (your account) | **XBRL financial results filed on NSE/BSE** (structured data, straight from the company); yfinance (patchy) | T2 / T1 | Use XBRL to cross-check the latest quarter. Always use **consolidated** figures, with standalone as a secondary view |
| Operating and segment KPIs (volumes, realisations, order book, same-store sales growth, ARPU) | **Tijori Finance** (strong on segment and operating data) | Investor presentations (PDF) parsed by the LLM | T2 / T1 | Sector KPIs that standard ratio sites miss |
| Shareholding pattern, pledge | NSE / BSE quarterly filings | Screener | T1 | Quarterly |
| **Insider trades (SEBI insider-trading rules), substantial acquisitions (SEBI takeover code)** | NSE / BSE disclosures | Trendlyne | T1 | Promoter open-market *buying* is one of the strongest value confirmations |
| Corporate announcements (results dates, board meetings, auditor or management resignations, orders won) | NSE / BSE announcements feed | Company IR page | T1 | Feeds the event calendar and red-flag engine |
| Credit ratings and rating actions | CRISIL / ICRA / CARE / India Ratings press releases | Exchange announcements | T1 | A downgrade is an early solvency warning, often before the price moves |
| Analyst consensus estimates, revisions | Trendlyne (paid tiers) / Moneycontrol estimates | — | T2 | Thin coverage for small caps, so mark it N/A rather than guess |
| Mutual fund holdings (per stock, monthly) | **AMFI / fund-house monthly portfolio disclosures** | Screener, Trendlyne | T1 | "Number of MF schemes holding" trending up = institutional discovery (strong for mid and small caps) |
| Cap classification | AMFI semi-annual list | — | T1 | January and July |

**Qualitative inputs**

| Need | Primary | Fallback | Tier | Notes |
|---|---|---|---|---|
| **Concall transcripts, guidance, management commentary** | **BSE-filed transcript PDFs, found via Screener's Concalls list** (locked, D7; verified 2026-09-24; extraction and validation ported from Drishti) | Manual upload; concall.in summaries (optional); company IR pages | T1 (filed transcript) | Companies must upload earnings-call transcripts under SEBI's listing rules. Every number or guidance statement used anywhere must be an **exact quote** found in the transcript text |
| Annual reports, investor presentations | NSE / BSE filings, company IR | — | T1 | MD&A, related-party transactions, contingent liabilities, auditor report |
| News | Google News RSS per company, ET / Business Standard / Mint / Moneycontrol RSS | — | T2 | Event risk only; never feeds a score directly |

**Macro and market context**

| Need | Primary | Fallback | Tier |
|---|---|---|---|
| 10-year G-sec yield, repo rate, CPI | RBI DBIE / FBIL | Manual config | T1 |
| FII / DII daily flows | NSDL FPI Monitor (FII), NSE provisional FII/DII data | — | T1 |
| Nifty P/E, P/B, dividend yield (history) | niftyindices.com | — | T1 |
| USD/INR, crude (Brent) | yfinance / RBI reference rate | — | T2 |

**Optional paid sources, if this grows into something bigger:** ACE Equity or Capitaline (clean point-in-time fundamentals, which also fix the value-backtest problem), CMIE Prowess (institutional-grade, expensive), EODHD or Financial Modeling Prep (APIs with varying India coverage).

---

## 8. Report template (per stock, monthly)

```markdown
---
ticker: POLYCAB
isin: INE_XXXXXXXXX           ← (illustrative) stable ID across symbol changes & mergers
cap: mid_cap
sector: Capital Goods – Cables
peers: [KEI, FINCABLES, RRKABEL]
benchmark: NIFTY MIDCAP 150
period: 2026-09
price_asof: 2026-09-30
fundamentals_asof: Q1 FY27 (2026-07-18)
value_score: 58   (Δ +4)
momentum_score: 81 (Δ -3)
qualitative_score: 3.8/5 (Δ +0.2)
verdict: BUY (momentum-led)   (prev: BUY, held 3 months)
confidence: High
regime: Risk-On (VIX 12.4, FII 20d net: +₹8,200 Cr)
position: HELD · 40 sh · avg ₹6,210 · P&L +14.6% · wt 4.1% · LTCG in 37 days
framework_version: 0.2 (weights hash a91f…)
next_event: Q2 FY27 results — 2026-10-17
---
# POLYCAB — Sep 2026
## 0. TL;DR                            ← one line: verdict + the single biggest reason
## 1. Verdict, what changed & why      ← score-attribution: which metrics moved the score (Δ waterfall)
## 2. Action box                       ← entry zone · stop · fair-value range · risk/reward ratio
                                         · suggested action given position (add / hold / trim / exit)
                                         · tax note (STCG vs LTCG if sold now)
## 3. Bull / Base / Bear cases         ← price ranges with key assumption for each
## 4. Value scorecard                  ← metric | value | vs 5y median | vs sector | vs peers | points
## 5. Momentum scorecard               ← + active signals + trend template + stage + signal track record
## 6. Earnings & concall tracker       ← results vs expectations; guidance vs delivery (last 4 qtrs);
                                         key management quotes QoQ (exact quotes from the filed transcript)
## 7. Peer comparison table            ← valuation, ROCE, growth, RS for 3–5 peers
## 8. Ownership & smart money          ← promoter / FII / DII / MF-scheme count; insider buys/sells;
                                         bulk/block deals; pledge
## 9. Qualitative view                 ← moat, management, industry; citations
## 10. Thesis check                    ← each "sell if…" condition from THESIS.md: ✅ intact / ⚠️ / ❌ broken
## 11. Time-series view + charts       ← price+DMAs+RS line, P/E band, score trajectory (PNG embeds)
## 12. Upcoming events & catalysts     ← results, ex-dates, index rebalance, lock-in expiry
## 13. Red flags, risks & watch items
## 14. Data quality & sources          ← per-section freshness, source tier, cross-source conflicts
## 15. Methodology & disclaimer        ← framework version; personal-use disclaimer
```

**Fields added in v0.2 and why:**

- **ISIN:** stable across ticker renames, demergers and mergers, so history never breaks.
- **Position, tax and action box:** turn "BUY/SELL" into an action you can take for your own situation.
- **Score attribution:** explains *why* a verdict changed.
- **Bull/base/bear cases:** force you to think in ranges.
- **Thesis check:** holds you to the sell rules you wrote.
- **Signal track record:** shows how reliable each signal has been for this particular stock.
- **Events:** so you don't act 3 days before results.
- **Charts:** a P/E band chart and an RS line are worth more than any table.
- **framework_version:** keeps the history comparable when the rules change.

The `_SEGMENT_SUMMARY/YYYY-MM.md` file ranks every stock in the cap by combined verdict, lists **verdict changes**, **new signals** and **red flags**, and shows the segment regime (benchmark vs its 200 DMA, breadth, VIX and flows). **v0.2 adds:** a portfolio-level view (sector concentration, correlation clusters, total exposure by verdict), a "best new ideas" list (highest combined score among stocks not held), a "weakest holdings" list, and a monthly **framework scorecard** (hit rate of last quarter's BUYs and SELLs).

---

## 9. Phased roadmap

Dates, phase contents and exit gates live only in **plan 09**. The test gates for each phase are in **plan 14 §9**.

---

## 10. Decisions

Every decision is logged in one place: **plan 13 §2**. Architecture decisions are ADR-001…012, indexed in plan 04 §5.

---

## 11. Changelog

Pre-baseline history. **Changes after the baseline are logged only in plan 13 §9.**

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-09-24 | Initial plans: master, value, momentum, automation |
| **1.0** | 2026-09-24 | **Baseline locked.** New **plan 13** (decision log D1–D16, Production checklist 26/34 → 34/34 with P1–P10, CAS and Supabase consequences, slip rule, week-1 steps). Name **Parakh**, tier **Production**. §7 concall source → BSE-filed transcripts; §10 decisions resolved. PRD 1.3, feature spec 1.3, rollout 1.3, plans 01/03/04/05/10/11 updated; ADR-003/004/008 accepted, ADR-009 (secrets via AWS SSM + OIDC) added |
| 0.7 | 2026-09-24 | New **plan 11: Drishti review** (what to reuse from Drishti 2.0) and **plan 12: UI/UX design** (surfaces, UX-01…13 principles, design tokens adopted from Drishti, `UI.*` component library, review-inbox Home, Stock Detail order, thesis form, Telegram UX, privacy/share, UX tests). Plan 03 §4 rewritten: channel comparison incl. **WhatsApp Business Platform (deferred)**, **ADR-008 (proposed)**, routing matrix, two-way Telegram actions. PRD 1.2 (US-14/15/16, FR-23/24, NFR-13, §8), feature spec 1.2 (F22; UI criteria in F09/F11/F15/F17), rollout 1.2, plans 04/06/10 updated |
| 0.6 | 2026-09-24 | New **plan 10: Audit, Logging & Governance** (4 sub-layers, `AUD.*` event taxonomy, hash-chained append-only audit, outbox, step ledger + replay, lineage/explain, LLM/model/data governance, retention, review cadence, ADR-007). PRD 1.1 (G8, US-13, FR-21/22, NFR-11/12), feature spec 1.1 (F21), rollout 1.1 (governance deliverables per phase), plans 03/04/05 cross-referenced |
| 0.5 | 2026-09-24 | ADR index + **ADR-006 (UI: Streamlit first, thin UI over services, FastAPI + React for future animated pages)** in plan 04 §5. New **07_PRD.md**, **08_FEATURE_SPEC.md** (F01–F20 with acceptance criteria) and **09_PHASED_ROLLOUT_PLAN.md** (dated phases, milestones, shadow mode, feature flags, rollback) |
| 0.4 | 2026-09-24 | New plan 06: watchlist auto-curation. Confirmed choices: two lists (My = approval only; System = auto, capacity-limited), monthly review + mid-month urgent adds, all four add sources, approvals on a Streamlit page (CLI fallback). It supersedes the tier-promotion rules in plan 05; the Streamlit page is pulled into Phase 4, and watchlist and holdings tables move to Supabase in Phase 4 |
| 0.3 | 2026-09-24 | Strengthening pass: value §11 (archetypes, expected IRR vs hurdle rate, value-trap detector, owner earnings, thesis drift), momentum §11 (dual/residual momentum, path smoothness, rank buffer, after-tax evaluation, volatility sizing, walk-forward). New plan 04 (Lens plug-in architecture, ID-anchored code standards, pre-build infra/data risks) and plan 05 (storage review → DuckDB/Parquet + Supabase, data model, tiered full-cap coverage, tax-lot holdings, ownership-aware alerts) |
| 0.2 | 2026-09-24 | Gap review. Added cross-cutting layers (market context, event calendar, position and tax context, earnings-revision momentum, peer sets, methodology versioning); expanded data sources with trust tiers (XBRL, insider-trading disclosures, AMFI MF holdings, Tijori, credit ratings, NSDL flows, **concall.in**); expanded report template (TL;DR, action box, bull/base/bear, earnings and concall tracker, thesis check, peers, ownership, events, charts); new value parameters (plan 01 §2.7); new momentum parameters and signals (plan 02 §3.8); event-driven alerts and a plain-language "how it works" (plan 03 §0) |

---

*This is a personal analytical framework, not investment advice. All thresholds are starting assumptions, to be calibrated in Phase 5.*
