# ADR-012: MCP transport: local stdio only (for now)

- **Status:** Accepted; revisit in Phase 5
- **Date:** 2026-09-27
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 15 §7, §10; plan 13 D22 (docs/plan/)

## Context
- A holdings-aware service exposed on the internet needs hosting, OAuth and a security review.

## Decision
- `parakh-mcp` runs only as a **stdio subprocess** (Claude Desktop, Claude Code via `.mcp.json`, and inside job runners). It never listens on a network port; a test forbids `bind`/`listen` (AC-F24.6).

## Consequences
- ➕ No attack surface, no hosting cost, no auth to build.
- ➖ No Ask Parakh from phone or claude.ai; the monthly review moved into the GitHub job (ADR-003, ADR-008 amended).
- Revisit (reminder set, Phase 5 before v1.0 GA): Ask Parakh away from the PC, a hosted UI behind a login anyway, or a second user.
