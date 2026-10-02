# Golden fixtures (L3)

Parsed facts (`facts.json`) from the Screener exports of HDFCBANK, INDIGO (Interglobe Aviation) and M&M. The exports themselves are not committed (source terms, plan 13 §8.0c); `MANIFEST.sha256` records each export's hash. Rebuild with `python tools/make_golden_facts.py ISIN export.xlsx`.
`tests/golden/test_golden_stocks.py` runs the real Phase 2 pipeline on the real fundamentals with deterministic
synthetic prices (so the run is repeatable offline) and pins the verdict and score bands.

These are **regression baselines**, not accuracy checks: the UAT-0 analyst oracle is not available yet, and the synthetic
price level is not the real market price. Replace the expected values with the analyst oracle when UAT-0 lands.
The manifest ties the facts to their export; change a fixture and update the manifest and the expectations together.
