# Spike ③: Screener export format and exchange XBRL

- **Date:** 29 Sep 2026 · **Scripts:** `spikes/s3_xbrl.py` · **Code kept:** `src/parakh/adapters/screener_export.py`

## Screener export (your M&M file)

- Data Sheet v2.1: 10 years (FY17–FY26), 10 quarters (to Jun 2026), balance sheet, cash flow, year-end prices, derived share count. Values in ₹ crore. 460 facts parsed.
- The company is identified by the COMPANY NAME cell (your file was `M & M.xlsx`).
- **Pitfalls found and flagged by the parser:** META "Number of shares" is blank; balance-sheet "No. of Equity Shares" (111.76 Cr) is 10% below "Adjusted Equity Shares" (124.35 Cr) because shares held by M&M's employee trust are excluded. **Market cap must use the adjusted count**: ₹3,035 × 124.35 Cr = ₹3,77,402 Cr against Screener's ₹3,77,411 Cr.
- Year-end prices are bonus-adjusted (the FY18 1:1 bonus appears as "New Bonus Shares").
- No "reported on" dates, so point-in-time needs exchange filing times (below).

## Exchange XBRL (NSE, from the runner)

- `/api/corporates-financial-results` works and returns 107 rows for M&M, each with an XBRL link and a **broadcast timestamp**, which is the `reported_on` the bitemporal design needs (plan 04 §4 #3).
- **The feed stops at the Dec 2024 quarter.** Later results moved to SEBI's integrated filing. **Phase 1 must find the integrated-filing endpoint** for 2025+ results; until then the XBRL cross-check covers history only.
- **Revenue ties exactly:** consolidated Q3 FY25 `RevenueFromOperations` = ₹41,470.05 Cr = Screener's quarter (T1 = T2).
- **Profit lines need a definition map:** XBRL `ProfitLossForPeriod` (₹3,624.48 Cr) includes minority interest; Screener's "Net profit" (₹3,180.58 Cr) is attributable to owners. PBT also differs (likely the share of associates' profit; to confirm in Phase 1). Phase 1 maps each Screener line to its XBRL element before reconciling.

## How it is tested

`tests/unit/test_screener_export.py` (real export) and `tests/unit/test_recorded_sources.py` (XBRL vs Screener tie-out, the definition gap, and the Dec 2024 cut-off).
