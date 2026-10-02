# Golden fixtures (L3)

Parsed facts (`facts.json`) from the Screener exports of HDFCBANK, INDIGO (Interglobe Aviation) and M&M. The exports themselves are not committed (source terms, plan 13 §8.0c); `MANIFEST.sha256` records each export's hash. Rebuild with `python tools/make_golden_facts.py ISIN export.xlsx`.
`tests/golden/test_golden_stocks.py` runs the real Phase 2 pipeline on the real fundamentals with deterministic
synthetic prices (so the run is repeatable offline) and pins the verdict and score bands.

The verdict and score bands are **regression baselines** on synthetic prices, not accuracy checks. Accuracy is checked against
the analyst oracle: `tests/golden/test_oracle.py` compares the value metrics with `tests/oracles/golden_expected.json`
(built by `tools/compare_oracle.py`; sign-off in `docs/uat/UAT-0_*.md`).
The manifest ties the facts to their export; change a fixture and update the manifest and the expectations together.
