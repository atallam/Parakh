# ADR-007: Audit and governance: append-only, hash-chained audit events

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 10 §15 (docs/plan/)

## Context
- Every verdict, alert and change must be explainable and replayable; logs alone are neither queryable nor tamper-evident.

## Decision
- One append-only `audit_events` store: a Postgres trigger rejects UPDATE, DELETE and TRUNCATE; RLS allows INSERT and SELECT only.
- **Hash chain:** `record_hash = sha256(prev_hash + canonical_json(record))`; a daily integrity check; daily chain heads anchored in git.
- **Outbox:** events go to a local JSONL outbox first, then to Postgres; a run can't finish SUCCESS while events are unsynced (`SUCCESS_AUDIT_PENDING`).
- Step ledger + run manifests for replay; metric-level lineage; prompt registry with an eval gate; PR-only config changes.
- Phase 0 implementation: `src/parakh/audit/` (context, events, emit, steps, manifest), `parakh audit verify`.

## Consequences
- ➕ Cheap tamper evidence; "why did it say BUY in March?" always has an answer.
- ➖ Small write overhead and audit wiring in every service, mitigated by `audited_step`, `run_lifecycle` and a test sweep.
