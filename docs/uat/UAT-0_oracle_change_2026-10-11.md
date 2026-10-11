# UAT-0 oracle change: INDIGO lease basis (plan 14 §4.1)

Raised 2026-10-11 · PR #35 (commit "oracle-change") · Owner sign-off required before the 30 Oct 2026 golden freeze.

## What changes in the oracle (`tools/build_oracle.py`, ORACLE_INDIGO)

| Cell / metric | Before | After |
|---|---|---|
| `MET.value.ev_ebitdar` | (mcap + borrowings **+ lease liabilities** − cash) ÷ (TTM operating profit + rentals) | (mcap + borrowings − cash) ÷ (TTM operating profit + rentals) |
| `MET.value.lease_adj_leverage` | (borrowings **+ lease liabilities** − cash) ÷ (TTM operating profit + rentals) | (borrowings − cash) ÷ (TTM operating profit + rentals) |
| Input B59 label | Aircraft and engine rentals, FY26 | Aircraft and engine rentals, last 4 quarters (TTM) |
| Input B58 label | Lease liabilities, FY26 | Lease liabilities, latest balance sheet (a memo; already inside Screener Borrowings) |

## Why

Screener's INDIGO `Borrowings` at 31 Mar 2026 is 77,749.2 ₹ Cr (777,492 ₹ mn). The filed lease liabilities are 75,942.9 ₹ Cr (non-current 64,470.5 + current 11,472.4 → 75,942.9). Leases are about 98% of Screener's borrowings, so the line already contains them (Ind AS 116). Adding them again counts about 75,900 Cr of debt twice. Rentals are a quarterly flow in the filings, so the lease cost must be summed over four consecutive quarters; FY26 was 2,084.7 Cr and TTM to Jun 2026 is 2,131.9 Cr (T2, to verify).

## Code that follows

`borrowings_include_leases: true` in `config/value.yaml`; the airline metrics then do not add the filed leases, and return N/A if a filed lease balance ever exceeds borrowings. Tests T-VAL-45…49.

## Effect on the freeze

The two INDIGO cells are still "INPUT NEEDED" in the workbook, so no frozen oracle value moves. Re-run `tools/compare_oracle.py` with the three Screener exports after merge; the INDIGO lease rows then fill from B58/B59.

## Sign-off

I have read the formulas in words and agree the leases must not be added twice.

Signed: ______  Date: ______
