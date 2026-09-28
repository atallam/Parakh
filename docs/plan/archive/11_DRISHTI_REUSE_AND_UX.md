---
title: Drishti Review — What to Reuse, and UI/UX Considerations
version: 1.3 (ARCHIVED 2026-09-24)
date: 2026-09-24
status: "Resolved at baseline (plan 13): UI/UX (§5) adopted into plan 12; concall source #6 adopted (D7); thesis-aware concall + structured THESIS.md adopted with LLM-flag-only rule (D13); holdings #7 decided differently: CAS statement, not WealthLens (D8); Drishti's own future is outside Parakh's scope (D16)."
owner: Avinash Tallam
reviewed:
  - "Web Applications/Drishti 2.0" (May 2026: FastAPI backend, React frontend, 8 design docs)
  - "Web Applications/Drishti" (v1 backend, plus a Claude worktree of WealthLens Hub)
method: read the design docs and code · ran the test suite · ran live source checks from the owner's PC (2026-09-24) · ran the app on seeded demo data and took screenshots
related: 00 §7 (sources), 01 §11.7 (thesis drift), 04 ADR-006 (UI), 05 (holdings), 07 §12 (decisions #6, #7, locked in plan 13), 08 F06/F09/F14/F15, 10 (audit)
---

# Drishti Review: What to Reuse, and UI/UX Considerations

> **ARCHIVED on 2026-09-24. This is a point-in-time review, kept as history and porting guidance.** Its live content has moved: the THESIS.md schema → plan 05 §2.4; UI/UX → plan 12; decisions → plan 13 (D7, D8, D13, D16); the Drishti test lessons → plan 14 §12. The reuse matrix (§3) stays useful as porting guidance in Phases 0.5–4. If anything here disagrees with a live doc, the live doc wins.

## 1. Recommendation in one paragraph

**Don't extend Drishti into this framework. Build the framework as planned, and bring in Drishti's best idea as its thesis layer.** That idea is the *structured, versioned investment thesis* that each quarter's concall is checked against. Port four modules (concall pipeline, stock universe, portfolio analytics maths, the provider pattern) with the hardening listed below. Keep Drishti's visual language for the UI. Leave its API, signal and verdict engines, scrapers and React app behind.

Drishti answers *"is the story I bought still true?"* for 5–15 holdings, on demand. This framework answers *"what is cheap, what is strong, and what changed?"* across 150–500 stocks, in batch, with audit and replay. The two fit together well, but Drishti's app shell and its standards don't carry over. Drishti's database holds one holding and no thesis history, so there is **no data to migrate**.

---

## 2. What Drishti is today (verified)

| Item | Finding |
|---|---|
| Stack | FastAPI + SQLAlchemy + APScheduler; ~8,000 lines of Python (excluding tests) across engines, services and routers; React 18 single-file UI (`App.jsx`, 2,071 lines); DM Sans/DM Mono design system |
| Engines | `price`, `signal`, `thesis`, `verdict`, `concall`, `redflags`, `calendar`, `analytics`, `stock_universe`, `twelve_data_provider` |
| Tests | 199 collected: **197 pass, 2 skipped** from a local copy. On the OneDrive-synced folder, SQLite fails with `disk I/O error`, so run tests outside OneDrive (consistent with decision #9) |
| Data | `drishti.db`: 1 holding, 0 thesis-history rows, 0 concall analyses |
| Drishti v1 folder | Early backend, plus a worktree copy of **WealthLens Hub** with broker import routes (Kite, ICICI Breeze, Setu Account Aggregator, SnapTrade) writing to a Supabase `holdings` table |

### Live checks (2026-09-24, from your PC)

| Check | Result | Consequence |
|---|---|---|
| NSE announcements API (`/api/corp-announcements`) | **HTTP 404**; the endpoint has moved | NSE transcript provider returns nothing |
| BSE announcements API | **HTTP 403 Access Denied** | BSE transcript provider returns nothing |
| Screener documents-page PDF scrape | Nothing found (NTPC, POLYCAB) | — |
| Screener "text" provider | Returns the *Concalls link list* (9.6k chars), not a transcript; the validator correctly rejects it | **Automatic concall analysis fails for every Indian stock today**; only manual upload works |
| **Screener company page → Concalls → "Transcript" link → BSE PDF** | NTPC lists 18 transcripts. The latest (Aug 2026) redirects to `bseindia.com/xml-data/corpfiling/AttachHis/…pdf`: **25 pages, 73.5k characters, passes Drishti's validator** | A working, T1 (exchange-filed) sourcing route: one small new provider |
| Promoter-pledge and FII regexes vs today's Screener page | Neither matches; both return UNKNOWN | The UI then shows **"✅ No red flags detected"** (fails open) |
| Screener shareholding column order | Oldest → newest (Sep 2023 … Jun 2026) | Even if it matched, the FII regex (first two cells) would compare the **two oldest** quarters |
| `pe_3yr_avg` | Computed as `price_t ÷ today's trailing EPS` | Measures price against its 3-year average, not P/E history. Don't port it; plan 01 needs P/E vs the stock's own 5y/10y median from historical EPS |

### The app running on seeded demo data (9 holdings)

| Finding | Evidence |
|---|---|
| Portfolio header always shows `₹—` | `/api/portfolio/summary` returns 500: the router passes 2 arguments to a 1-argument function |
| Card and drawer can disagree on the signal | `/verdict` recomputes the signal for one holding in isolation. For NTPC, the list says **ADD** (4.0% of portfolio, sector −21.6pp); `/verdict` says **TRIM** (100% of portfolio, +70pp) |
| The two headline V2 sections never render | The UI reads `verdict.components` / `verdict.thesis_history`; the API returns `component_status` / `thesis_timeline` |
| Drawer opens slowly | `/verdict` takes about **5 s per open**, uncached (PRD target was < 500 ms) |
| LLM call | Model hard-coded (`claude-sonnet-4-20250514`), raw HTTP, no retry, prompt inline in code, JSON parsed with a regex fallback |

The tests pass because they mock the scrapers and never exercise the UI↔API contract. That's the gap to close here: **fixtures from real HTML and PDFs, plus UI contract tests**.

---

## 3. Reuse matrix

| # | Drishti module | Decision | Keep | Change | Lands in |
|---|---|---|---|---|---|
| 1 | `thesis_engine` + V2 thesis model | **Adopt the model** (rewrite, ~200 lines) | 4-part thesis; original locked after first save; component status (CONFIRMED / NEUTRAL / STRESSED / BROKEN); pre-committed breakers; evidence on every change | THESIS.md front matter (§4); history = `AUD.THESIS.*` audit events (plan 10), not a separate table; **LLM output can't set BROKEN by itself** (NFR-02) | F09 §10 Thesis check · F14 `FLAG.thesis_broken` · F06 · F21 |
| 2 | `concall_engine` | **Adapt: the biggest win** | Provider-chain pattern; `PDFExtractor` (PyMuPDF + optional OCR); `_is_valid_transcript` (4 heuristics, proven today); Q&A-preserving truncation; thesis-aware prompt schema (`component_assessment`, `breaker_checks`, `quote_or_paraphrase`); stage-by-stage error model with a manual-upload fallback; transcript text stored for re-analysis | New **ScreenerConcallsProvider** (§2); validate *each* candidate and continue down the chain on failure (today the first "found" source ends the search); Anthropic SDK + Pydantic structured output + Tenacity; prompt in `src/prompts/*.yaml`; model name from config; **exact quotes only**, string-matched against the transcript (AC-F06.2); cache by document hash (AC-F06.3) | Spike ② (Phase 0.5) · F06 (Phase 4) |
| 3 | `stock_universe` | **Lift** | NSE `EQUITY_L.csv` + BSE scrip list, symbol/name → ISIN lookup, 24 h cache | Re-test the BSE list endpoint (the BSE announcements API now returns 403); key on ISIN | F01 · F15 (AC-F15.2 ISIN lookup) · Phase 1 |
| 4 | `analytics_engine` | **Lift the maths, rewire I/O** | XIRR (Newton with bisection fallback), max drawdown, HHI concentration, sector attribution | Read from the repository layer, not the ORM; benchmarks by cap (Nifty 100 / Midcap 150 / Smallcap 250) instead of Nifty 50/500 | F10 portfolio view (AC-F10.3) · F17 · Phase 2 |
| 5 | `price_engine` | **Pattern only** | `BaseMarketDataProvider` + fallback merge; FX handling; "no network call on a hot path" rule | Drop `pe_3yr_avg`; adapters return pandera frames with source/tier/as-of (F02) | F02 · Phase 1 |
| 6 | `twelve_data_provider` | **Optional** | Graceful-null client (800 credits/day free) | Register as a T2 price fallback behind yfinance/bhavcopy | F02 |
| 7 | `redflags_engine` | **Pattern only** | `BaseFlagChecker` + severity model + per-check TTL | Replace the Screener regexes with exchange shareholding/pledge filings (T1) or the Screener export; **UNKNOWN must never render as clean** | F04 vetoes · F13 · Phase 1/3 |
| 8 | `calendar_engine` | **Concept only** | "What's coming up", sorted by days until the event | Source from exchange board-meeting announcements (T1), not yfinance `.calendar` | Report §12 · F13 |
| 9 | `signal_engine`, `verdict_engine` | **Leave the code, keep two ideas** | ① Evidence-first reasons: at most 4 bullets, thesis → concall → valuation → allocation. ② Separate wording for owned stocks (ADD / HOLD / TRIM / EXIT) and research stocks (ENTER NOW / WAIT / AVOID) | The verdict policy (matrix, vetoes, hysteresis) replaces allocation-driven signals; **one verdict source** that every surface reads | F08 · Phase 2 |
| 10 | FastAPI routers, auth, React UI | **Leave (ADR-006)** | Design tokens and the component vocabulary (§5.1) | Rebuild as Streamlit helpers over shared Pydantic view models | F15 · Phase 4 |
| 11 | Test suite | **Borrow the cases** | Edge-case catalogue: research stocks excluded from weights, one TRIM per sector, cache guards, original thesis immutable | Add golden fixtures of real Screener HTML and filed PDFs; UI contract tests | Phase 0 CI |
| 12 | WealthLens Hub broker imports (in the Drishti v1 folder) | **Pointer for decision #7** | Kite, Breeze, Setu AA and SnapTrade → Supabase `holdings` already exist | Read holdings from WealthLens tables instead of building importers. The copy reviewed is from May, so confirm against the live repo | F03 · Phase 1/4 |

---

## 4. Structured thesis for THESIS.md

This keeps AC-F09.4 intact: the pipeline still **never writes** THESIS.md. You write it (by hand, or through the Streamlit form). The pipeline reads it and writes thesis *state* into the snapshot and the audit trail.

```markdown
---
symbol: NTPC
isin: INE_XXXXXXXXX            # illustrative
thesis_version: 1
original:                       # locked: pre-commit hook rejects edits once saved
  written_on: 2024-01-15
  statement: >
    Primary beneficiary of India's 500 GW renewable target through FY28;
    government power-infra capex growing 20%+ a year.
key_metrics:                    # max 5; the concall agent reports on each, every quarter
  - {id: KM1, text: "Renewable capacity addition per quarter (GW)"}
  - {id: KM2, text: "PGCIL order inflow for transmission"}
  - {id: KM3, text: "Fuel cost per unit (coal linkage stability)"}
breakers:                       # max 5; exit conditions committed in advance
  - {id: BR1, text: "Renewable target cut by more than 30%",        check: llm_flag}
  - {id: BR2, text: "Private sector wins most new capacity awards",  check: llm_flag}
  - {id: BR3, text: "Revenue growth below -10% YoY",                 check: metric,
     rule: "revenue_growth_yoy_pct < -10"}
sizing_rationale: "Core position, ~8%. Add on thesis confirmation."
review_by: 2027-01-31
---
## Working thesis (editable prose)
…
```

**Status rules (improving on Drishti):**

| Input | Can set | Why |
|---|---|---|
| `check: metric` breaker, evaluated in Python | **BROKEN** | Deterministic and replayable |
| LLM `component_assessment` = STRESSED | **WATCH** + `FLAG.thesis_review` | The LLM informs, it doesn't decide |
| LLM `breaker_checks.triggered` (`llm_flag`), or `component_assessment` = BROKEN | **WATCH** + a 🔴 review flag with the verbatim quote; **BROKEN only after you confirm** | In Drishti, a guidance score < 4 alone produced BROKEN → EXIT. Here that becomes a flag for you, in line with NFR-02 and AC-F06.1 |
| Owner confirmation or override | Any status, with a reason and expiry | Plan 10 overrides |

A component-by-quarter history comes free from the audit events, which enables Drishti's best visual, the thesis heatmap (§5.1).

---

## 5. UI/UX

### 5.1 Borrow from Drishti

| Drishti element | Why it works | How it maps here |
|---|---|---|
| **Locked colour tokens**: HOLD slate `#64748B`, ADD/INTACT green `#16A34A`, TRIM/WATCH amber `#D97706`, EXIT/BROKEN red `#DC2626`, navy `#1E3A5F` | One meaning per colour everywhere | `config/ui_tokens.yaml`, read by the Jinja report templates, the Telegram formatter and Streamlit CSS. Extend to the 8 verdict levels; pair every colour with an icon and a word |
| **DM Mono for every number**, Indian digit grouping (`en-IN`) | Columns don't jitter; ₹1,92,000 reads naturally | Same fonts via `st.html` CSS; `format_inr()` helper shared with the reports |
| **SignalChip + ThesisPill + ConcallPill** | Verdict, thesis health and latest concall in a single glance | `ui/components.py: verdict_chip(), thesis_pill(), concall_pill()` |
| **52-week bar with an entry-price notch** | Instant "where am I versus my cost" | Plotly mini-bar; for this framework also show the **value fair-value band** and **action-box entry zone** |
| **Sparkline with a dashed average-cost line**, `~` marker when data is synthetic | Honest, compact trend | Plotly sparkline on Watchlist Review cards (plan 06 already asks for a 12-month sparkline) |
| **Thesis heatmap**: components × last 3 quarters | Shows slow erosion that no single number catches | Stock Detail page; also a **score heatmap** (stock × month, value and momentum) on the Segment Dashboard |
| **Component grid**: coloured left border, status badge, one-line evidence | Evidence sits right beside each status | Report §10 Thesis check and the Stock Detail page |
| **Signals tab**: count chips + urgency sort + first reason inline | Triage in seconds | Home page "Needs attention" list |
| **Alerts drift feed** with filter chips | A readable log of what changed and why | Home review inbox (§5.2 #1); powered by `AUD.*` events |
| **Concall stage ladder** with a named failing stage, retry and manual upload | No dead ends | Any long job in Streamlit (qualitative refresh, re-score) |

### 5.2 What else to consider (beyond plans 04/06/07)

1. **Open on a review inbox, not a dashboard.** Home = everything that changed since your last review: verdict changes, thesis status changes, new flags, pending approvals. Each has "mark reviewed". This is how you hit the ≤ 60 min monthly review target (PRD §5).
2. **One verdict, three depths.** Telegram (one line per item) → Streamlit card (verdict + ≤ 4 evidence bullets) → full report (15 sections, collapsed below TL;DR + action box). All three read the **same snapshot**, so the ADD-vs-TRIM contradiction seen in Drishti can't happen.
3. **Unknown ≠ clean.** Every check shows one of three states: ✅ checked and clean · ⚠️ flagged · ❔ couldn't check (with the reason and when it was last attempted). Make this a UI rule with a test. It's the "honest uncertainty" principle (PRD §8.6) made concrete.
4. **Two sets of verbs.** Owned: ADD / HOLD / TRIM / EXIT. Not owned: STRONG BUY … AVOID, or Drishti's ENTER NOW / WAIT / AVOID. Never show "BUY" on a stock you already hold at full weight.
5. **Capture the thesis at the moment of decision.** When a holding is added or a My Watchlist suggestion is approved, open the 4-field thesis form (tag inputs, max 5 each). Show a single "N holdings without a thesis" banner, not a nag on every row (Drishti's Signals tab repeated it on 5 of 9 rows).
6. **Nothing slow in page render.** Pages read precomputed snapshots only; no scraping or LLM calls while a page draws (Drishti's drawer waited about 5 s). Long jobs run in the background with the stage ladder. That keeps NFR-07 (< 2 s) achievable in Streamlit.
7. **Shared view models.** The UI↔API key mismatch in Drishti silently hid two sections. Streamlit + Pydantic view models in `services/` removes that class of bug; add a Streamlit `AppTest` smoke test that renders every page from fixtures (another point in ADR-006's favour).
8. **A privacy view that is safe to screenshot.** One toggle hides quantities, ₹ values and P&L (percentages only) and adds the personal-use disclaimer. You said you'd only ever share this as a recommendation, and this is the view to share from. It also keeps you on the right side of the SEBI note in plan 00 §2.
9. **Feedback where you read.** 👍/👎 "useful?" buttons on Telegram alerts (inline keyboard) and on Streamlit cards. That's the data PRD §5's alert-precision metric and F17 need, at zero extra effort.
10. **Telegram is the phone app.** Keep Streamlit desktop-first. Give Telegram a fixed template (≤ 10 lines, verdict chips as emoji + word, a deep link to the report). Drishti's 480 px mobile canvas is the right reference if a hosted phone UI arrives in Phase 6.
11. **Charts carry context, not decoration.** Every price chart shows entry cost, the fair-value band and the next event date (results, ex-date). Every score chart shows the verdict thresholds and hysteresis band, so a flip, or a non-flip, explains itself.
12. **Accessibility basics.** Never rely on colour alone (▲▼ arrows, icons, words). Tabular numbers. A readable dark mode for the Streamlit theme.

### 5.3 Drishti UX issues not to repeat

| Issue seen | Rule here |
|---|---|
| "No red flags detected" when 2 of 3 checks couldn't run | Tri-state checks (§5.2 #3) |
| Card and drawer disagree on the signal | One snapshot, many views (§5.2 #2) |
| Header `₹—` from a silent 500 | Every page region shows an explicit error with a next step, never a bare dash |
| Repeated setup nag on every row | One banner with a count, plus a direct action |
| About 5 s spinner on every drawer open | No network in render (§5.2 #6) |

---

## 6. Proposed plan changes (for your approval)

| Doc | Change |
|---|---|
| 07 §12 decision **#6** / 09 spike ② | Replace "concall.in access from the WealthLens code" with **"Screener Concalls → BSE-filed transcript PDF" provider** (verified working). concall.in becomes optional, not a dependency. Drishti's code never calls concall.in |
| 07 §12 decision **#7** | Default holdings source: **WealthLens Hub Supabase `holdings`** (already fed by Kite / Breeze / Setu AA / SnapTrade), after checking the live repo |
| 08 F06 | Thesis-aware prompt (key metrics + breakers); exact-quote verification; LLM breaker hits raise a review flag, never an automatic BROKEN |
| 08 F09 / 00 §3 | THESIS.md front-matter schema (§4); original locked by a pre-commit hook |
| 08 F15 | ✅ *Adopted v0.7 (F15, F22, plan 12).* Add a **Home review inbox** and a **thesis form**; tri-state checks; privacy view; Streamlit `AppTest` smoke test |
| 04 | ✅ *Adopted v0.7 (ADR-006 item 5).* New `config/ui_tokens.yaml` shared by reports, Telegram and Streamlit |
| 09 Phase 1 | Port `stock_universe` and the XIRR/drawdown/HHI maths; add real-HTML/PDF fixtures |

---

*Personal analytical framework; not investment advice.*
