# Spike ⑤: SupabaseRepository, Parquet in Storage, DuckDB

- **Date:** 29 Sep 2026 · **Script:** `spikes/s5_supabase_storage.py` · **Where:** GitHub runner, Supabase local stack (same migrations as production)
- **Code kept:** `src/parakh/storage/supabase_repo.py`, `src/parakh/storage/prices.py`

## Result: all 5 probes passed

1. A dummy run with the Supabase audit syncer ends **SUCCESS** (0 pending) instead of SUCCESS_AUDIT_PENDING.
2. Re-sending the same audit events leaves the count at 2: inserts use ON CONFLICT DO NOTHING, never an UPDATE.
3. An UPDATE on `audit_events` through the API is rejected by the trigger (`42501 … append-only`).
4. `runs` and `run_steps` upsert (1 run, 3 steps).
5. Price Parquet (`prices/<ISIN>/<year>.parquet`) round-trips through a private Storage bucket; a fresh cache downloads and DuckDB returns all 20 rows.

## Decision

ADR-004 confirmed as designed. Phase 1 builds on these two modules; the outbox flush (AC-F21.5) is already wired and tested offline (`tests/unit/test_storage.py`).

## Still open (your action)

The real `parakh` project needs `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in `.env` (the service key is missing today) before Phase 1 writes to it.
