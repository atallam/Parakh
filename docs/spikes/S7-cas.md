# Spike ⑦: parsing your real CAS locally (D8, P6)

- **Date:** 29 Sep 2026 · **Where:** your PC only; the file never left it. Only structure and counts were printed, never a value.

## Result

- casparser 1.4.1 parses the NSDL CAS (Aug 2026) with 0 warnings.
- 3 demat accounts: 2 NSDL (empty), 1 CDSL with 11 equities and 3 mutual funds. 14 distinct ISINs; **all 7 pilot stocks are held**.
- Equity rows: `name, isin, num_shares, price, value, symbol, exchange`, with numbers as **strings** (parse with Decimal). No cost and no transactions, as plan 13 §4.1 expected, so the one-time cost seed stands.
- Mutual-fund rows do carry `avg_cost`, `total_cost` and `pnl`.
- Personal data in the parsed output: `investor_info.{name, email, address, mobile}` and each account's `dp_id`, `client_id`. PAN is printed in the PDF but is not a parsed field.

## Decision

- The Phase 1 importer keeps only ISIN, quantity and an account alias (P6); every other field is dropped at the parse boundary.
- The synthetic CAS fixtures were regenerated to match casparser's real shape field for field. A rendered PDF isn't generated, because casparser needs the depository's exact layout; the importer is tested at the parsed-dict boundary.
- Add `casparser` as a dependency in Phase 1.
