# ADR-002: Value and momentum scored separately, combined through a decision matrix

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 00 §5 (docs/plan/)

## Context
- Value and momentum answer different questions ("is it cheap?" vs "does the market agree?").
- Averaging them hides the most useful cases: cheap-but-falling (value trap risk) and expensive-but-rising (momentum trade only).

## Decision
- Each lens produces its own 0–100 score. A **decision matrix** (value row × momentum column) gives the verdict; the two scores are **never averaged**.
- Red-flag vetoes override the matrix. Verdicts carry confidence, a delta vs last month, hysteresis (±5 points) and the regime tag.
- *(D24)* A lens without enough history is informational; the verdict says "limited history".

## Consequences
- ➕ Verdicts are explainable cell by cell; new lenses plug in without changing existing scores.
- ➖ The matrix grows with each lens that gets a verdict-policy row; new lenses stay informational for two runs first (plan 04 §1.3).
