# ADR-001: Hybrid output formats: JSON snapshot is canonical

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 00 §3 (docs/plan/)

## Context
- Reports must be readable in OneDrive, VS Code and Obsidian, and usable by code and agents.
- Markdown alone is a poor database (numbers parsed back out of prose tables are fragile); JSON alone is a poor report.
- Hundreds of stocks a month need a queryable store as well (ADR-004).

## Decision
- Each run writes a **Pydantic-validated JSON snapshot first**; it is the source of truth.
- Markdown reports, `HISTORY.md` and `history.csv` are **rendered** from it and never hand-edited.
- From Phase 1 the operational store (ADR-004) holds the same data for queries; files become rendered outputs.

## Consequences
- ➕ One source of truth; any surface can be re-rendered from a snapshot; git diffs of snapshots are meaningful.
- ➖ Every new field needs a schema change and a template change.
- Watch: renderers must never compute numbers (they format only, via `render/format.py`).
