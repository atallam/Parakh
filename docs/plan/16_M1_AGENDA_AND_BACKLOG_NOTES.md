---
title: M1 review agenda and backlog notes (staging, merge into 08 and 13 at the M1 review)
date: 2026-10-11
owner: Avinash Tallam
status: STAGING. Not a plan of record. Items here are merged into plan 08 (feature spec) and plan 13 (decision log) at the M1 backlog review (D25), then this file is retired.
---

# M1 review agenda and backlog notes

Recorded 2026-10-11 under the D25 scope freeze: backlog only, no new scope before the M1 review.

> **Update 2026-10-14 (D28):** the Hub holdings-contract question below now has a worked proposal in **plan 18** (contracts `holdings.v1` and `insights.v1`, providers, exchange options, overlaps in §7). Treat plan 18 as the draft answer; the decisions listed here still get settled at the M1 review.

## Backlog item: US equities (decided "consider later", 2026-10-11)

Already listed as a one-line "US equities adapter" in F20 and "US stocks" in the spec's Later list. Added here with trigger conditions.

**What it would be:** a separate US market pack, not a retrofit of the Indian one. The Indian data layer (Screener, NSE/BSE filings, XBRL, AMFI caps, SEBI insider and pledge rules, ASM/GSM lists, FII/DII flows, India VIX, Nifty benchmarks, BSE-filed concall transcripts, the 15% INR hurdle) has no one-to-one US equivalent. US equivalents would be SEC EDGAR filings (10-K, 10-Q, 8-K, Form 4), S&P 500 / Russell benchmarks, and a separate transcript source.

**Needs that Parakh does not have today:** USD and INR returns with the FX gain separated; Indian-resident tax treatment of foreign holdings (LRS remittance, TCS, Schedule FA reporting, holding-period and dividend-withholding rules; confirm current rules with a tax professional); a US holiday calendar; new golden tests, calibration and UAT.

**Triggers to build (all must hold):**
1. v1.0 GA is signed and the fund lens (below) is done or consciously skipped.
2. You actively pick individual US stocks. If US exposure is through Indian feeder funds or ETFs, it is a fund-lens case (INR, no FX or LRS work). If it is a few passive direct holdings, track them in WealthLens only.
3. A separate ADR defines the US pack's scope.

**Earliest:** Q3 2027.

## First-review agenda item: WealthLens Hub holdings contract (noted 2026-10-11, to be settled at the first-milestone review)

**Question to settle:** which system owns holdings across all asset classes, and how does Parakh read them?

**Facts established 2026-10-11 from the Hub repo (read-only look, `wealthlens-hub` main):**
- `holdings.isin` exists and is part of Hub's CAS natural key (migration 0029: user, member, depository, account_id, isin). Older rows may hold the ISIN in `ticker` (a backfill resolves them) or have no ISIN (LEGACY rows).
- Hub imports NSDL, CDSL, CAMS and KFintech statements through casparser, with a Gmail auto-import cron, and tracks mutual funds (`scheme_code`, `routes/mf.js`).
- Asset types include IN_STOCK, IN_ETF, US_STOCK, US_ETF, MF, CRYPTO and US_BOND; USD handling and SnapTrade broker sync exist.
- Hub has a transaction ledger (migrations 0030, 0031) and `avg_cost`, which could supply the cost basis Parakh shows as "cost pending".
- Hub also has a Claude-based concall analysis (0–10 scores, migration 0012), which overlaps Parakh's F06.
- Hub's API accepts only a logged-in user's Supabase JWT; there is no machine-token route for Parakh's jobs.
- Not checked: what `lib/crypto.js` encrypts at rest.

**Working position (to confirm at the review):**
- Keep the two applications separate; integrate. Single-writer rule: Hub owns holdings, Parakh owns analysis (verdicts, scores, exposures).
- Scheduled jobs read a versioned, read-only holdings snapshot or endpoint through a `HoldingsProvider` adapter. MCP is for the agent and human layer (a read-only `wealthlens-mcp` beside `parakh-mcp`, masked by default), not for the pipeline (ADR-012 keeps MCP local; AG-02).
- Parakh's CAS path (D8) stays through GA.
- Never copy Hub's Supabase service key into Parakh's secrets; use a scoped read-only token or view.

**Decisions needed at the review:**
1. Holdings owner and the contract (fields, ISIN rule, masking, refresh).
2. Which concall analyser is authoritative (Parakh F06 or Hub), and whether Hub reads Parakh's output.
3. Whether to add `instrument_type` and `currency` columns to the securities table now (cheap now, costly to retrofit); the 1 ETF already needs a defined treatment (no ROCE or concalls; tracking error, expense ratio, premium or discount to NAV, underlying index valuation).
4. Whether a fund lens (mutual funds and ETFs, plus look-through exposure across funds and direct holdings) is the first post-GA item (suggested Mar–Apr 2027).
5. **Does anything need to call *into* Parakh?** Decides whether remote MCP access (plan 09 Phase 6 candidate, ADR-012) is reopened. Parakh calling a `wealthlens-mcp` (outbound; Hub runs on Render, so it is remote by nature) needs no change to ADR-012. Inbound access is needed only if a cloud tool or a shared claude.ai/phone surface must query Parakh. Prefer the lighter option first: Parakh pushes masked verdicts to Hub after each run. If inbound is chosen: a read-only, masked `reports.*` and `calibration.*` toolset behind OAuth, its own ADR, and never `portfolio.*` or any write-capable tool.
6. **Revisit My Watchlist and curated peers** (plan 13 D30, BL-11; plan 17 §9). My Watchlist stays off until this review.
