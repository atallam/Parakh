---
title: Integration with WealthLens Hub, and what to reuse from Drishti
version: 1.1 (new: D28, ADR-015; Drishti re-assessed after D26)
date: 2026-10-14
owner: Avinash Tallam
parent: 00_MASTER_PLAN.md
owns: the integration contracts (`holdings.v1`, `insights.v1`), the `HoldingsProvider` and `InsightPublisher` interfaces, how Parakh and WealthLens Hub exchange data, what each side must build, the Drishti reuse assessment and recommendation, and ADR-015. Phase placement lives only in plan 09; decision D28 lives only in plan 13
related: 05 §2 and §4 (holdings and privacy), 15 (agents, MCP), 16 (Hub holdings contract, staging), 17 (coverage), archive/11 (the September Drishti review), 13 D8/D16/D22/D26/D27/D28
reviewed: "Web Applications/Drishti 2.0" (code last changed 18 May 2026), "Web Applications/Drishti" (v1), the `atallam/wealthlenshub` repo (main, pushed 13 Oct 2026), Drishti's V2 direction document
---

# Integration with WealthLens Hub, and what to reuse from Drishti

# Part I: Integration with WealthLens Hub (and other tools)

## 1. What Hub is, as found in the repo

Facts below are from reading `atallam/wealthlenshub` on 14 Oct 2026, not from memory.

| Area | Finding |
|---|---|
| Stack | Node/Express server on Render, Supabase Postgres, React front end; numbered migrations up to 0032 |
| Holdings | A `holdings` table with `isin`, `type` (IN_STOCK, IN_ETF, MF and others), units, prices, `holding_status` (active or exited) and a CAS natural key (user, member, depository, account, isin; migration 0029). A transaction ledger exists (0030, 0031) |
| Imports | CAS (NSDL, CDSL, CAMS, KFintech) through casparser, a Gmail auto-import, broker routes (SnapTrade, Setu, Plaid) |
| Auth | Every API route needs a logged-in user's Supabase JWT (`lib/auth.js`). There is no machine-token route. Row-level security is enabled on `holdings` in the later migrations, but the server connects with the Supabase service key, which bypasses it, and filters by `user_id` in code |
| AI | An Advisor with an in-process tool-use loop (`routes/ai.js`, `services/ai-tools.service.js`), a Claude-based concall analyser (`routes/concall.js`, `lib/concall/trend.js`, migration 0012), a watchlist, alerts and notifications |
| MCP | None. A search for MCP code in the server, libs, routes and services found nothing |
| Backlog | Hub's own backlog lists a Python/LangGraph "Portfolio Advisor Agent" microservice and a weekly copilot digest. Both overlap Parakh's agent layer (section 7) |
| Visibility | The repo is **public**. Contract documents are fine to publish; passwords, tokens and role names with secrets are never committed there |

## 2. Principles

1. **Single writer.** Hub owns holdings across all asset classes. Parakh owns analysis (verdicts, scores, theses, exposures). Neither writes the other's tables.
2. **Contracts, not coupling.** The two systems meet at two small, versioned, ISIN-keyed contracts. Each side can change inside without breaking the other until a contract's major version changes.
3. **No shared secrets.** Never copy Hub's Supabase service key into Parakh, or the reverse. Each direction gets its own read-only credential.
4. **Masked by default.** What Parakh publishes carries weights and percentages, never quantities or rupee amounts (AG-07). What it reads may carry quantities, and stays in Parakh's private store.
5. **MCP is the agent and human layer, not the pipeline.** `parakh-mcp` stays local (ADR-012). Scheduled jobs exchange data through the contracts. A hosted `wealthlens-mcp` can be added later without changing them.
6. **Tool-agnostic.** The contracts name no application. Any tool that can read a database view or a JSON file can consume `insights.v1`; any source that can produce `holdings.v1` can feed Parakh.

## 3. The contracts

Both are Pydantic models in `src/parakh/contracts/`, exported as JSON Schema to `docs/contracts/`, versioned with SemVer, and covered by golden-file contract tests. A breaking change bumps the major version and runs the old and new side by side for one cycle.

### 3.1 `holdings.v1` (into Parakh)

| Field | Type | Notes |
|---|---|---|
| `schema_version` | string | `holdings.v1` |
| `isin` | string | Join key. ISO 6166 check digit validated |
| `symbol`, `name` | string | For display; never a key |
| `instrument_type` | enum | `IN_STOCK`, `IN_ETF`, `MF`, `US_STOCK`, `US_ETF`, `CRYPTO`, `BOND`, `OTHER`. Parakh scores `IN_STOCK` only; `IN_ETF` is price-tracked; the rest are listed as "not analysed" |
| `currency` | string | ISO 4217 |
| `status` | enum | `active` or `exited`. Exited holdings leave the coverage set |
| `quantity`, `avg_cost` | number, optional | Private fields. Stored only in Parakh's holdings tables; never in `insights.v1` |
| `account_alias`, `member_alias` | string | Hashed or aliased. PAN, names, addresses and DP or client IDs never cross (P6) |
| `as_of` | date | Statement or sync date |
| `source` | string | `cas`, `hub`, `manual` |

### 3.2 `insights.v1` (out of Parakh)

One record per ISIN in the coverage set per period. All fields are masked.

| Field | Notes |
|---|---|
| `schema_version`, `isin`, `symbol`, `period`, `as_of`, `run_id`, `framework_version` | Identity and lineage |
| `verdict`, `verdict_prev`, `verdict_since` | Owned wording: ADD, HOLD, TRIM, EXIT |
| `value` | `score`, `band`, `confidence`, `profile`, `history_class`, `view` |
| `momentum` | `score`, `band`, `confidence`, `stage`, `rs_percentile`, `regime` |
| `thesis` | `status` (INTACT, WATCH, BROKEN, NOT SET), `flags[]`, `review_by` |
| `qualitative` | `status` (ok or pending), a one-paragraph summary, guidance-vs-delivery, `confidence_delta`, `unverified_quotes` count |
| `risks[]` | Top three flags with severity |
| `next_event` | Type and date |
| `position` | `weight_pct`, `xirr_vs_benchmark_pp`, `ltcg_days`. No quantity, cost or rupee value |
| `data_quality` | Score and the worst warning |
| `case_file_ref` | Pointer to the full case file (plan 15 §5b) |

## 4. Interfaces and providers

```python
# src/parakh/contracts/ and src/parakh/integrations/
class HoldingsProvider(Protocol):
    def list_holdings(self, asof: date) -> list[HoldingV1]: ...


class InsightPublisher(Protocol):
    def publish(self, insights: list[InsightV1], run: RunContext) -> PublishReceipt: ...
```

| Implementation | Direction | Status |
|---|---|---|
| `CasHoldingsProvider` | In | Wraps today's CAS import and lot model (D8). Stays the default through GA |
| `FakeHoldingsProvider` | In | Fixtures for tests |
| `HubHoldingsProvider` | In | Reads Hub's `parakh_holdings_v1` view with a read-only role (section 5). Built after GA |
| `McpHoldingsProvider` | In | Wraps a hosted `wealthlens-mcp`. Only if Hub ever hosts one |
| `FilePublisher` | Out | Writes `insights_<period>.json` beside the reports. Default, first |
| `SupabaseViewPublisher` | Out | Upserts into an `insights_v1` table in Parakh's own Supabase project, exposed as the `parakh_insights_v1` view for a read-only role |
| `HubHttpPublisher` | Out | POSTs to a Hub route with a machine token. Only if Hub adds that route |

Selection is config: `integration.holdings_provider` and `integration.publishers[]`. Both default to today's behaviour, so nothing changes until you switch them on.

## 5. How the data moves

| Option | How | Pros | Cons | Verdict |
|---|---|---|---|---|
| **A. Read-only database views with scoped roles** | Hub exposes a `parakh_holdings_v1` view (active listed-equity and ETF rows for your user, contract columns only) and a role `parakh_reader` with `SELECT` on it. Parakh exposes `parakh_insights_v1` and a role for Hub the same way | No new API code or auth in Hub; works with Hub's JWT-only API; credentials per direction; the view is the contract | Network access from GitHub Actions to Hub's Postgres; the view must be maintained when Hub's schema moves | **Recommended** |
| B. HTTP routes with a machine token | Hub adds `/api/integrations/*` with a hashed, rotating token | Explicit, easy to rate-limit | New code and auth paths in Hub; Hub's public repo shows the surface | Fallback |
| C. MCP | A hosted MCP on Hub | Natural for agents | Hub has none; scheduled jobs would need a remote client; `parakh-mcp` is local stdio (ADR-012) | Agent layer only, later |

### Exchange sequence (option A)

```
 Hub (Render, Supabase A)                          Parakh (GitHub Actions, Supabase B)
 CAS / broker / Gmail imports                       monthly run, watchers, orchestrated agents
        │ holdings (all asset classes)                         │
        ▼                                                     │ reads, SELECT only
 parakh_holdings_v1 (view) ───────────────────────────────────►  HoldingsProvider → coverage set
                                                              │
                                                              ▼ analysis → case files
 Hub Advisor, holding cards, concall panel  ◄─────────────── parakh_insights_v1 (view)  ◄── InsightPublisher
        (read-only role, masked)
```

## 6. What each side must build

**Parakh (plan 09 R8, R9):**
- Contract models, JSON Schemas, golden-file tests, and the provider and publisher interfaces with the CAS, Fake and File implementations (R8, before any Hub work).
- `HubHoldingsProvider`, `SupabaseViewPublisher` and the role and view migrations (R9, after GA).
- A contract-version check at job start: refuse to run if the Hub view's declared version is not one Parakh supports.

**Hub (not done here; listed so the work is visible in Hub's own backlog):**
- H1: the `parakh_holdings_v1` view and the read-only role, filtered to the configured Hub user. Hub's server bypasses row-level security with its service key, so the view must hard-filter by `user_id` itself and the role must not be able to see other users' rows.
- H2: an Advisor tool `get_parakh_insights` that reads `parakh_insights_v1`, so the Advisor answers with Parakh's verdicts and thesis status.
- H3 (optional): a verdict chip on the holding card and a thesis-check strip in the concall panel, read from `insights.v1`.
- H4: decide the overlaps in section 7.

## 7. Overlaps to settle at the M1 review

These extend the five decisions in plan 16.

| Overlap | Recommendation |
|---|---|
| **Concall analysis.** Hub has a Node, Claude-based analyser with 0 to 10 scores; Parakh's F06 is thesis-aware, quote-verified and flags only | For stocks in the coverage set, Parakh's F06 is authoritative and Hub *displays* it through `insights.v1`. Hub's analyser stays for holdings Parakh does not cover. Retire it only after UAT |
| **Advisor agents.** Hub's backlog has a LangGraph Portfolio Advisor Agent (P3 item 10) and a weekly copilot | Do not build a second orchestrator in Hub. Make Hub's Advisor a *client* of `insights.v1`, and let Parakh's orchestrator (plan 15) own the multi-step analysis of listed equities. Hub's agents keep what only Hub can see: budget, FDs, MFs, tax |
| **Watchlist.** Hub has one; Parakh's is parked (D26) | Leave Hub's alone |
| **CAS import.** Both import CAS | Parakh keeps its own path through GA (D8). After GA, `HubHoldingsProvider` can replace it and Parakh's importer becomes a fallback |
| **Mutual funds, FDs, US stocks, crypto** | Hub owns them. A fund lens in Parakh (plan 16 item 4) is a post-GA decision; Parakh would read funds through `holdings.v1` |

## 8. Phasing

Placement and dates are in plan 09 (R8 and R9). In short: contracts and the Fake, CAS and File implementations are cheap and land early so the seam exists before anything depends on it; the Hub-side view, role and Advisor tool come after GA, behind `integration.*` flags, with the outputs shown to you in shadow before Hub reads them.

## 9. Architecture decision

### ADR-015: Integration through versioned, ISIN-keyed contracts and database views

- **Status:** Accepted 2026-10-14 (plan 13 D28).
- **Context:** you want Parakh to integrate easily with WealthLens Hub (and other tools) once it is built. Hub's API accepts only a user JWT, has no MCP, and its repo is public; Parakh's MCP server is local-only (ADR-012).
- **Decision:** two versioned contracts (`holdings.v1` in, `insights.v1` out), two small interfaces (`HoldingsProvider`, `InsightPublisher`), and read-only database views with scoped roles as the default exchange. Single-writer rule. CAS stays Parakh's source through GA.
- **Alternatives considered:** merging Parakh into Hub (undecided on 11 Oct; rejected here because Hub's Node stack, JWT-only API and holdings focus do not fit a Python, audit-heavy analysis engine, and a merge would drag Hub through Parakh's governance); HTTP routes with machine tokens (more Hub code and a visible attack surface); making MCP the integration path (Hub has none and scheduled jobs cannot reach a stdio server).
- **Consequences:**
  - ➕ Either system can be rebuilt or replaced without touching the other, and a third tool can use the same contracts.
  - ➕ Nothing changes for you until the flags are switched on.
  - ➖ Two schemas to keep stable; mitigated by the contract tests and `_v1` view names.
  - ➖ Hub's database becomes reachable from Parakh's runner; mitigated by a view-only role, SSM-held credentials and a quarterly rotation.
  - **Revisit when:** Hub gains a machine-token route or an MCP server, a third consumer appears, or the M1 review decides inbound access to Parakh (plan 16 item 5).

---

# Part II: What to reuse from Drishti

## 10. Where Drishti stands

| Item | Finding |
|---|---|
| Last change | Code last modified 18 May 2026; nothing since |
| Size | About 9,000 lines of Python (engines, services, routers), a React front end, eight design documents, 199 tests (September review: 197 pass) |
| Data | One holding, no thesis history, no concall analyses (September review; `drishti.db` is unchanged) |
| Known defects | Fails-open red flags, dead transcript providers, a 500 on the portfolio summary, card and drawer disagreeing, a 5-second verdict call (September review, archive/11 §2) |
| North star (V2 direction document) | *"For every position I hold, is the story I bought still intact, what has changed since I bought it, and does my current size make sense?"* with allocation as the **output** of the verdict, not its driver |

**You are right: after D26, Parakh and Drishti ask the same question.** Before D26 they differed in scale (500 stocks versus 5 to 15). They no longer do.

## 11. What Parakh already took

| Drishti piece | Where it landed |
|---|---|
| Structured thesis (original, key metrics, breakers, status, history) | F23 and the THESIS.md schema (plan 05 §2.4); the LLM can only flag |
| Concall pipeline (PDF extractor, transcript validator, Q&A-preserving truncation) | `adapters/concalls.py`, rebuilt on the Screener-to-BSE route |
| XIRR, drawdown, HHI | `holdings/xirr.py`, `services/risk.py` |
| Design tokens, chips, pills, heatmap, tri-state checks | Plan 12, `config/ui_tokens.yaml` |
| Owned wording (ADD / HOLD / TRIM / EXIT) | `verdict_policy.yaml` `owned_wording` |
| Universe lookup idea | AMFI directory and `listed_on` from `EQUITY_L.csv` |

## 12. What is still worth taking

| # | Item | Why it matters now | Effort | Lands in |
|---|---|---|---|---|
| 1 | **Allocation as context.** Sector weights against *targets you set* (Parakh has only maximum limits), the deviation in percentage points, and Drishti's refinements ("thesis WATCH and overweight: HOLD becomes TRIM"; ADD downgraded when valuation is stretched) | With holdings-only coverage, "does my size make sense?" is a core question. It belongs as a **deterministic** row in `verdict_policy.yaml` plus numbers in `services/risk.py`, and as input to the Portfolio Analyst agent, never as an agent decision | 5 to 7 h | R7 |
| 2 | **Evidence-first reasons.** At most four bullets in the order thesis, concall, valuation, allocation | Cheap, and it keeps the TL;DR consistent with the thesis-first idea | 1 to 2 h | R7 |
| 3 | **"What changed since I bought it."** Price versus entry, thesis timeline since the first lot, days held | Parakh has the position block and thesis timeline; a single "since purchase" panel on Stock Detail ties them together | 1 to 2 h | R7 |
| 4 | **The edge-case test catalogue** (`test cases/`, especially `test_edge_cases.py` and `test_api_thesis.py`): one TRIM per sector, original thesis immutable, cache guards | Free test ideas; mine them into fixtures for plan 14 §4.4 | 2 to 3 h | R7 |
| 5 | **FX handling and USD P&L** (`fx_pnl_inr`) | Not needed now. Keep as the reference when a US pack is built (earliest Q3 2027, plan 16) | 0 now | Backlog |

Not taken, on purpose: the React app (a 2,000-line single file, replaced by Streamlit, ADR-006), the FastAPI routers and auth, the scrapers (dead), the allocation-driven signal engine, the regex red-flag engine, and the Twelve Data provider (Parakh has two price sources).

I re-read the V2 direction document and the code layout. I did not re-read the other seven design documents; the September review in archive/11 covers their earlier assessment.

## 13. Recommendation

**Decided 14 Oct 2026 (plan 13 D29): items 1 and 2 accepted.** Recommendation as written:

1. **Do not merge or extend Drishti.** Parakh is its successor for listed Indian equities. Running both means two data models, two UIs and two sets of defects for one question.
2. **Freeze Drishti 2.0 as a read-only archive.** Tag its final state, add a note "superseded by Parakh" to its README, leave the folder in place, and do not migrate data (one holding, no thesis rows).
3. **Reposition Parakh around Drishti's question.** Its headline becomes "is the story I bought still true?", with the lenses, audit trail and agents as the evidence. This is already reflected in plan 17 §1.
4. **Take items 1 to 4 above** as part of R7, about 9 to 14 hours in total.
5. **Keep Drishti's FX logic as a reference** for the future US pack.

Recorded as D29 in plan 13, which supersedes D16. Remaining action: tag Drishti's final state and add the "superseded by Parakh" note to its README.

*Personal analytical framework; not investment advice.*
