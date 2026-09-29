# Phase 0.5 spikes (plan 09)

Throwaway probes that retire unknowns before Phase 1 builds on them. Each spike writes its raw
results to `spikes/out/<spike>/` (git-ignored; CI uploads it as an artifact) and its conclusion to
`docs/spikes/S<n>-*.md`. Code that survives a spike moves into `src/parakh/` with tests.

| Spike | Script | Where it runs |
|---|---|---|
| ① NSE/BSE access | `s1_exchange_access.py` | GitHub-hosted runner (`.github/workflows/spikes.yml`) |
| ② Concall transcripts | `s2_concalls.py` | Runner and workspace |
| ③ Screener export + XBRL | `s3_fundamentals.py` | Runner (XBRL) and locally (export) |
| ④ Corporate actions | `s4_corporate_actions.py` | Runner |
| ⑤ Supabase + Parquet + DuckDB | `s5_supabase_storage.py` | Runner, against the local Supabase stack |
| ⑥ Telegram | `s6_telegram.py` | Your PC |
| ⑦ CAS parse | `s7_cas.py` | Your PC only (the real CAS never leaves it) |
| ⑧ Claude Agent SDK | `s8_agent_sdk.py` | Runner |

**Status (29 Sep 2026):** ①–⑦ closed. ⑧'s model turn runs on the next push here now that `ANTHROPIC_API_KEY` is a repo secret.
