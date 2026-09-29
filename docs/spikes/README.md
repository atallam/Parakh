# Phase 0.5 spike outcomes

| Spike | Outcome | Note |
|---|---|---|
| ① NSE/BSE from a GitHub runner | ✅ Works; no self-hosted runner needed (ADR-003 stands) | [S1](S1-exchange-access.md) |
| ② Concall transcripts (D7) | ✅ 7/7 pilots; MAZDOCK flagged stale | [S2](S2-concall-transcripts.md) |
| ③ Screener export + XBRL | ✅ Parser kept; ⚠️ NSE XBRL feed ends Dec 2024 | [S3](S3-fundamentals.md) |
| ④ Corporate actions | ✅ Adjustment works; ⚠️ splits change the ISIN → `isin_history` | [S4](S4-corporate-actions.md) |
| ⑤ Supabase + Parquet + DuckDB | ✅ All 5 probes on the Supabase stack | [S5](S5-supabase-storage.md) |
| ⑥ Telegram | ✅ Adapter tested; ⏳ live send needs `TELEGRAM_CHAT_ID` | [S6](S6-telegram.md) |
| ⑦ CAS parse | ✅ casparser 1.4.1 on your real CAS, locally | [S7](S7-cas.md) |
| ⑧ Claude Agent SDK | ✅ Install + MCP wiring on the runner; ⏳ one turn needs an API key | [S8](S8-agent-sdk.md) |

No unresolved blocker for Phase 1. Two items wait on keys from you (⑥, ⑧), and two findings (③ integrated filing, ④ ISIN history) become Phase 1 tasks.
