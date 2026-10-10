# UAT-5: v1.0 acceptance (plan 14 §7)

Status: **prepared, not started.** UAT-5 needs three consecutive unattended monthly runs and two months of real use, so it can only be signed by you.
Prepared: 2026-10-11 · Tester: Avinash · Framework: fill in at sign-off

## Before you start

| Check | How | Done |
|---|---|---|
| Historical index constituents imported (10 years) | `uv run parakh calibrate membership-import FILE.csv` (columns: index_id, isin, valid_from, valid_to) | |
| Prices loaded for the whole window, including delisted names | `uv run parakh calibrate panel` finishes without gaps | |
| Three monthly runs in a row ran unattended and passed | Actions history: `monthly` for three consecutive months | |
| `monthly-checks` ran at least once and all three jobs are green | Actions history | |
| `BACKUP_AGE_IDENTITY` secret set (the private age key) | repository secrets | |
| Two months of alerts rated | Calibration page, "Rate alerts" tab | |

## Steps

| Step | What to do | Result |
|---|---|---|
| 1 | `uv run parakh calibrate report --write`; read `docs/calibration/<quarter>.md` top to bottom | |
| 2 | Backtest: confirm the three return series are ordered gross >= after cost >= after tax and the survivorship warning is absent | |
| 3 | Quintiles: for each lens, decide CONFIRM / REVIEW. INSUFFICIENT is acceptable only if the sample warning is correct | |
| 4 | Alert precision: any signal below target with enough ratings gets a tuning ticket or is demoted | |
| 5 | Open `governance/reviews/<quarter>.md` and tick every item | |
| 6 | Sample 10 stocks across the three caps; for each, read the report and say whether the verdict is one you would defend | |
| 7 | Decide the weights: CONFIRMED, or CHANGED (PR, framework version bump, then re-run `parakh run --mode monthly --asof YYYY-MM-DD` for each past month so history is re-scored; there is no bulk re-score command yet) | |
| 8 | Decide ADR-012 (see the ADR) | |
| 9 | PRD §13 release checklist complete; no open S1 or S2 | |

## Sign-off

Weights decision: ______ · Open S1/S2: ______ · Signed: ______ Date: ______
