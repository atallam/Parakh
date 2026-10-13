---
title: Coverage model and benchmarks: holdings only, universe as benchmark
version: 1.1 (new: D26, ADR-013; promoted from the 14 Oct 2026 staging draft)
date: 2026-10-14
owner: Avinash Tallam
parent: 00_MASTER_PLAN.md
owns: who Parakh analyses (the coverage set), what the wider universe is for (the benchmark panel), where benchmark numbers come from (borrow or build), and ADR-013. Phase placement of the work items lives only in plan 09; decision D26 lives only in plan 13
related: 01 §3 (profiles), 02 §2 (benchmarks), 05 §1 (data model), 06 (parked), 08 F01/F10/F14, 09 (R-items), 13 D9/D23/D25/D26, 18 (integration)
---

# Coverage model and benchmarks

## 1. Decision

Parakh analyses **only the stocks you own**. The wider universe (AMFI Large, Mid and Small) exists **only as a comparison baseline** (plan 13 D26, your decision of 12 Oct 2026).

The question Parakh answers changes with it. Before: "what is cheap, what is strong, and what changed across 150 to 500 stocks?" After: **"for every stock I hold, is the story I bought still true, how is it doing against its peers and its market, and does the position make sense?"** That is the question Drishti V2 asked of 5 to 15 holdings (plan 18 Part II), answered with Parakh's lenses, audit and agents.

This removes work, so it passes the D25 test ("does it change a decision I make with money?"): every verdict, alert and report now targets a stock you hold.

## 2. The coverage model

| Layer | Who is in it | What runs | What you get |
|---|---|---|---|
| **Coverage set** (replaces Tier A) | ISINs with an open lot in your CAS holdings. The three golden stocks stay as test fixtures even if sold | Everything: value and momentum lenses, verdict, thesis checks, event and momentum watchers, alerts, the orchestrated agents (plan 15), the monthly report | Reports, verdicts, alerts, case files |
| **Benchmark panel** (replaces Tier B and C) | The AMFI directory lists (100 Large, about 148 Mid, 250 Small) | **Prices only.** Cross-sectional maths: RS percentile, momentum z-score, breadth, regime inputs. No fundamentals, no LLM, no verdicts, no alerts, no reports | Numbers inside your reports ("top 12% of Midcaps"), never a row of its own |
| **Index benchmarks** | Cap indices (Nifty 100, Midcap 150, Smallcap 250, 500) and the NSE sector index that fits each holding | Level, total return, P/E, P/B and dividend yield history | "Stock P/E vs its sector index"; the regime's market-valuation check (F16) |

Rules:
1. **Nothing in the panel can raise an alert, a verdict, a watchlist suggestion or an LLM call.** It is read-only reference data, versioned and stamped like any other source (source, tier, as-of, raw hash).
2. **The coverage set comes from holdings, not from config.** `HoldingsProvider` (plan 18) returns the ISINs; the pilot list in `universe.yaml` keeps seeding tests and M1.
3. **A holding that is not an NSE-listed equity** (a mutual fund, a US stock, crypto) is outside Parakh's analysis in v1.0. An ETF is price-tracked and not scored until the instrument-type treatment is decided (plan 16 item 3).

## 3. What each comparison uses afterwards

| Comparison | Before (plan) | After | Status |
|---|---|---|---|
| Momentum RS percentile and momentum z-score | Cap universe, from prices | Benchmark panel (prices only) | Kept, no loss |
| Excess return, RS line, Mansfield RS | Cap index and sector index | Same | Kept |
| Regime breadth (% above 200 DMA) | Cap constituents | Panel (needs 80% member coverage, as built in `watch/context.py`) | Kept |
| Valuation vs own history (P/E percentile, reverse DCF) | Own 10-year history | Same | Kept (the core of the value lens) |
| Valuation vs sector | Sector medians from universe fundamentals | **NSE sector index P/E, P/B, dividend yield** (borrowed) | Changed; basis check needed (section 5) |
| Peer table (3 to 5 peers) | Auto-built from the universe | **Curated peers per holding**, only where the sector index does not fit | Changed, deferred |
| Value score percentile within cap, sector-neutral z-scores | Universe fundamentals | Not available | **Dropped** |
| "Best opportunities you don't own", full ranked universe, segment ranking table | Tier B | Not available | **Dropped** |
| System Watchlist, Watchlist Curator, urgent adds | Universe scores | Off (`watchlist.enabled: false`) | **Switched off**, code kept |
| Score-quintile calibration | Universe scores | **Momentum lens only**, on the price panel | Narrowed (section 7) |
| Allocation context (sector weight vs your target, concentration) | Limits only | **Portfolio Analyst** and a deterministic allocation refinement (plan 15, plan 18 Part II) | New |

## 4. What is switched off or removed

All by config flag, so each can come back without a rewrite.

1. Fundamentals loading for non-holdings: no Screener exports for the other ~490 names, no Tier B screening. This is the biggest saving; each export is a manual download.
2. Event watcher, daily momentum watcher, alerts and digests: scope is the coverage set. Today they iterate `universe.active` (the pilot plus the Mid rollout, about 154 names), so shadow logs fill with names you do not own.
3. System Watchlist, Watchlist Curator, suggestion tables, urgent adds: off. My Watchlist: see §9.
4. Segment summary v2 sections "opportunities" and "full ranking": removed; the holdings section, sector concentration, exposure and regime stay.
5. Qualitative, devil's-advocate and portfolio-analyst agents: coverage set only, scheduled by the orchestrator (plan 15 §5b).
6. The staged scale-up weeks (Mid, then Large, then Small) for fundamentals and reports: replaced by the price-only panel stages (R5).

## 5. Borrow or build the benchmarks?

**Borrow the index-level numbers, build the cross-sectional maths, and buy nothing.**

| Need | Borrow or build | Source | Notes |
|---|---|---|---|
| Index levels, total return, P/E, P/B, dividend yield history, cap and sector | **Borrow** | NSE Indices, [Historical Data page](https://niftyindices.com/reports/historical-data) (P/E, P/B, Div Yield and Total Return series are selectable there) | Free, T1. Named as the source for F16 in plan 00 §7, but **the loader is not built**: only the constituent CSVs are wired (`adapters/reference.py`) |
| Cap buckets and constituents | Already borrowed | AMFI half-yearly list, niftyindices constituent CSVs | Done (D9 as amended) |
| RS percentile, momentum z-score, breadth | **Build** (it already exists) | Your own price panel | Arithmetic on prices you load anyway. A vendor "relative strength rating" would be opaque and break the audit lineage and the numbers firewall (NFR-02) |
| Sector fundamentals medians (ROCE, margins, growth) | **Neither, for now** | n/a | Needs fundamentals for the whole sector, which D26 drops. Use sector-index multiples plus curated peers |
| Cross-check of industry multiples | Borrow, occasionally, by eye | [Damodaran's industry datasets](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/data.html), updated every January (last: 9 Jan 2026) | Annual. The region list I saw was US, Europe, Japan, Emerging Markets and Global, so I could not confirm an India-only cut. A sanity check, never an input |
| Paid databases (ACE Equity, Capitaline, CMIE Prowess) | Do not buy now | Plan 00 §7 | Only if you later want clean point-in-time fundamentals for a value backtest |
| Screeners with their own scores (Trendlyne, Tickertape and similar) | Human cross-check only | n/a | Proprietary and unauditable, so never an input to a score |

Why this split: an index-level P/E or P/B is a published statistic, so borrowing it costs one loader and traces to a T1 source. A percentile or breadth figure is arithmetic on data you already hold, so buying it would add an unauditable dependency to save nothing.

**Caveats to settle before relying on it (R3 starts with a spike):**
- **Basis mismatch.** Parakh's P/E comes from Screener consolidated figures. Confirm in NSE's index methodology which earnings basis the index P/E uses; if it differs, show the sector comparison as directional and flag the basis.
- **Terms and access.** I could not read niftyindices' Terms of use, and the historical series is served through a web form, not a documented API. The spike answers: can a GitHub-hosted runner fetch it (NSE has blocked cloud IPs elsewhere), what do the terms allow for personal use, and does each sector index you need have P/E, P/B and yield history?
- **No fitting sector index.** Airline, new-age, capital-markets intermediary and some defence names may have no representative NSE index. Fall back to the cap index and print "no sector benchmark" (UX-05: unknown is not clean).
- **Survivorship in the panel.** The panel is today's AMFI list. Fine for current percentiles; the calibration backtest keeps using point-in-time constituents (already enforced by `calibrate`).
- **Benchmark values are data.** Every stored benchmark value carries source, tier, as-of and raw hash, and the DQ scorecard covers it, so a re-score or replay uses the benchmark of the day.

## 6. Work items

Hours are estimates. Plan 09 owns the phase and date of each item (§1b there).

| ID | Work | Est. | Gate |
|---|---|---|---|
| **R2** | Split `universe.active` into `coverage_set` (from holdings) and `panel` (prices only). Point the analysis job, both watchers, alerts and agents at the coverage set; point `segment_mom` and breadth at the panel. Set watchlist and curator flags off. Tests: a panel-only stock can never reach alerts, agents or reports | 6 to 8 h | Pilot scores and verdicts unchanged (golden tests); AC-F01 reworded and green |
| **R3** | Benchmark pack: spike (access, terms, sector coverage), then a loader for index levels, total return, P/E, P/B, yield with lineage; `config/sector_benchmarks.yaml` mapping each holding's sector to an index or "none"; feed `index_pe_percentile` and the sector comparison | Spike 1 h, loader 3 to 4 h, mapping 1 to 2 h | Every benchmark value carries source, tier, as-of and hash; the DQ scorecard covers it |
| **R4** | Derive the coverage set from CAS; onboard the holdings that are not in the pilot: Screener export, profile choice, `listed_on`, thesis stub; ETF price-only | About 1 h per stock; more if a holding needs a new sector profile | Each new holding passes the plan 14 §4.4 edge-case checks and the R1 to R6 report rubric |
| **R5** | Panel hygiene: keep Mid, add Large and Small as price-only stages with about 2 years of daily bars per stock (enough for 12-1 momentum, the 200 DMA and 52-week measures). The 10-year load stays a one-off for `calibrate panel`. At the roughly 25 s per stock noted in `daily_prices.yml`, 350 more stocks is about 2.4 hours on the old depth, so split it across two runs; a shorter history may cut this, so measure it | 3 to 4 h | Breadth coverage at or above 80% of members per cap |
| **R10** | Calibration framing: the value lens is reported as "not calibrated on a universe"; the momentum lens is calibrated on the panel | 1 h | The quarterly report states the limitation |

## 7. Trade-offs you are accepting

1. **No discovery engine.** Parakh will not surface stocks you do not own. If you later want idea generation, the panel plus fundamentals can be re-enabled by flag, or you screen elsewhere and add the name by hand.
2. **The value lens stays uncalibrated.** Calibrating a score needs hundreds of scored stocks over years; 11 holdings cannot do it. The value weights stay judgment-based, the quarterly report says INSUFFICIENT for value by design, and you accept that the value lens is a disciplined checklist, not a measured predictor.
3. **Sector comparisons are coarser.** An index P/E is a cap-weighted aggregate, not a peer median. Curated peers close part of the gap for the names where it matters.
4. **Alternatives are yours to find.** A holdings-only engine cannot say a holding is cheap versus a better alternative. The "better opportunity" sell trigger in plan 01 §5 is limited to your own holdings.

## 8. Architecture decisions

### ADR-013: Coverage set plus a price-only benchmark panel

- **Status:** Accepted 2026-10-14 (plan 13 D26).
- **Context:** the plan covered 150 to 500 stocks in three tiers. You own 11 stocks and 1 ETF and said the initial scope went too wide. Cross-sectional measures (RS percentile, breadth) need many stocks, but only their prices.
- **Decision:** two populations with different rights. The coverage set (your holdings) gets every analysis. The benchmark panel (AMFI lists) gets prices only and can never reach alerts, agents or reports. Index-level valuation comes from NSE Indices.
- **Alternatives considered:**
  - Cut the universe entirely and rank only against indices: loses RS percentile and breadth, which the momentum lens and the regime need.
  - Keep Tier B fundamentals for the universe: it is the reason for the manual export load and the noisy shadow logs, and it only serves discovery.
  - Buy a fundamentals database: cost and an unauditable dependency for a feature (sector medians) that the sector index approximates.
- **Consequences:**
  - ➕ Far less to load, run, alert on and review; the review inbox contains only your stocks.
  - ➕ Cleaner story: every number in a report is about something you hold.
  - ➖ No discovery, no value-lens calibration on a universe, coarser sector comparison (section 7).
  - **Revisit when:** you want idea generation, or a value backtest becomes worth buying data for.

## 9. Decisions and open items

Decided 14 Oct 2026 (plan 13 D30):

- **Panel breadth:** all caps, meaning the AMFI Large, Mid and Small lists (about 498 stocks), prices only.
- **Golden stocks you no longer own:** kept as fixtures in tests only.

Deferred to the M1 review (plan 13 BL-11):

1. **My Watchlist:** stays off until the review. The choice then is off entirely, or a small manual list (up to 10) for stocks you are considering buying; it is discussed with the fund-lens question (plan 16).
2. **Curated peers:** start after M1, only for holdings the sector index does not fit.

*Personal analytical framework; not investment advice.*
