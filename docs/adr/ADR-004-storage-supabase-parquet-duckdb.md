# ADR-004: Storage: Supabase Postgres for operational tables, Parquet + DuckDB for analytics

- **Status:** Accepted (amended 2026-09-24)
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 05 §3; plan 13 D11 (docs/plan/)

## Context
- Files alone are slow and join-less across hundreds of stocks; SQLite corrupts under OneDrive sync.
- Supabase is already familiar (WealthLens), reachable from Actions and Streamlit, and has RLS for holdings and pgvector for concall search.

## Decision
- **Supabase Postgres** (dedicated `parakh` project, RLS on) holds operational tables **from Phase 1**: holdings, runs, snapshots, signals, events, audit.
- **Parquet in Supabase Storage**, queried by **DuckDB**, holds price history and analytics.
- All code goes through a `Repository` interface (`DuckDBRepository` for local dev and tests, `SupabaseRepository` for runs). Files are rendered outputs (ADR-001).
- Phase 0 ships the first migration (`supabase/migrations/`) with RLS and append-only audit tables; `supabase/tests/` holds the pgTAP checks.

## Consequences
- ➕ One store for every surface; RLS protects holdings; free tier fits the scale.
- ➖ Free projects pause after a week idle (trading-day jobs and the Sunday heartbeat prevent it); no built-in backups on Free, so weekly encrypted `pg_dump` + monthly restore test (P9).
