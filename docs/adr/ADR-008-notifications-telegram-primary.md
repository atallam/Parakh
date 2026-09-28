# ADR-008: Notifications: Telegram primary, email archive

- **Status:** Accepted (amended 2026-09-27)
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 03 §4; plan 13 D5 (docs/plan/)

## Context
- Alerts need buttons (approve, useful/noise, mute) and commands, at any time, for one user.
- WhatsApp needs approvals, a dedicated number, templates and a public webhook.

## Decision
- **Telegram** is primary (alerts, digests, approvals, feedback); **email** carries the monthly archive and full review; **ntfy** is an optional loud lane (off at baseline); **WhatsApp deferred** behind the same `Notifier` interface.
- *(Amended 2026-09-27)* The Claude push lane is retired; the Monthly Reviewer agent's output goes to Telegram + email. Agents never call a channel directly: they use `notify.queue`, which applies routing, de-duplication, cool-downs and masking (AG-05).

## Consequences
- ➕ Free, two-way, set up in minutes (bot @Parakh_avinash_bot is live).
- ➖ Another app to keep; mirrored to WhatsApp only if an ADR-008 revisit trigger fires.
