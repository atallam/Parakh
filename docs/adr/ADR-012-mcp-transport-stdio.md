# ADR-012: MCP transport: local stdio only (for now)

- **Status:** Accepted; Phase 5 review prepared, **waiting for the owner's decision** (see "Phase 5 review")
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

## Phase 5 review (prepared 2026-10-11; the decision is yours)

The question: keep the MCP server local, or plan remote access (Ask Parakh from a phone or claude.ai) as a Phase 6 item with its own ADR.

| | Keep local (stdio only) | Plan remote access for Phase 6 |
|---|---|---|
| What it takes | Nothing | Streamable HTTP transport, OAuth, a hosted process, a masked read-only toolset, a security review, a new ADR |
| Exposure | None. The server opens no socket (AC-F24.6) | Holdings-aware data behind an internet login; `portfolio.*` must be masked or left out |
| Cost | None | Hosting plus your time; a second secret store |
| What you give up | Ask Parakh away from the PC | Nothing, once built |
| What Phase 5 shows | The Calibration page, Telegram buttons and the monthly summary already cover the away-from-PC cases that matter (rate an alert, review a journal entry, approve a suggestion) | Only worth it if you find yourself wanting to ask free-form questions on the move |

**Recommendation:** keep it local for v1.0 GA. Nothing in Phase 5 needed remote access, the three away-from-PC actions already have a phone channel, and the first remote tool would be the largest attack surface in the system. Re-open it as a Phase 6 candidate only if, during the two months of real use, you notice yourself wanting to ask questions from the phone and not having an answer. If you do choose remote access, the least risky shape is a read-only `reports.*` and `calibration.*` toolset, with `portfolio.*` and every `P`, `N` and `J` tool left off the remote server.

**To close the review:** reply with "keep local" or "plan remote"; the status above then becomes Accepted (decision date) and plan 13 D22 and plan 09 Phase 6 are updated to match.
