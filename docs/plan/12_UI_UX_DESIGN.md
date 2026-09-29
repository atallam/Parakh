---
title: UI/UX Design — Surfaces, Principles, Design System and Components
version: 1.4 (Claude Desktop / Claude Code as a surface through `parakh-mcp`; Claude push retired; UX-14 agent-written content marked; §9 superseded by plan 15 — D20–D22; v1.3: phase columns removed (phases live in 09); targets cite NFR-07 / PRD §5; v1.2: §10/§12 now point to 14/09; v1.1 baseline: thesis schema adopted, ntfy off at baseline — plan 13 D5/D13)
date: 2026-09-24
owner: Avinash Tallam
parent: 07_PRD.md
related: 03 §4 (notification channels, ADR-008) · 04 ADR-006 (UI framework) · 05 §4 (privacy) · 06 §5 (Watchlist Review) · 08 F09/F11/F15/F22 · 10 (audit of human actions) · archive/11 (Drishti review, the source of the borrowed elements)
conventions: UX principles are `UX-nn`; UI components are `UI.<name>` (plan 04 §3.1 ID-anchored traceability). "Drishti" marks an element borrowed from Drishti 2.0 (archived plan 11)
---

# UI/UX Design

## 1. Surfaces: one snapshot, several depths

Every surface reads the **same monthly snapshot and the same view models** (`src/services/view_models.py`). No surface computes its own verdict. This rules out the contradiction seen in Drishti, where the card said ADD and the drawer said TRIM (archived plan 11 §2).

| Surface | Job | Depth | Interaction |
|---|---|---|---|
| **Telegram** (phone) | Know what changed; act in one tap | 1 line per item, ≤ 10 lines per message | Inline buttons (approve / reject / snooze, useful / noise, mute) and commands (§6) |
| **Streamlit app** (desk) | Review, decide, edit | Card: verdict + ≤ 4 evidence bullets; detail page | Review inbox, approvals, holdings, thesis form (§5) |
| **Markdown report** (OneDrive / VS Code / Obsidian) | Deep read and permanent record | Full 15-section report | Read-only; generated |
| **Email** | Monthly archive, searchable | Segment summaries as HTML + links | Read-only |
| **Claude Desktop / Claude Code** *(v1.4, "Ask Parakh")* | Ask questions in plain words; walk through a verdict; monthly review as a conversation | Answers built from the same view models, through `parakh-mcp` (plan 15) | Prompts `/monthly-review`, `/explain`, `/deep-dive`, `/thesis-check`; propose tools with Claude's confirmation prompt; no approvals |
| ~~Claude push~~ | *Retired in v1.4:* the monthly narrative review now comes from the Monthly Reviewer agent on Telegram and email (plan 03 §3C) | — | — |
| **ntfy** *(optional; off at baseline)* | Loud lane for 🔴 High on owned stocks | 1 line | Open link |
| **WhatsApp** *(deferred)* | Mirror of the Telegram digest, if ever needed | 1 line per item | Reply buttons |

Channel choice, routing and the WhatsApp evaluation are in **plan 03 §4 (ADR-008)**. When each surface arrives is in **plan 09**.

---

## 2. UX principles

| ID | Principle | What it means in practice |
|---|---|---|
| **UX-01** | **Open on what changed** | Streamlit Home is a *review inbox*: everything since your last review, with "mark reviewed". It's the main lever for the monthly review-time target (PRD §5) |
| **UX-02** | **One snapshot, many depths** | Telegram line → card → report, all from one view model; none recomputes anything |
| **UX-03** | **Evidence-first explanations** *(Drishti)* | At most 4 bullets, in a fixed order: thesis → qualitative/concall → valuation/momentum → position/allocation. Shown in full on the detail page and report; the first bullet on cards and Telegram |
| **UX-04** | **Owned first, owned verbs** | Holdings lead every list. Owned stocks use position verbs (ADD / HOLD / TRIM / EXIT); others use verdict names (§3.2). Never show "BUY" on a stock already held at full weight |
| **UX-05** | **Unknown ≠ clean** | Every check has three states: ✅ clean · ⚠️ flagged · ❔ couldn't check (reason + last attempt). A failed check never renders as "no red flags" (the Drishti bug) |
| **UX-06** | **Honest uncertainty** | Confidence level, data-freshness stamps and "N/A" instead of forced numbers (PRD §8, unchanged) |
| **UX-07** | **Signal over noise** | One monthly message; daily messages only on change; aggregated nudges ("4 holdings without a thesis") instead of repeating one on every row |
| **UX-08** | **Human in control; capture intent at the moment of decision** | Adding a holding or approving a My Watchlist entry opens the thesis form (§5.3). The system proposes; you decide |
| **UX-09** | **Fast by design** | Pages read precomputed view models. **No network or LLM calls while a page renders.** Long jobs run in the background with a progress ladder. Target: NFR-07 |
| **UX-10** | **No dead ends** | Every error names the step, the reason and the next action (retry, manual upload, open log). Never a bare "—" |
| **UX-11** | **Private by default, shareable on purpose** | Quantities, ₹ values and ₹ P&L are masked by default in notifications and shareable outputs; a one-click privacy view; a share export with the personal-use disclaimer (§8) |
| **UX-12** | **Accessible and local** | Colour + icon + word on every status; tabular (monospaced) numbers; Indian digit grouping and lakh/crore; readable dark mode |
| **UX-13** | **Learn from use** | 👍/👎 "useful?" on alerts and cards feeds alert precision (PRD §5) and calibration (F17) |
| **UX-14** *(v1.4)* | **Say who wrote it** | Anything an agent wrote carries 🤖 and the agent's name ("🤖 Monthly Reviewer"). A proposal always looks like a suggestion with Approve / Reject, never like a decision already made. Agent text never replaces the deterministic TL;DR or verdict; it sits beside them |

---

## 3. Design system

### 3.1 Tokens: one file, three renderers

`config/ui_tokens.yaml` is the single source of colours, icons and words. It's read by the Jinja report templates (`src/render/`), the Telegram/email formatters (`src/notify/`) and Streamlit CSS (`app/ui/`). No hex colour may appear anywhere else; a lint check enforces this (AC-F22.1).

Base palette *(Drishti's locked palette)*:

| Token | Hex | Meaning |
|---|---|---|
| `positive` | `#16A34A` | ADD, BUY, INTACT, CONFIRMS, gains |
| `positive_strong` | `#15803D` | STRONG BUY |
| `neutral` | `#64748B` | HOLD, NEUTRAL, NOT SET, Low severity: deliberately muted, "no action" |
| `caution` | `#D97706` | TRIM, WATCH, CHALLENGES, Medium severity |
| `caution_strong` | `#B45309` | REDUCE |
| `negative` | `#DC2626` | EXIT, SELL, BROKEN, BREAKS, High severity, losses |
| `negative_strong` | `#991B1B` | AVOID, vetoes |
| `navy` | `#1E3A5F` | Headers, primary buttons |
| `accent` | `#2563EB` | Links, active state |
| `bg_base` / `bg_card` / `bg_muted` | `#F8FAFC` / `#FFFFFF` / `#F1F5F9` | Surfaces (dark-mode equivalents defined alongside) |
| `text` / `text_muted` / `border` | `#0F172A` / `#64748B` / `#CBD5E1` | Text and dividers |

### 3.2 Status vocabulary

**Verdicts (stocks you don't own):**

| Verdict | Token | Telegram / Markdown |
|---|---|---|
| STRONG BUY | `positive_strong` | 🟢 ▲▲ STRONG BUY |
| BUY (incl. staggered, momentum-led) | `positive` | 🟢 ▲ BUY |
| ACCUMULATE | `positive` (outline style) | 🟢 △ ACCUMULATE |
| HOLD | `neutral` | ⚪ ● HOLD |
| WATCH / MOMENTUM TRADE ONLY | `caution` | 🟡 ◐ WATCH · 🟡 ⚡ MOMENTUM ONLY |
| REDUCE | `caution_strong` | 🟠 ▼ REDUCE |
| SELL | `negative` | 🔴 ▼▼ SELL |
| AVOID | `negative_strong` | 🔴 ⛔ AVOID |

**Position verbs (stocks you own)** *(Drishti's owned/research split)*. This is the default display mapping; the verdict policy (F08, `verdict_policy.yaml`) owns the final wording and can use weight versus target:

| Verdict | Owned wording |
|---|---|
| STRONG BUY, BUY, ACCUMULATE | 🟢 ADD (in tranches for ACCUMULATE), or ⚪ HOLD if already at target weight |
| HOLD, WATCH | ⚪ HOLD (WATCH adds a 👁 note) |
| MOMENTUM TRADE ONLY | ⚪ HOLD · tight stop |
| REDUCE | 🟡 TRIM |
| SELL, AVOID | 🔴 EXIT |

**Other statuses:**

| Family | Values |
|---|---|
| Thesis *(Drishti)* | 🟢 INTACT · 🟡 WATCH · 🔴 BROKEN · ⚪ NOT SET (hidden on cards, counted in a banner) |
| Concall vs thesis *(Drishti)* | 🟢 CONFIRMS · ⚪ NEUTRAL · 🟡 CHALLENGES · 🔴 BREAKS |
| Checks (UX-05) | ✅ CLEAN · ⚠️ FLAGGED (+ severity) · ❔ UNKNOWN ("couldn't check: <reason> · tried <time>") |
| Severity | 🔴 High · 🟡 Medium · ⚪ Low |
| Change | ▲ +4 (positive) · ▼ −3 (negative) · ● 0 (neutral) · "HOLD → BUY" for verdict moves |
| Ownership | 🟢 OWNED · wt 4.1% · P&L +14.6% (quantity and ₹ only when unmasked) |

### 3.3 Typography and numbers

- **DM Sans** for UI text; **DM Mono** for every number, ticker and score, so columns don't jitter *(Drishti)*.
- `src/render/format.py` is shared by all renderers:
  - `inr()`: `₹19,20,000` (full) or `₹19.2 L` / `₹12.4 Cr` (compact).
  - `pct()`: `+4.6%`; `pp()`: `+2.1 pp`; `mult()`: `24.3×`.
  - Dates: `24 Sep 2026`; times: `18:30 IST`; relative: `3d ago`.
- Unit suffixes follow plan 04 §3.2 (`_pct`, `_ratio`, `_x`, `_inr`), so a formatter can never mix a ratio and a percentage.

---

## 4. Component library (`app/ui/components.py`)

Components are plain functions returning HTML (via `st.html`) or Plotly figures, built only from tokens. A dev-only **Component Gallery** page renders each one from fixtures, which doubles as its test (AC-F22.4).

| ID | Component | Shows | Origin | Used in |
|---|---|---|---|---|
| `UI.verdict_chip` | Verdict chip (sm / lg) | Verdict or position verb, icon, colour; optional "prev →" | Drishti SignalChip, extended to 8 verdicts | Everywhere |
| `UI.owned_badge` | Owned badge | 🟢 OWNED · weight · P&L % (₹ and quantity when unmasked) | New | Cards, detail, Telegram, reports |
| `UI.thesis_pill` | Thesis pill | Thesis · INTACT / WATCH / BROKEN | Drishti | Cards, detail, inbox |
| `UI.concall_pill` | Concall pill | Q1 FY27 · CONFIRMS … | Drishti | Detail, inbox |
| `UI.score_ring` | Score ring | 0–100 score + Δ vs last month; Value and Momentum side by side | Drishti ScoreRing (1–10 → 0–100) | Cards, detail |
| `UI.evidence_list` | Evidence list | ≤ 4 ordered bullets (UX-03), with source links | Drishti signal reasons | Detail, cards (first), Telegram (first) |
| `UI.check_row` | Check row | Tri-state check with reason and freshness | New (fixes Drishti's fail-open) | Detail, report §8/§13 |
| `UI.range_bar` | Range bar | 52-week low–high, CMP dot, **entry-cost notch**, **fair-value band**, **action-box entry zone** | Drishti Week52Bar + new bands | Cards, detail |
| `UI.sparkline` | Sparkline | 12-month close + 50/200 DMA; dashed average-cost line if owned; `~` marker when data is incomplete | Drishti PriceSparkline | Suggestion cards, holdings |
| `UI.component_grid` | Component grid | Thesis key metrics: coloured left border, status badge, one-line evidence, link to the verified quote | Drishti | Detail, report §10 |
| `UI.thesis_heatmap` | Thesis heatmap | Key metrics × last 4 quarters | Drishti (3 quarters) | Detail |
| `UI.score_heatmap` | Score heatmap | Stocks × months (Value or Momentum), verdict changes marked | New | Segment Dashboard |
| `UI.timeline` | Timeline feed | Dated verdict/thesis changes, signals and filings, with filter chips | Drishti Alerts feed | Home, detail |
| `UI.count_chips` | Count chips | Counts per bucket; click to filter | Drishti Signals tab | Home, Segment Dashboard |
| `UI.stage_ladder` | Stage ladder | Long-job stages; the failing stage, reason, retry, manual fallback | Drishti concall pipeline UI | On-demand refresh, uploads |
| `UI.suggestion_card` | Suggestion card | Plan 06 §5.1 card assembled from the components above | Plan 06 + Drishti card | Watchlist Review |
| `UI.banner` | Banner | One aggregated nudge with a direct action | New (fixes Drishti's per-row nag) | Home |
| `UI.error_panel` | Error panel | Region-level error with the next step (UX-10) | Drishti ErrorMsg, improved | Everywhere |
| `UI.feedback` | Feedback buttons | 👍 useful / 👎 noise | New | Alerts, cards |
| `UI.privacy_toggle` | Privacy toggle | Masks quantities, ₹ values and ₹ P&L | New (`privacy.mask_positions`, plan 05) | App header |

---

## 5. Streamlit screens (ADR-006)

| Page | Purpose | Key components |
|---|---|---|
| `Home.py` · **Review inbox** | Everything since your last review, owned first | `count_chips` (verdict changes · thesis alerts · flags · approvals · journal reviews due · data warnings), grouped list with `verdict_chip` (prev → now) + first evidence bullet + `thesis_pill`, **Mark reviewed**, progress "12 of 18 reviewed", governance line (plan 10), `banner` |
| `1_Watchlist_Review.py` | Approvals (plan 06 §5) | `suggestion_card`; approving a My Watchlist add opens the thesis form |
| `2_Holdings.py` | Lots and positions | `st.data_editor`, thesis status per row, "Add thesis" action; a new holding opens the thesis form |
| `3_Segment_Dashboard.py` | Cap-level view | `count_chips`, ranked table, `score_heatmap`, regime; animated charts in Phase 6 |
| `4_Stock_Detail.py` | One stock, in decision order (§5.2) | See below |
| `5_Audit_Governance.py` | Plan 10 views | Timeline of `AUD.*` events, overrides expiring, integrity status |
| `99_Components.py` *(dev only)* | Component gallery | Every `UI.*` from fixtures |

### 5.1 Home: review inbox rules

- "Since your last review" is the time you last pressed **Mark all reviewed** (stored per user; `AUD.REVIEW.MARKED`).
- Items are ordered: owned 🔴 → owned 🟡 → approvals pending → non-owned upgrades → everything else.
- Each item has *Open* (to Stock Detail) and *Mark reviewed*. Review time is measured from first open to "all reviewed", which gives the PRD §5 metric a real number instead of a self-report.

### 5.2 Stock Detail: section order

Adapted from Drishti's Overview. The verdict comes first and reference material last:

1. **Header:** name, cap, `owned_badge`, `verdict_chip` (prev → now), `thesis_pill`, `concall_pill`, confidence.
2. **Why:** `evidence_list` (4 bullets).
3. **Action box:** entry zone · stop · fair-value range · suggested action for your position · tax note (plan 00 §8).
4. **Scores:** Value and Momentum `score_ring`s with Δ and the score-attribution waterfall.
5. **Price context:** `range_bar` + price chart (DMAs, entry cost, fair-value band, next event marker).
6. **Thesis:** `component_grid`, breakers, `thesis_heatmap`.
7. **Checks:** `check_row`s for red flags and vetoes (tri-state).
8. **Upcoming events.**
9. **Timeline.**
10. **Links:** full report · `explain` lineage (plan 10 §6).

### 5.3 Thesis form (dialog) *(Drishti's first-use flow)*

- A `st.dialog` reused by Holdings, Watchlist Review and Stock Detail.
- 4 fields: **Why I bought** · **What to watch** (tags, max 5) · **What would make me sell** (tags, max 5; each marked *metric* / *LLM flag* / *manual*) · **Why this size**.
- The original is locked after the first save; later edits change the working thesis and show a diff against the original.
- It saves through the thesis service into THESIS.md front matter (schema in plan 05 §2.4, plan 13 D13) and emits `AUD.THESIS.CHANGED`. The pipeline still never writes THESIS.md (AC-F09.4).
- Skipping is allowed. It's then counted in the Home banner ("4 holdings without a thesis → Add"), not repeated on every row.

---

## 6. Telegram UX

Channel selection, routing and callback processing are in plan 03 §4. These are the presentation rules:

| Rule | Detail |
|---|---|
| Length | ≤ 10 lines; the first line says what happened and why it matters |
| Vocabulary | Emoji + word from §3.2; never colour alone |
| Evidence | One bullet per item (the first from UX-03) |
| Links | Every item ends with *Open ▸*: the Streamlit Stock Detail page when hosted, otherwise the report path |
| Privacy | `notify.include_amounts: false` by default: weight % and P&L % only |
| Quiet by default | Heartbeat and ⚪ Low digests are sent **silently** (`disable_notification`); 🔴 High uses normal sound |
| Buttons | Alerts: 👍 Useful · 👎 Noise · 🔕 Mute 10d. Suggestions: ✅ Approve · ❌ Reject · 💤 Snooze |
| Commands | `/today` · `/stock <SYMBOL>` · `/pending` · `/status` · `/mute <1d>` · `/privacy on|off` |
| Scope | Framework commands only, no open-ended AI chat. This keeps the bot simple, private and compatible with WhatsApp's business-bot policy if it's ever mirrored there (plan 03 §4.4) |

---

## 7. Markdown report rules (F09)

- **Top block:** TL;DR · `verdict_chip` (prev → now) · **What changed since last month** (≤ 4 bullets) · action box. Everything else follows plan 00 §8.
- Sections 4–15 go inside `<details>` blocks, which fold in VS Code, Obsidian and GitHub.
- Checks use the three states (UX-05).
- Every price chart shows entry cost, the fair-value band and the next event. Every score chart shows the verdict thresholds and the hysteresis band, so a flip, or a non-flip, explains itself.
- The segment summary links stocks as `[[SYMBOL]]`, so the Obsidian graph and backlinks work over the report folder.

---

## 8. Privacy and sharing (UX-11)

| Mode | Where | What's hidden |
|---|---|---|
| **Default notifications** | Telegram, email, ntfy | Quantities, ₹ values, ₹ P&L (weights and % shown) |
| **Privacy view** | Streamlit header toggle (`privacy.mask_positions`) | Same, on every page; safe for screenshots |
| **Share export** | `run.py share <SYMBOL>` → Markdown + PNG card | All position data, sizing rationale and personal notes; adds the personal-use disclaimer and the SEBI note (plan 00 §2) |

Telegram bot chats and WhatsApp Business messages are processed on the provider's servers and aren't end-to-end encrypted, which is why masking is the default.

---

## 9. Integrations beyond notifications

| Integration | Value |
|---|---|
| **Calendar (.ics)** | Results dates, board meetings and ex-dates for owned and watchlist stocks, attached to the monthly email (one tap to add to Google Calendar) |
| **Claude as a conversational front-end** | *(v1.4: now core, not an integration.)* The `parakh-mcp` server (plan 15 §4) gives Claude Desktop and Claude Code the same tools the agents use, so you can ask "why did POLYCAB move to BUY?". Local only for now (ADR-012) |
| **Obsidian** | `[[SYMBOL]]` links in summaries (§7) |

---

## 10. Testing the UX

UX tests live in **plan 14**: AppTest (L5), view-model contracts (L2), no network in render, tri-state, redaction and token lint (L0/L6), and Telegram/report snapshot tests (L3).

---

## 11. What we deliberately don't copy from Drishti

| Drishti behaviour | Rule here |
|---|---|
| "No red flags detected" when checks failed | UX-05 |
| Card and drawer disagreeing | UX-02 |
| `₹—` from a silent server error | UX-10 |
| Setup nag on every row | UX-07 banner |
| About 5 s spinner on each drawer open (live scraping) | UX-09 |
| React single-file UI (2,000+ lines) | Streamlit pages + a component module (ADR-006) |

---

## 12. Rollout by phase

The phase placement of the UI/UX deliverables lives in **plan 09**.

*Personal analytical framework; not investment advice.*
