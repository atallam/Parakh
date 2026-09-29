# Spike ①: NSE and BSE access from a GitHub-hosted runner

- **Date:** 29 Sep 2026 · **Run:** GitHub Actions `spikes` run 36515232909 (ubuntu-latest) · **Script:** `spikes/s1_exchange_access.py`
- **Question:** can scheduled jobs on GitHub's cloud runners fetch the exchange data Parakh needs, or do NSE steps need a self-hosted runner on the PC (plan 04 §4 #2)?

## Result

| Source | Result | Notes |
|---|---|---|
| NSE UDiFF bhavcopy (`nsearchives…/BhavCopy_NSE_CM_0_0_0_<date>_F_0000.csv.zip`) | ✅ 200, 206 KB | All 7 pilot ISINs present (series EQ) |
| NSE equity list (`EQUITY_L.csv`) | ✅ 200 | Symbol → current ISIN for every pilot |
| NSE `/api/corporate-announcements` | ✅ 200, 1.6 MB for HDFCBANK | Works **without** the homepage cookie step (homepage itself returned 403) |
| NSE `/api/corporates-corporateActions` | ✅ 200 | Carries ex-date, record date, face value, ISIN |
| NSE `/api/quote-equity` | ❌ 403 | Not needed: prices come from bhavcopy / Yahoo |
| niftyindices constituents (Nifty 100, Midcap 150, Smallcap 250) | ✅ 200 | CSV with `ISIN Code` |
| BSE UDiFF bhavcopy | ✅ 200 | Same column layout as NSE, so one parser |
| BSE announcements API | ❌ 403 | Same as Drishti's finding on 24 Sep; announcements come from NSE |
| AMFI categorisation page + latest list (30 Jun 2026) | ✅ 200 | xlsx link found on the page (`portal.amfiindia.com/spages/…`) |
| Yahoo via yfinance (`HDFCBANK.NS`, `M&M.NS`, `MAZDOCK.NS`) | ✅ 22 rows to 28 Sep 2026 | |

From the Claude workspace and your PC's workspace (both behind filtering proxies) NSE was blocked, which is why the runner is the test that counts.

## Decision

- **ADR-003 stands: GitHub-hosted runners, no self-hosted runner needed** for Phase 1–3 sources. The self-hosted fallback stays documented in case NSE starts blocking cloud IPs.
- Prices: yfinance primary, **NSE bhavcopy as the T1 cross-check and fallback** (plan 00 §7). Announcements: NSE API (BSE's is closed).

## How these sources are tested (plan 14 §4.2)

Recorded fixtures in `tests/fixtures/sources/{nse,bse,niftyindices,amfi}/` with `tests/unit/test_recorded_sources.py`. The weekly source canary (AC-F19.8, Phase 3) compares live responses with them. Access can change without notice, so the canary also alerts on a status-code change.

## Follow-ups (Phase 1)

- Throttle and cache NSE calls (plan 04 §4 #7); send a browser User-Agent.
- Record an AMFI January list when it arrives (live cap-migration test, AC-F01.2).
