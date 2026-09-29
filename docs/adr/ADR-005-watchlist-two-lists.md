# ADR-005: Watchlist: two lists

- **Status:** Accepted (owner-confirmed)
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 06 (docs/plan/)

## Context
- An automated watchlist is useful but must never silently change the list you curate.

## Decision
- **My Watchlist** changes only with your approval.
- **System Watchlist** is auto-managed and capacity-limited (minimum stay, expiry).
- Promotion from System to My is a suggestion you approve in Streamlit or Telegram. Agents may only propose (AG-03).

## Consequences
- ➕ Automation without losing control; every decision is audited (`AUD.WATCHLIST.*`).
- ➖ Two lists to explain in the UI; the review inbox makes pending suggestions visible.
