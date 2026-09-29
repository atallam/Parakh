---
title: Storage, Full-Cap Coverage & Holdings
version: 0.13 (`isin_history` table: splits change the ISIN — spike ④, plan 13 v1.19; v0.12: MCP access to holdings: masked by default, CAS never reachable, `parakh_mcp` DB role — plan 15 AG-07; v0.11: D19: CAS and .env stay in OneDrive; v0.10: CAS and .env locations outside OneDrive; v0.9: §3.3 table relabelled, superseded row removed; v0.8: §2.4 THESIS.md schema now lives here; v0.7 baseline: holdings from CAS + cost seed, Supabase from Phase 1, CAS privacy rules — plan 13 D8/D11/P6; v0.6: audit & governance tables → plan 10 §13; v0.4: §1 superseded by plan 06)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
covers: storage options review & recommendation · data model · analysing ALL stocks in a cap · marking owned stocks & quantities
---

# Storage, Full-Cap Coverage and Holdings

## 1. Analysing every stock in a cap: tiered coverage

Covering *all* stocks in a segment changes the scale. Deep analysis (fundamentals, LLM qualitative work and full reports) on hundreds of stocks is slow, costly and noisy. The answer is **tiered coverage**: every stock in the cap gets scored, and the expensive work goes only where it matters.

| Cap | Universe (default) | Approx. size |
|---|---|---|
| Large | AMFI ranks 1–100 | 100 |
| Mid | AMFI ranks 101–250 | 150 |
| Small | **Nifty Smallcap 250 constituents** (liquid, investable) | 250 |
| Small (extended, optional) | AMFI ranks 251–1000, after a liquidity filter (≥ ₹1 Cr average daily traded value) | ~500–700 |

| Tier | Who is in it | What is computed | Output |
|---|---|---|---|
| **A: Deep** | **Stocks you own** + **My Watchlist** + **System Watchlist** (plan 06) | Everything: all lenses, qualitative (BSE-filed transcripts, thesis-aware), devil's advocate, full monthly report, event watcher | Stock folder with report, history and thesis |
| **B: Screen** | **Every stock in the cap universe** | All quantitative lenses (value + momentum scores, vetoes, signals); **no LLM** | One row per stock in the **segment ranking table** + database; daily momentum watch |
| **C: Discovery** *(optional)* | Extended small-cap universe | Momentum signals + liquidity + veto checks only | "New names entering Stage 2" digest |

**Moving between tiers (v0.4): replaced by plan 06.** The earlier tier-promotion rules are now the **System Watchlist**. Additions come from 4 sources (top combined score, momentum setup, value BUY zone, smart-money events). Removals are automatic but capacity-limited, with a minimum stay and a one-in-one-out rule. Your **My Watchlist** is never changed without your approval. Tier A = owned + My Watchlist + System Watchlist. Changes appear in the segment summary and in the monthly watchlist review.

Run it as:

```powershell
python run.py --mode monthly --cap mid                 # all 150 midcaps scored; deep dives for Tier A
python run.py --mode monthly --cap small --extended    # + Tier C discovery
python run.py --mode monthly --cap all --only-owned    # quick refresh of just your holdings
```

**Segment summary layout** (`mid_cap/_SEGMENT_SUMMARY/2026-09.md`):

1. **Your holdings in this cap**: 🟢 OWNED badge, quantity, value, P&L, weight, verdict, and any action flags ("owned but SELL-rated", "LTCG in < 30 days").
2. **Best opportunities you don't own**: top 15 by combined verdict.
3. **Full ranked universe**: all 150 rows (score, view, key metrics, signals). This also exists as CSV and XLSX for sorting.
4. Regime, breadth, sector heat-map, **watchlist changes** (auto-added, auto-removed, pending your review), and new red flags.

---

## 2. Marking owned stocks and quantities

### 2.1 How holdings get in (pick one or more)

> **Locked (plan 13 D8):** the **CAS statement** (NSDL/CDSL) is the source of truth for quantities, parsed locally with `casparser` (MIT), which returns holdings per demat account **without transactions or cost**. Cost basis comes from a **one-time seed** (broker tradebook / tax P&L export, or `parakh holdings add`). Each new CAS is compared with the stored lots, and any quantity change creates a "complete this trade" prompt (price and date). Until you complete it, P&L and the LTCG timer show **cost pending**. Trades between statements can be entered with the CLI; the next CAS reconciles them. The other methods below remain available as fallbacks.

| Method | Effort | Notes |
|---|---|---|
| **Broker holdings import** (e.g. Zerodha Console / Groww / Upstox holdings CSV or XLSX export) | 1 minute per month | `python run.py holdings import --broker zerodha --file holdings.xlsx`. Each broker has an adapter, the same pattern as data sources |
| **CAS statement** (CDSL/NSDL consolidated account statement PDF) | 2 minutes | Covers all demat accounts in one file; a PDF parser adapter |
| **CLI** | Instant | `python run.py holdings add TCS --qty 10 --price 3450 --date 2026-09-01 --account zerodha` |
| **Streamlit editor** (Phase 6) | Easiest to use | Editable table (`st.data_editor`) with ISIN lookup, validation and save |
| **WealthLens sync** | Zero once built | Read the holdings table from the WealthLens Supabase DB, so portfolio data has a single source of truth |

### 2.2 Holdings model: tax-lot level (needed for capital-gains accuracy)

```yaml
# config/holdings.yaml  (stored encrypted as holdings.enc.yaml — see §4)
accounts: [zerodha, hdfc_sec]
lots:
  - isin: INE467B01029     # illustrative
    symbol: TCS
    account: zerodha
    qty: 10
    buy_price_inr: 3450.00
    buy_date: 2026-09-01
    tags: [core]           # core / satellite / tracking
    target_weight_pct: 5
    thesis: large_cap/TCS/THESIS.md
```

Derived automatically for each stock:

- Total quantity, average cost, market value, unrealised P&L, portfolio weight.
- **Lot-wise holding period**, days until each lot turns long-term, and the tax estimate if sold now. Shares in demat are treated **first-in, first-out** for capital gains. Tax rates live in config, so they can be updated when budgets change.
- Sales are recorded as transactions, so realised P&L and history stay correct (`holdings sell TCS --qty 4 --price 3900 --date …`).

### 2.3 How ownership changes the analysis

| Where | Owned stock | Not owned |
|---|---|---|
| Coverage tier | Always Tier A (deep) | A if on My or System Watchlist, otherwise B |
| Verdict wording | Action on a position: **ADD / HOLD / TRIM / EXIT** | Entry wording: **BUY / WATCH / AVOID** |
| Alerts | **Exit and warning** signals (M11, M20–M28, red-flag events) go out immediately | **Entry** signals go into the daily digest |
| Report | Position box, tax note, thesis check, stop levels based on *your* entry | Entry zone and suggested initial stop |
| Segment summary | "Your holdings" section at the top | Opportunities section |
| Portfolio checks | Sector concentration, single-stock weight limit, correlated clusters, total exposure by verdict | — |

---

### 2.4 THESIS.md: the structured thesis (locked, plan 13 D13)

*(v0.8: moved here from the archived Drishti review, plan 11 §4, so the schema has a live owner.)*

- **Where it lives:** one THESIS.md per stock, in the repo's cap folder (`large_cap/<SYMBOL>/THESIS.md`, plan 00 §4). The pipeline **never writes it** (AC-F09.4). You write it by hand or through the Streamlit thesis form (plan 12 §5.3).
- **What the pipeline does with it:** reads it, and writes thesis *state* into the snapshot and the audit trail (`AUD.THESIS.*`).
- **Validation:** the front matter validates against this schema (AC-F09.9), and a pre-commit hook rejects any change to `original` after the first save.

```markdown
---
symbol: NTPC
isin: INE_XXXXXXXXX            # illustrative
thesis_version: 1
original:                       # locked: pre-commit hook rejects edits once saved
  written_on: 2024-01-15
  statement: >
    Primary beneficiary of India's 500 GW renewable target through FY28;
    government power-infra capex growing 20%+ a year.
key_metrics:                    # max 5; the concall agent reports on each, every quarter
  - {id: KM1, text: "Renewable capacity addition per quarter (GW)"}
  - {id: KM2, text: "PGCIL order inflow for transmission"}
  - {id: KM3, text: "Fuel cost per unit (coal linkage stability)"}
breakers:                       # max 5; exit conditions committed in advance
  - {id: BR1, text: "Renewable target cut by more than 30%",        check: llm_flag}
  - {id: BR2, text: "Private sector wins most new capacity awards",  check: llm_flag}
  - {id: BR3, text: "Revenue growth below -10% YoY",                 check: metric,
     rule: "revenue_growth_yoy_pct < -10"}
sizing_rationale: "Core position, ~8%. Add on thesis confirmation."
review_by: 2027-01-31
---
## Working thesis (editable prose)
…
```

**Status rules (locked, plan 13 D13):**

| Input | Can set | Why |
|---|---|---|
| `check: metric` breaker, evaluated in Python | **BROKEN** | Deterministic and replayable |
| LLM `component_assessment` = STRESSED | **WATCH** + `FLAG.thesis_review` | The LLM informs, it doesn't decide |
| LLM `breaker_checks.triggered` (`llm_flag`), or `component_assessment` = BROKEN | **WATCH** + a 🔴 review flag with the verbatim quote; **BROKEN only after you confirm** | In Drishti, a guidance score < 4 alone produced BROKEN → EXIT. Here that becomes a flag for you, in line with NFR-02 and AC-F06.1 |
| Owner confirmation or override | Any status, with a reason and expiry | Plan 10 overrides |

A component-by-quarter history comes from the audit events, which drives the thesis heatmap (`UI.thesis_heatmap`, plan 12 §4).

---

## 3. Storage review and recommendation

### 3.1 What needs storing

| Data | Volume (full-cap, 10 years) | Access pattern |
|---|---|---|
| Daily prices and volumes | ~500–1,000 stocks × ~2,500 days ≈ 1–2.5M rows | Bulk time-series scans |
| Fundamentals (quarterly, bitemporal, long format) | ~1,000 stocks × 40 quarters × ~150 fields ≈ 6M rows | Point-in-time lookups |
| Monthly lens results and metric snapshots | Small, but growing forever | Trend queries, history rendering |
| Signals and events | Small | State diffing, de-duplication |
| Holdings and transactions | Tiny, **sensitive** | CRUD |
| Documents (concall transcripts, annual reports) | GBs of PDFs/text | Retrieval, semantic search |
| Reports (md/json) | Small | Human reading |

### 3.2 Options compared

| Option | Strengths | Weaknesses | Fit |
|---|---|---|---|
| **JSON / CSV / MD files only** (plan v0.1) | Simple, readable, git-diffable | Slow and awkward across hundreds of stocks; no joins; no concurrency | ✅ Keep as **rendered outputs** only |
| **Parquet files (partitioned) + DuckDB** | Columnar and fast; zero server; SQL over files; ideal for prices and analytics; free | Local; weak concurrent writers; not a web-app backend | ✅ **Analytical store** for prices, fundamentals and features |
| **SQLite** | Simple, transactional | Corrupts easily under OneDrive sync; slow on analytics | ⚠️ Only outside OneDrive |
| **Supabase (Postgres)** | You already use it (WealthLens); reachable from GitHub Actions, Streamlit and WealthLens; auth + RLS for holdings; **pgvector** for concall search | Free-tier limits (DB size; free projects pause after a period of inactivity, which the daily jobs prevent); network dependency | ✅ **Operational store** for holdings, snapshots, signals, events and documents |
| **Cloud object storage** (Cloudflare R2 / S3 / Supabase Storage) | Cheap storage for PDFs and raw files | Another service to manage | ✅ For raw documents (Supabase Storage is simplest) |
| **Time-series DB** (TimescaleDB / InfluxDB / QuestDB) | Built for ticks | Overkill for daily bars | ❌ Not needed unless you go intraday |
| **Dedicated vector DB** (Pinecone, Qdrant) | Scale | pgvector covers this use case | ❌ Not needed |

### 3.3 Recommendation: a phased hybrid behind one interface

| Scope | Store | Holds |
|---|---|---|
| **All runs (locked, plan 13 D11)** | **Supabase Postgres** (operational; dedicated `parakh` project, RLS on) + **Parquet in Supabase Storage** (bulk prices) queried by **DuckDB** | Holdings, lens results, metric snapshots, signals and events, runs, audit, documents and embeddings in Postgres; price history as Parquet |
| **Local dev and tests** | **Parquet + DuckDB** (outside OneDrive) through `DuckDBRepository` | Fast iteration, fixtures, golden tests |
| **Always** | md/json/csv **rendered** into the cap folders in OneDrive | Human reading and git history |

All code talks to a **`Repository` interface** (`storage/base.py`) with `DuckDBRepository` and `SupabaseRepository` implementations. Switching is a config change, recorded as ADR-004.

**Bonus from Supabase + pgvector:** a "Concall Q&A agent". For example, *"What has Polycab management said about margins over the last 8 quarters?"* is answered from embedded transcripts with citations, the RAG pattern already on your WealthLens backlog.

### 3.4 Core data model

| Table | Key columns | Notes |
|---|---|---|
| `securities` | **isin (PK)**, symbol, name, sector, industry, listing_date, status | Never deleted (survivorship) |
| `symbol_history` | isin, symbol, valid_from, valid_to | Renames |
| `isin_history` *(v0.13, spike ④)* | old_isin, new_isin, changed_on, reason | A split or face-value change issues a new ISIN (MAZDOCK: INE249Z01012 → INE249Z01020 on 27 Dec 2024); adapters resolve through it |
| `corporate_actions` | isin, ex_date, type, ratio | Splits, bonuses, demergers |
| `cap_classification` | isin, effective_date, amfi_rank, bucket | Semi-annual AMFI history → migrations |
| `index_membership` | index_id, isin, valid_from, valid_to | Point-in-time constituents |
| `prices_daily` (Parquet) | isin, trade_date, o/h/l/c, adj_close, volume, delivery_qty | Partitioned by year |
| `fundamentals` | isin, metric_id, period_end, **reported_on**, value, source, version | Bitemporal, long format |
| `documents` | doc_id, isin, type (concall/AR/presentation), period, source_url, sha256, storage_path | BSE-filed transcripts via Screener's Concalls list (D7) + other exchange filings |
| `doc_chunks` | doc_id, chunk_no, text, embedding (pgvector) | Phase 4+ |
| `runs` | run_id, mode, cap, started_at, finished_at, framework_version, config_hash, status | Reproducibility |
| `metric_values` | run_id, isin, metric_id, value, source, asof | Everything the lenses used |
| `lens_results` | run_id, isin, lens_id, lens_version, score, subscores (json), view, confidence | One row per lens |
| `verdicts` | run_id, isin, verdict, confidence, prev_verdict, drivers (json) | Output of the policy engine |
| `signal_state` / `signal_events` | isin, signal_id, state, first_seen, confirmed_on, severity, notified_at | Watcher state and de-duplication |
| `holdings_lots` / `transactions` | lot_id, isin, account, qty, price, date, side | **RLS-protected**, encrypted at rest |
| `journal` | isin, date, action, reason, expected, review_on | Decision journal |
| `guidance` | isin, metric, target, period, said_on, source | From the concall pipeline |
| *Audit & governance tables* | `audit_events` (append-only, hash-chained), `run_steps`, `llm_calls`, `alerts_log`, `verdict_explanations`, `overrides`, `model_inventory`, `config_versions`, `sources`; *(v0.12)* `mcp_tool_calls`, `proposals`, `notify_queue`, `job_requests` | **See plan 10 §13** |

---

## 4. Security of holdings data

- **Local and git:** `holdings.enc.yaml` is encrypted with **sops + age** (or `age` alone); the decryption key lives in `.env` locally and in AWS SSM for Actions (ADR-009). The plaintext file is git-ignored.
- **Supabase:** holdings tables use Row-Level Security bound to your user; the service key exists only in AWS SSM (ADR-009) and your local `.env`.
- **Reports:** reports in a *shared* location can hide quantities and values (`privacy.mask_positions: true` shows weight % only).
- **LLM calls:** send holdings to the LLM only when needed (e.g. the thesis check), and never your whole portfolio.
- *(v0.7, plan 13 P6)* **CAS statements:** parsed locally, in memory. Only ISIN, quantity and an account alias are persisted. PAN, name, address and DP/client IDs are never stored, logged or sent to an LLM (hashed only if needed for de-duplication). CAS files are never uploaded to storage the app writes to (Supabase, GitHub). *(v0.11, plan 13 D19)* Your CAS PDFs and `.env` stay in OneDrive (`Stock Analysis\FILES FOR ANALYSIS\` and `Stock Analysis\.env`); the code reads them through `cas.inbox_dir` and `PARAKH_ENV_FILE`, so neither is ever inside the repo, and the `Stock Analysis` folder is never shared as a whole. The CAS password lives in the secret store (ADR-009), and the redaction test includes PAN and DP-ID patterns.
- *(v0.7)* **Secrets:** the decryption key and the Supabase service key live in AWS SSM Parameter Store, read via OIDC in GitHub Actions (ADR-009), and in `.env` locally.
- *(v0.12, plan 15 AG-07)* **Agents and MCP:** holdings reach agents only through `portfolio.*` tools, which return weights, P&L % and LTCG days, never quantities, costs or ₹ values. `detail: true` is honoured only for your own local Claude Desktop / Claude Code session. No tool reads CAS files or CAS-derived identifiers. The server connects with the `parakh_mcp` database role, which can read the read models and insert proposals, but can't read `restricted` data or update or delete anything. Snapshots exposed as `parakh://` resources are the masked versions.
