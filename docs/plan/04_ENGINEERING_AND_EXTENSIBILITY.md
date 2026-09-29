---
title: Engineering, Extensibility & Pre-Build Checklist
version: 1.0 (MCP-first: ADR-010/011/012 indexed, ADR-003/008 amended, `src/mcp/` + `AgentRunner` in the repo layout, TOOL./AGENT./AG- IDs — plan 15; v0.9: repo layout: docs/plan, outputs, test folders; v0.8 baseline: ADR-003/004/008 accepted, ADR-009 secrets, Production module layout, repo `parakh` — plan 13; v0.7: ADR-006 extended with design system + render guardrails; ADR-008 notifications proposed; UX/UI IDs; v0.6: ADR-007 audit & governance; v0.5: ADR-006 UI)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
covers: plug-in "Lens" architecture for new investing styles · code maintainability & searchability standards · infra/data risks to settle before coding
---

# Engineering, Extensibility and Pre-Build Checklist

## 1. Adding a new investing style without reinventing the wheel

### 1.1 Core idea: every style is a "Lens" plug-in

Value and Momentum become the first two **Lenses**. A Lens is a small class that only *combines* shared building blocks. It never fetches data, never writes files and never sends alerts itself.

```
            ┌──────────────── SHARED PLATFORM (built once) ────────────────┐
 Data       │ adapters → validated DataFrames → Feature Store (metrics)    │
 layer      │ (prices, fundamentals, filings, concalls, macro, holdings)   │
            ├──────────────────────────────────────────────────────────────┤
 Libraries  │ Metric Registry   (ROCE, P/E-vs-median, RS, ATR … each once) │
            │ Signal Registry   (M01…M30, event detectors, debouncing)     │
            │ Scoring toolkit   (percentile, bands, z-score, re-weighting) │
            ├──────────────────────────────────────────────────────────────┤
 Lenses     │  ValueLens │ MomentumLens │ QualityLens │ DividendLens │ …   │ ← plug-ins
            ├──────────────────────────────────────────────────────────────┤
 Policy     │ Verdict Policy (YAML rules: matrix, vetoes, hysteresis)      │
            ├──────────────────────────────────────────────────────────────┤
 Outputs    │ Snapshot/JSON · History · Report partials · Alerts · Storage │
            └──────────────────────────────────────────────────────────────┘
```

### 1.2 The Lens contract

```python
# src/lenses/base.py
class LensResult(BaseModel):
    """Standard output every lens must return. Rendered, stored and alerted generically."""

    lens_id: str  # "value", "momentum", "dividend"
    lens_version: str  # semver; stored in every snapshot
    score: float | None  # 0–100 (None = not applicable to this stock)
    subscores: dict[str, float]  # 0–1 each
    view: str  # lens-specific label, e.g. "UNDERVALUED"
    confidence: Literal["High", "Med", "Low"]
    metrics_used: list[str]  # metric IDs from the registry (traceability)
    signals: list[str]  # signal IDs fired
    vetoes: list[str]  # rule IDs
    explanations: list[str]  # top drivers, used for score attribution


class Lens(ABC):
    lens_id: ClassVar[str]
    required_metrics: ClassVar[list[str]]  # declared, so the platform computes them first
    applicable_profiles: ClassVar[list[str]]  # e.g. exclude "bank" for EV/EBITDA-based lenses

    @abstractmethod
    def evaluate(self, ctx: StockContext, cfg: LensConfig) -> LensResult: ...
```

Lenses register themselves with a decorator (`@register_lens("dividend")`), and `config/lenses.yaml` switches them on or off per cap.

### 1.3 Adding a new style: the 5-file recipe

```powershell
python run.py new-lens dividend      # scaffolds the 5 files below from a template
```

| File | What you write |
|---|---|
| `src/lenses/dividend.py` | The `evaluate()` logic: usually 50–150 lines, because metrics come from the registry |
| `config/lenses/dividend.yaml` | Weights, thresholds per cap, and comments explaining each number |
| `src/render/partials/dividend.md.j2` | The report section for this lens |
| `tests/lenses/test_dividend.py` | Golden test on 3 frozen stocks (plus automatic contract tests) |
| `FRAMEWORK/0X_DIVIDEND_PLAN.md` | The plan / rationale doc (same shape as plans 01 and 02) |

Then **optionally** add one row to the Verdict Policy YAML (how this lens combines with the others). If you skip it, the lens appears in reports and history as an **informational** score only.

**What you get for free:** data fetching, MCP access (`analytics.evaluate_lens` and `reports.get_stock` pick the lens up from the registry, plan 15 §4.4), caching, history columns (`dividend.score` added to `history.csv` automatically), report rendering, segment ranking, alerts on its signals, storage, observability and the backtest harness.

### 1.4 Candidate future lenses, and how much they reuse

| Lens | What it does | New metrics needed | Reuse |
|---|---|---|---|
| **Quality / Coffee-Can** (Indian variant) | 10 years of ROCE > 15% and revenue growth > 10% every year | Consistency counters | ~95% |
| **Magic Formula** (Greenblatt) | Rank on earnings yield (EBIT/EV) + return on capital | EBIT/EV | ~95% |
| **GARP** | Growth at a reasonable price | Forward growth where available | ~90% |
| **Dividend / Income** | Yield, payout sustainability, dividend growth | Dividend CAGR, FCF payout | ~85% |
| **CAN SLIM** (O'Neil growth-momentum) | Quarterly EPS acceleration + RS + institutional sponsorship | EPS acceleration | ~85% |
| **Low-volatility / defensive** | Low beta, low drawdown, stable earnings | Downside beta | ~90% |
| **Turnaround** | Improving ROCE from a low base, deleveraging, margin recovery | Delta-based metrics | ~80% |
| **Special situations** | Demergers, buybacks, open offers, delisting | Event parser (announcements) | ~60% |

### 1.5 Rules that keep lenses composable

1. **A metric is defined once**, in the Metric Registry. Two lenses needing ROCE share the same function and the same number.
2. **Lenses are pure:** same inputs give the same output, with no I/O and no LLM calls. Qualitative inputs arrive already computed in `StockContext`.
3. **Every threshold lives in YAML**, never hard-coded.
4. **Lens versioning:** changing a lens's logic bumps its version, and history can be re-scored with `python run.py rescore --lens value --from 2026-01`.
5. **Contract tests run automatically** for every registered lens: score within 0–100, subscores within 0–1, every metric ID used exists in the registry, runs in < 50 ms per stock, and it doesn't crash on missing data.

---

## 2. Strengthening the analysis (cross-cutting)

Style-specific additions are in plan 01 §11 and plan 02 §11. These apply to every lens:

| Addition | What it does | Why |
|---|---|---|
| **Devil's-advocate agent** | For every BUY or SELL, a separate LLM agent is prompted to argue the **opposite** case using the same data plus concall evidence. Its best 3 counter-points go into the report | Guards against confirmation bias, which is the most common failure in personal investing. A natural agentic pattern |
| **Calibration dashboard** | Each quarter: forward 3M/6M/12M returns by score quintile and by verdict. Is the top quintile actually beating the bottom? | A score that doesn't sort future returns is decoration. This makes it measurable |
| **Decision journal** | When you act (buy or sell), a 3-line entry is logged: reason, expected outcome, review date. The monthly run shows the journal entries that are due for review | Separates good decisions from good luck |
| **Pre-buy checklist gate** | Before a verdict is shown as BUY, the stock must pass a short checklist (liquidity, no veto, thesis written, position size within limits) | Behavioural discipline |
| **Sector-neutral normalisation** | Scores computed as z-scores *within sector*, with a sector-tilt note | Stops whole sectors (for example PSU banks on P/E) dominating rankings |
| **Out-of-sample discipline** | Tune weights on 2014–2021 data, validate on 2022 onward; cap the number of tunable parameters | Prevents over-fitting the backtest |

---

## 3. Code maintainability and searchability standards

### 3.1 ID-anchored traceability (the key to "easy to search")

Every business concept gets a **stable ID** that appears identically in docs, config, code, tests, logs and reports:

| Concept | ID pattern | Example |
|---|---|---|
| Metric | `MET.<lens-or-common>.<name>` | `MET.value.pe_vs_5y_median` |
| Signal | `M<nn>` / `E<nn>` (events) | `M03`, `E04` (auditor resignation) |
| Rule / veto | `RULE.<area>.<name>` | `RULE.veto.promoter_pledge` |
| Lens | `LENS.<name>` | `LENS.momentum` |
| Architecture decision | `ADR-<nnn>` | `ADR-004 storage choice` |
| UX principle *(v0.7)* | `UX-<nn>` | `UX-05` (unknown ≠ clean), plan 12 §2 |
| UI component *(v0.7)* | `UI.<name>` | `UI.range_bar`, plan 12 §4 |
| MCP tool *(v1.0)* | `TOOL.<toolset>.<name>` | `TOOL.reports.what_changed`, plan 15 §4.2 |
| Agent *(v1.0)* | `AGENT.<name>` | `AGENT.event_triage`, plan 15 §5 |
| Agentic principle *(v1.0)* | `AG-<nn>` | `AG-03` (agents propose; you decide), plan 15 §2 |

So `Ctrl+Shift+F "M03"` in VS Code or Cursor finds the plan definition, the YAML threshold, the detector function, its tests, and every log line and report where it fired.

```python
@register_metric(
    id="MET.value.pe_vs_5y_median",
    unit="ratio",
    inputs=["prices.close", "fundamentals.eps_ttm"],
    used_by=["LENS.value", "LENS.garp"],
)
def pe_vs_5y_median(pe_series: pd.Series) -> float:
    """Current P/E divided by its own 5-year median P/E.

    Formula:   pe_now / median(pe over last 1260 trading days)
    Meaning:   < 1.0 → cheaper than its own history; 0.8 = 20% discount.
    Pitfalls:  Meaningless when EPS <= 0 (returns NaN). For cyclicals use
               MET.value.normalised_pe instead (see plan 01 §3).
    Source:    FRAMEWORK/01_VALUE_INVESTING_PLAN.md §2.1
    """
```

### 3.2 Conventions

| Area | Standard |
|---|---|
| **Docstrings** | Google style, with `Formula / Meaning / Pitfalls / Source` sections for every metric and signal |
| **Unit suffixes in names** | `_pct` (0–100), `_ratio` (0–1), `_x` (multiples, e.g. `pe_x`), `_cr` (₹ crore), `_inr`, `_days`, `_bps`. This removes the most common finance-code bug: mixing % and ratios |
| **Types** | Full type hints; Pydantic v2 for all boundary objects; **pandera** schemas for DataFrames (column names, dtypes, ranges) |
| **Lint and format** | `ruff` (lint + format) and `pyright` in basic mode, run via **pre-commit** hooks |
| **No magic numbers** | Thresholds only in YAML, each with a `# why:` comment |
| **Small units** | One metric per function; files < 400 lines; pure functions in `analytics/`; I/O only in `adapters/` and `storage/` |
| **Logging** | structlog with fixed keys: `run_id, isin, symbol, lens_id, metric_id, signal_id, source, latency_ms` |
| **Comments** | Explain *why*, not *what*. Link to plan sections and ADRs |
| **Auto-generated catalogues** | `docs/METRICS.md`, `docs/SIGNALS.md`, `docs/RULES.md` and *(v1.0)* `docs/TOOLS.md` are **generated from the registries** in CI, so documentation can't drift from code |
| **ADRs** | `docs/adr/ADR-nnn-*.md` for every significant choice (storage, data source, scoring change) |
| **AI-assistant context** | `CLAUDE.md` / `AGENTS.md` at the repo root: architecture map, ID conventions, "how to add a lens", commands. Cursor, Copilot and Claude then follow the same rules. *(v1.0)* `.mcp.json` registers `parakh-mcp` for Claude Code, so the coding assistant can query real snapshots and the plan docs (plan 15 §7) |
| **Versioning** | SemVer for the framework and each lens; `CHANGELOG.md`; the framework version is stamped into every snapshot |
| **Dependency pinning** | `uv` with a lock file; Python 3.12 |
| **Tests** | Mirror `src/`. Unit tests (metrics vs hand-computed values), indicator cross-checks against a reference library (e.g. `pandas-ta`), golden snapshots, lens contract tests, mocked LLM. Levels, environments, oracles, traceability and UAT are owned by **plan 14** |

### 3.3 Repository layout (updated)

```
parakh/                        ← C:\dev\parakh (plan 13 D10)
├── CLAUDE.md  AGENTS.md  README.md  CHANGELOG.md  pyproject.toml  uv.lock  .mcp.json
├── docs/
│   ├── plan/                  ← these plan docs (moved in from OneDrive FRAMEWORK/ in Phase 0; canonical from then on)
│   ├── adr/  uat/             ← ADR files; UAT records (plan 14 §7)
│   └── METRICS.md  SIGNALS.md  RULES.md  TRACEABILITY.md   (generated)
├── config/
│   ├── lenses.yaml            ← which lenses are active per cap
│   ├── lenses/value.yaml  momentum.yaml …
│   ├── verdict_policy.yaml
│   ├── universe.yaml          ← coverage tiers per cap (see plan 05)
│   ├── alerts.yaml
│   ├── agents.yaml            ← per agent: model_id, max_turns, token_budget, allowed_tools (plan 15 §6.2)
│   ├── ui_tokens.yaml         ← colours, icons, words for reports, Telegram and Streamlit (plan 12 §3)
│   └── holdings.enc.yaml      ← encrypted (see plan 05 §4)
├── src/
│   ├── adapters/              ← one module per source; all return pandera-validated frames
│   ├── storage/               ← repository interface + DuckDB / Supabase implementations
│   ├── registry/              ← metric, signal and lens registries
│   ├── analytics/metrics/     ← pure metric functions, grouped by domain
│   ├── analytics/signals/
│   ├── lenses/                ← value.py, momentum.py, _template/
│   ├── mcp/                   ← parakh-mcp server (ADR-010): server.py + toolsets/ (reports, analytics, data,
│   │                            portfolio, notify, jobs, audit), resources, prompts; thin wrappers over services (P2)
│   ├── agents/                ← one module per agent: spec + prompt ref + output model (plan 15 §5)
│   │   └── runtime/           ← AgentRunner interface; ClaudeSDKRunner (ADR-011)
│   ├── orchestration/         ← the deterministic workflow per job (monthly, watch, events) with audited_step (P2)
│   ├── prompts/               ← versioned YAML prompts (pinned per agent in config/prompts.yaml)
│   ├── policy/                ← verdict engine
│   ├── services/              ← watchlist, holdings, thesis, report services + view_models.py (ADR-006: the only API the UI may call)
│   ├── render/                ← Jinja2 templates + partials per lens; format.py (₹, %, dates; shared by every surface)
│   ├── notify/                ← Notifier interface + telegram / email / ntfy adapters (whatsapp deferred, ADR-008)
│   └── cli/                   ← run, rescore, new-lens, holdings, backtest
├── app/                       ← Streamlit pages (ADR-006), thin: services only; app/ui/components.py (plan 12 §4)
├── tests/                     ← layout and levels in plan 14; oracles/ and fixtures/ protected by CODEOWNERS
├── large_cap/  mid_cap/  small_cap/   ← generated outputs + your THESIS.md files (published to OneDrive, plan 00 §4)
├── data/  state/              ← caches and watcher state (git-ignored)
└── .github/workflows/
```

---

## 4. Infra and data: settle these before writing code

| # | Topic | Risk | Decision / mitigation |
|---|---|---|---|
| 1 | **Corporate actions**: splits and bonuses (very frequent in India), rights issues, demergers, mergers, symbol changes | Broken DMA and return series, fake crashes, orphaned history | Key everything on **ISIN**; use adjusted prices; keep a `corporate_actions` table; handle demergers explicitly (the parent's history continues and the child starts a new history); a symbol-change map |
| 2 | **NSE blocking cloud IPs** | NSE's website often rejects requests from data-centre IPs, which may include GitHub Actions runners | **Test in Phase 1.** Fallbacks: yfinance / broker API in the cloud; NSE archive files; or a **GitHub self-hosted runner on your PC** for NSE-only steps |
| 3 | **Point-in-time data and look-ahead bias** | Backtests that use results *before* they were published look brilliant and are wrong | Store fundamentals **bitemporally**: `period_end` **and** `reported_on`. Scoring only sees data with `reported_on ≤ as_of` |
| 4 | **Restatements** | Companies restate past quarters | Keep every version; flag restatements (they're also a governance signal) |
| 5 | **Survivorship bias** | Delisted and merged companies disappear from today's lists | Keep historical index constituents and cap lists by date; never delete securities |
| 6 | **Trading calendar** | Holidays, special sessions (e.g. Diwali Muhurat trading), half days | NSE holiday calendar in config; "last trading day of month" helper |
| 7 | **Rate limits and terms of use** | Bans, broken scrapers | Polite fetching (throttling, caching, backoff); prefer exports and APIs; keep a per-source terms-of-use note |
| 8 | **Data validation** | Silent bad data leading to confident wrong verdicts | pandera schemas; range checks (P/E < 0? price jump > 40% with no corporate action?); cross-source reconciliation; bad data **blocks** the verdict (confidence Low + warning) rather than being scored |
| 9 | **LLM cost and determinism** | Token bills on 500 stocks; varying outputs | LLM only for coverage Tier A (plan 05); cache by transcript hash; temperature 0; prompt version stored; per-run token budget with a hard stop |
| 10 | **Secrets and privacy** | Holdings and API keys leaking | Private repo; secrets in **AWS SSM Parameter Store via GitHub OIDC** (ADR-009) and `.env` locally; gitleaks + pip-audit as required CI checks (P10); **holdings file encrypted** (plan 05 §4); holdings never sent to an LLM unless needed |
| 11 | **OneDrive + git + databases** | OneDrive sync can corrupt `.git` folders and database files | **Recommended:** code repo at a local path outside OneDrive (**locked: `C:\dev\parakh`**, plan 13 D10); the pipeline **publishes** reports into the OneDrive `Stock Analysis` folder; caches in `%LOCALAPPDATA%` |
| 12 | **Time zones** | Cron in UTC vs market in IST | Store UTC timestamps plus the IST trading date; all schedules documented in both |
| 13 | **Reproducibility** | "Why did it say BUY in March?" | Every run stores `run_id`, config hash, framework/lens versions, source as-of dates; raw inputs retained for 24 months |
| 14 | **Observability** | Silent failures | Run table + structlog + Langfuse; failure alerts and heartbeat (plan 03) |
| 15 | **Runtime budget** | A full-cap run grows long | Parallel fetch (asyncio / thread pool), incremental price updates, and fundamentals refreshed only when a new filing appears |

---

## 5. Architecture Decision Records (ADRs)

ADRs record *why* a choice was made, so future-you, or an AI coding assistant, doesn't undo it by accident. Once the repo exists, each ADR moves to `docs/adr/ADR-nnn-<slug>.md`; this section is the index until then.

### 5.1 ADR index

| ID | Decision | Status | Where it's detailed |
|---|---|---|---|
| ADR-001 | Hybrid output formats: JSON snapshot is canonical; Markdown/CSV are rendered from it | ✅ Accepted | Plan 00 §3 |
| ADR-002 | Value and Momentum scored separately and combined through a decision matrix, never averaged | ✅ Accepted | Plan 00 §5 |
| ADR-003 | Scheduler: GitHub Actions (private repo) primary, Windows Task Scheduler fallback. *(Amended 2026-09-27, D22)* The monthly narrative review runs as `AGENT.monthly_reviewer` inside the GitHub job, not as a Claude scheduled task, because the cloud task can't reach the local-only MCP server | ✅ Accepted 2026-09-24 (plan 13 D6); amended 2026-09-27 | Plan 03 §2 |
| ADR-004 | Storage: Parquet + DuckDB for prices and analytics (Parquet kept in Supabase Storage for cloud runs); **Supabase Postgres for operational tables from Phase 1** (dedicated `parakh` project, RLS on); files are rendered outputs | ✅ Accepted, amended 2026-09-24 (plan 13 D11) | Plan 05 §3 |
| ADR-005 | Watchlist: two lists (My = approval-only; System = auto, capacity-limited) | ✅ Accepted (owner-confirmed) | Plan 06 |
| **ADR-006** | **UI framework: Streamlit first; thin UI over a service layer; FastAPI + React for future animation-heavy pages** | ✅ **Accepted (owner-confirmed 2026-09-24)** | §5.2 below |
| ADR-007 | Audit & governance: append-only, hash-chained `audit_events` (Postgres + JSONL outbox + daily git anchor), step ledger + run manifests + replay, metric-level lineage, prompt registry with eval gate, PR-only config changes | ✅ Accepted | Plan 10 §15 |
| ADR-008 *(v0.7)* | Notifications: Telegram primary (two-way buttons and commands), email for the monthly archive, ~~Claude push for the narrative review~~ *(amended 2026-09-27: the narrative review goes to Telegram + email; agents send only through `notify.queue`, plan 15 §4.2)*, ntfy optional loud lane; WhatsApp Business Platform evaluated and **deferred** behind the same `Notifier` interface; unofficial WhatsApp automation rejected | ✅ Accepted 2026-09-24 (plan 13 D5); ntfy lane not enabled at baseline | Plan 03 §4 |
| ADR-009 *(v0.8)* | Secrets: **AWS SSM Parameter Store (SecureString)** read by GitHub Actions through **OIDC** (no long-lived AWS keys; GitHub holds only the role ARN); `.env` locally; CAS password and Supabase service key live there too. Recorded fallback if no AWS account: GitHub *environment* secrets with required reviewers (a documented deviation from the SCAIX standard) | ✅ Accepted 2026-09-24 (plan 13 P1) | Plan 13 §3 |
| **ADR-010** *(v1.0)* | **MCP as the agent-facing interface over services:** one `parakh-mcp` server with namespaced toolsets; the only way agents reach data or state; agents propose, never change state; workflows stay code | ✅ Accepted 2026-09-27 (plan 13 D20) | Plan 15 §10 |
| **ADR-011** *(v1.0)* | **Agent runtime: Claude Agent SDK** behind the `AgentRunner` interface; built-in tools disabled; recorded deviation from the SCAIX LangGraph default | ✅ Accepted 2026-09-27 (plan 13 D21) | Plan 15 §6, §10 |
| **ADR-012** *(v1.0)* | **MCP transport: local stdio only** (PC and inside job runners); remote Streamable HTTP + OAuth revisited in Phase 5 | ✅ Accepted 2026-09-27 (plan 13 D22) | Plan 15 §7, §10 |

### 5.2 ADR-006: UI framework for the review app and dashboard

- **Status:** Accepted, 2026-09-24
- **Deciders:** Avinash (owner)
- **Related:** ADR-004 (storage), ADR-005 (watchlist), plan 06 §5

**Context**

- Phase 4 needs a UI for watchlist approvals (plan 06), a holdings editor (plan 05 §2) and a simple dashboard.
- Priorities: **free**, **easy to deploy**, **user-friendly**, written in **Python**.
- Future wish: **animated pages** (animated charts now; possibly richer UI animations later).
- The app shows holdings, so it must never be public.

**Options considered**

| Option | Easy to deploy | User-friendly UI | Animation headroom | Notes |
|---|---|---|---|---|
| **Streamlit** | ★★★★★ | ★★★★ | ★★ | Fastest to build; `st.data_editor` suits approvals and holdings; the whole script re-runs on every interaction |
| NiceGUI (Python, Vue/Quasar) | ★★★★ | ★★★★ | ★★★ | Event-driven, no full re-run, CSS/Tailwind transitions; the best pure-Python fallback |
| Reflex (Python compiled to React) | ★★★ | ★★★★ | ★★★★ | Can wrap React animation libraries; heavier deployment (separate frontend and backend); younger framework |
| Dash (Plotly) | ★★★★ | ★★★ | ★★★ | Chart-strong; verbose callbacks |
| Gradio | ★★★★★ | ★★ | ★ | Built for ML demos, not dashboards |
| FastAPI + React (Vite) + Framer Motion | ★★★ | ★★★★★ | ★★★★★ | Owner's existing WealthLens stack; the most work |

**Decision**

1. **Streamlit** for Phase 4 (Watchlist Review page, holdings editor, basic dashboard), run **locally** first.
2. **The UI stays thin.** Pages call service functions only (`watchlist_service`, `holdings_service`, `report_service`) and contain **no business logic**.
3. **Animated charts inside Streamlit** use Plotly animation frames (animated sector-rotation chart with trailing paths, RS-rank race chart, valuation band played month by month), `streamlit-lottie`, or small `components.html` blocks.
4. **If animation-heavy or highly interactive pages become a goal,** add a **FastAPI** layer over the *same* services and build those pages in **React + Framer Motion** (reusing the WealthLens setup). Streamlit remains for admin tasks such as approvals.
5. *(v0.7)* **One design system for every surface** (plan 12):
   - `config/ui_tokens.yaml` holds colours, icons and words; `app/ui/components.py` holds the `UI.*` components.
   - It adopts Drishti's locked palette and component set (verdict chip, thesis pill, range bar with entry notch, sparkline with cost line, thesis heatmap, evidence list, stage ladder), plus tri-state checks and a privacy toggle.
   - Pages: Home = **review inbox**; Stock Detail follows the section order in plan 12 §5.2; a thesis form dialog is reused across pages.

**Consequences**

- ➕ A working review UI in about a day; one language across the whole stack; free.
- ➕ Switching or adding a frontend later means rewriting pages, not logic (the service layer is the contract).
- ➖ Limited UI transitions and fine-grained interactivity in Streamlit; the whole page re-runs, so caching with `st.cache_data` / `st.cache_resource` is required for speed.
- ➖ Phone access needs hosting behind a login (Render, as with WealthLens). Free tiers sleep when idle (acceptable for a monthly review page). Streamlit Community Cloud limits private apps.

**Guardrails**

- Never deploy publicly: login required, and `privacy.mask_positions` is available.
- A lint rule / code review checklist: `app/` must not import from `analytics/`, `lenses/` or `adapters/` directly; it goes through `services/` only.
- *(v0.7)* **No network or LLM calls during page render.** Pages read precomputed Pydantic view models. Long jobs run in the background with a stage ladder. This is the lesson from Drishti's ~5 s drawer (archived plan 11 §2).
- *(v0.7)* **A shared view-model contract** between services and pages, with a Streamlit `AppTest` smoke test per page from fixtures. This is the lesson from Drishti's UI↔API key mismatch.
- *(v0.7)* No hex colour outside `ui_tokens.yaml` (lint).
- Directory: `app/Home.py` (review inbox), `app/pages/1_Watchlist_Review.py`, `2_Holdings.py`, `3_Segment_Dashboard.py`, `4_Stock_Detail.py`, `5_Audit_Governance.py`, `99_Components.py` (dev-only gallery); `app/ui/components.py`.

**Revisit when:** (a) you want page transitions or UI animations beyond charts; (b) Streamlit re-run latency exceeds about 2 s on common pages even with caching; or (c) the app needs multi-user access. First fallback: NiceGUI (pure Python). Full option: FastAPI + React.
