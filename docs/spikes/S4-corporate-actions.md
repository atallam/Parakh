# Spike ④: corporate actions on known pilot events

- **Date:** 29 Sep 2026 · **Script:** `spikes/s4_corporate_actions.py` · **Code kept:** `src/parakh/adapters/corporate_actions.py`
- **Events:** MAZDOCK split 1:2 (face value ₹10 → ₹5), ex-date 27 Dec 2024; HDFCBANK bonus 1:1, ex-date 26 Aug 2025.

## Result

- **Yahoo `Close` is already adjusted** for both events (no gap) and reports the bonus as a 2-for-1 "split". Fine as a primary series, but it can't be used to detect actions.
- **NSE bhavcopy is unadjusted:** HDFCBANK closed ₹1,964.10 on 25 Aug and ₹973.40 on 26 Aug (−50.4%). `find_gaps` flags it, the bonus explains it, and `back_adjust` removes it (0 unexplained gaps).
- **Splits change the ISIN.** MAZDOCK was `INE249Z01012` before the split and is `INE249Z01020` now. The bhavcopy lookup by the new ISIN found nothing before 27 Dec 2024, and NSE's corporate-actions feed still labels every record, even 2026 dividends, with the **old** ISIN.

## Decision (Phase 1, within the existing "ISIN master, symbol map, corporate actions" task)

- Add an **`isin_history`** table (old ISIN → new ISIN, change date, reason) beside `symbol_history`; every adapter resolves ISINs through it before keying data.
- Corporate actions come from the NSE feed (T1), mapped through `isin_history`; Yahoo's split list is a cross-check only.
- A >40% one-day move with no matching action blocks the verdict (plan 04 §4 #8), as implemented.

## How it is tested

`tests/unit/test_corporate_actions.py` (factors, gap detection, compounding, demergers refused) and `tests/unit/test_recorded_sources.py::test_split_changed_mazdocks_isin…` against the recorded NSE feed.
