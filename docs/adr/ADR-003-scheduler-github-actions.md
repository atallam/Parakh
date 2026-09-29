# ADR-003: Scheduler: GitHub Actions, Windows Task Scheduler fallback

- **Status:** Accepted (amended 2026-09-27)
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 03 §2; plan 13 D6, D22 (docs/plan/)

## Context
- Runs must happen with the laptop off; the workload is small and free tiers are generous.
- Cron in UTC, the market in IST; runs may start a few minutes late.
- NSE may block cloud IPs (tested in the Phase 0.5 spike).

## Decision
- **GitHub Actions** in the private repo runs the monthly, daily-watch and events jobs and sends notifications.
- **Windows Task Scheduler** is the fallback; a **self-hosted runner on the PC** handles NSE steps if cloud IPs are blocked.
- *(Amended 2026-09-27, D22)* The monthly narrative review runs as `AGENT.monthly_reviewer` inside the GitHub job, not as a Claude scheduled task, because a cloud task can't reach the local-only MCP server (ADR-012).

## Consequences
- ➕ Hands-off, logged, retried, versioned outputs.
- ➖ Actions minutes are tracked in the Sunday heartbeat to stay within the free allowance; secrets come from AWS SSM via OIDC (ADR-009).

## Spike outcome (29 Sep 2026, Phase 0.5 ①)

A GitHub-hosted runner reached NSE's archives (UDiFF bhavcopy, equity list), NSE's announcements and corporate-actions APIs, niftyindices, the BSE bhavcopy, AMFI and Yahoo. Only NSE's quote API and BSE's announcements API refused (403), and neither is needed. **No self-hosted runner is needed**; the fallback stays documented. See `docs/spikes/S1-exchange-access.md`.
