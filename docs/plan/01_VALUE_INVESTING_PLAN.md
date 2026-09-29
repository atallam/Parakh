---
title: Value Investing Lens — Analysis Plan
version: 0.6 (§3 sector profiles for airlines/lease-heavy, conglomerates (SOTP), order-book businesses, capital-market intermediaries and new-age/loss-making; §3.1 limited-history classes; §3.2 pilot mapping; §3.3 profile rules — plan 13 D24; v0.5: thesis schema reference → plan 05 §2.4; golden oracle → plan 14; v0.4: baseline: hurdle rate 15%, concall source = BSE-filed transcripts, structured thesis — plan 13 D7/D12/D13; v0.3: §11; v0.2: §2.7, concall.in in §6)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
cadence: Monthly (price-driven metrics) · Quarterly (fundamentals refresh)
output: value_score (0–100), red_flags[], margin_of_safety, intrinsic_value_range, entry_overlay
---

# Value Investing Lens: Analysis Plan

## 1. Philosophy and scope

Value investing asks one question: **is the business worth more than the price, by a wide enough margin to absorb my errors?** To answer it, we need:

1. **Valuation:** how cheap the stock is *relative to its own history, its sector and its growth*.
2. **Quality:** whether the business earns high returns and converts profit into cash. Cheap stocks without quality are usually value traps.
3. **Safety:** whether the balance sheet and governance can survive a bad cycle.
4. **Margin of safety:** the price compared with a conservative intrinsic-value range.

**What changed from your brief:**

- **P/E and PEG stay**, but always in relative terms (vs own 5-year and 10-year median, vs sector) and with sector-appropriate substitutes.
- **50 DMA and 200 DMA move out of the score** and into an **Entry-Timing Overlay** (§7). A value investor shouldn't reject a stock because it sits below its 200 DMA; that's often when the bargain exists. The overlay controls *how* you buy (lump sum or staggered), which is where DMAs genuinely help a value investor.

---

## 2. Parameter set (the holistic view)

### 2.1 Valuation (weight 35)

| Metric | Why it matters | How it's scored | Notes / pitfalls |
|---|---|---|---|
| **P/E (TTM) vs own 5-year and 10-year median** | Tells you whether the stock is cheap *for itself* | Discount to median → points | Your core metric, used in its most reliable form |
| **P/E vs sector median** | Relative cheapness among peers | Percentile within sector | Sector medians computed from the watchlist plus index constituents |
| **PEG (P/E ÷ 3-year EPS CAGR)** | Growth-adjusted valuation | < 1.0 strong, 1–1.5 fair, 1.5–2.5 weak, > 2.5 expensive | N/A if EPS CAGR ≤ 0% or > 50%. Optional forward-PEG where estimates exist |
| **EV/EBITDA vs history & sector** | Capital-structure neutral, so debt-heavy firms can't look cheap on P/E | Discount to median | Not for banks, NBFCs or insurers |
| **P/B (and P/ABV)** | **The primary valuation metric for banks and NBFCs** | vs history, vs ROE (justified P/B ≈ ROE ÷ cost of equity) | P/ABV adjusts book for net NPAs |
| **Earnings yield vs 10-yr G-sec** | Equity vs bond opportunity cost | EY (1/PE) ÷ G-sec yield | Macro sanity check |
| **FCF yield** | Cash-based valuation that's harder to window-dress | > 5% strong; negative = 0 points | Use a 3-year average FCF for lumpy capex businesses |
| **Dividend yield** (info) | Income support, capital-allocation signal | Informational, low weight | Relevant for PSUs and utilities |

### 2.2 Quality (weight 25)

| Metric | Threshold idea (Large / Mid / Small) | Notes |
|---|---|---|
| **ROCE (5-year average + latest)** | ≥ 12% / 15% / 15% | Most important quality metric for Indian non-financials |
| **ROE (5-year average + consistency)** | ≥ 12% / 14% / 15% | Penalise high ROE driven by leverage (check against D/E) |
| **Cash conversion: CFO ÷ EBITDA (3-year) and CFO ÷ PAT** | > 70% / > 80% | Low conversion suggests receivables or inventory stuffing, and weak earnings quality |
| **Operating margin trend (12 quarters)** | Stable or rising | Falling margins together with a falling P/E is a classic value trap |
| **Piotroski F-Score (0–9)** | ≥ 7 good, ≤ 3 poor | Nine binary checks on profitability, leverage and efficiency |

### 2.3 Balance sheet and solvency (weight 15)

| Metric | Non-financials | Financials (banks / NBFCs) |
|---|---|---|
| Leverage | Debt/Equity ≤ 1.0 / 0.8 / 0.5 (L/M/S) | Capital adequacy ratio (CAR/CRAR) vs regulatory minimum plus buffer |
| Serviceability | Interest coverage ≥ 4× | Net interest margin (NIM) trend |
| Asset quality | Working-capital days trend | **GNPA / NNPA %** and trend, provision coverage |
| Liquidity | Current ratio | CASA ratio (banks) |
| Distress | **Altman Z-score** (not for financials) | — |

### 2.4 Growth (weight 10)

- Revenue CAGR over 3 and 5 years, and EPS CAGR over 3 and 5 years.
- **Consistency:** number of years with positive growth out of the last 5.
- **Earnings-quality check:** EPS growth well above revenue growth for more than 2 years gets flagged (margin expansion can't continue forever, and could be accounting-driven).

### 2.5 Governance and ownership (weight 15; critical in India, especially for mid and small caps)

| Metric | Why | Scoring / veto |
|---|---|---|
| **Promoter holding level & 4-quarter trend** | Skin in the game; steady selling is a warning | Rising = +, falling > 3 pts in a year = − |
| **Promoter pledge %** | Forced selling risk when the price falls | Flag > 0%; **veto** above 25% / 20% / 10% (L/M/S) |
| **FII and DII holding trend** | Institutional conviction | Rising for 2 or more quarters = + |
| **Auditor**: qualifications, resignation, frequent change | A leading indicator of accounting problems | **Veto** on qualified opinion or mid-term resignation |
| **Related-party transactions** (% of revenue) | Value leakage | Flag above a threshold |
| **Contingent liabilities vs net worth** | Hidden risk | Flag > 25% |
| **Beneish M-Score** | Probability of earnings manipulation | Flag > −1.78 |
| **Exchange surveillance lists (ASM / GSM)** | NSE/BSE flags for abnormal activity, mainly small caps | **Veto** if on GSM; flag if on ASM |

### 2.6 Intrinsic value and margin of safety (gate, not weighted)

The pipeline computes an **intrinsic-value range**, not a single point:

| Method | Use |
|---|---|
| **Reverse DCF** *(recommended primary)* | Answers "what growth is the current price assuming?" and compares that with historical growth. If the market implies 25% growth for 10 years and the company has delivered 12%, the stock is expensive whatever its P/E says |
| **Simple 2-stage DCF** | Conservative base case (growth = min(5-year CAGR, 15%), fading to 5% terminal; cost of equity ≈ 12–13% for India) |
| **Graham Number** √(22.5 × EPS × BVPS) | Floor sanity check for mature businesses |
| **Historical-multiple method** | Median P/E × normalised EPS |

**Margin of safety** = (Intrinsic-value midpoint − Price) ÷ Intrinsic-value midpoint.
Required MoS for a BUY: **15% Large · 25% Mid · 35% Small**. Smaller and less certain businesses need a bigger cushion.

### 2.7 Additional parameters from the v0.2 gap review

These slot into the **existing sub-scores**; the top-level weights are unchanged.

| Parameter | Sub-score | Why it matters (India lens) | Rule of thumb |
|---|---|---|---|
| **ROIIC** (return on incremental invested capital) and **reinvestment rate** | Quality | Separates true compounders (high ROCE *and* able to reinvest at high ROCE) from cash cows | ROIIC ≥ ROCE and reinvestment > 30% = compounder |
| **Cash conversion cycle** (debtor + inventory − payable days), 5-year trend | Quality | Rising debtor days is the most common early warning in Indian mid and small caps | Flag if debtor days rise > 20% YoY without matching revenue growth |
| **Other income as % of PBT** | Quality | Many Indian companies show inflated profit from treasury income or one-offs | Flag > 25% (non-financials); use core EPS for P/E |
| **Exceptional items frequency** | Quality | "Exceptional" losses every year are not exceptional | Flag if present in 3 of 5 years |
| **Accruals ratio** ((PAT − CFO) ÷ total assets) | Quality | Earnings-quality check that complements Beneish | Flag if persistently high |
| **Consolidated vs standalone gap** | Quality | Loss-making subsidiaries can hide behind a healthy standalone entity | Always score consolidated; flag a large divergence |
| **CWIP ÷ gross block and the capex cycle** | Growth | Large capital work-in-progress points to capacity coming online, i.e. future growth *or* future depreciation and debt | Informational plus a trend flag |
| **Share count dilution** (3-year CAGR), ESOP cost | Governance | Dilution quietly erodes per-share value | Flag > 3% per year |
| **Net cash ÷ market cap** | Balance sheet | Downside cushion; also flags "cash hoarding without payout" | Positive = +; > 20% of market cap with no payout = governance question |
| **Dividend payout and buyback history** | Governance | Capital-allocation discipline | Informational |
| **Credit rating and rating actions** | Balance sheet | Rating downgrades often lead price declines | Downgrade in the last 12 months = −; below investment grade = veto for small caps |
| **Promoter open-market buying / selling** (insider-trading disclosures) | Governance | The strongest insider signal. Excludes ESOP sales and gifts | Promoter buying in the last 6 months = +; heavy selling = − |
| **MF scheme count holding the stock** (AMFI monthly) | Governance / ownership | Institutional discovery, especially in mid and small caps | Rising 3 or more months in a row = + |
| **Bulk and block deals** | Ownership (info) | Who is entering or exiting | Informational, linked to the momentum plan |
| **KMP changes** (CFO/CEO resignation), auditor fees vs revenue | Governance | CFO resignation is a classic red flag in India | CFO exit within 2 years of appointment = flag |
| **Promoter remuneration as % of PAT** | Governance | Value extraction | Flag > 5% (small caps) |
| **Guidance vs delivery** (last 4–8 quarters, from filed transcripts) | Qualitative → confidence | Management credibility, quantified | Hit rate < 50% lowers confidence |
| **Sector operating KPIs** (volume growth, realisation per unit, order-book-to-revenue, same-store sales growth, ARPU, occupancy) | Growth | Leading indicators *before* they show up in P&L | Profile-specific (see §3) |
| **Sum-of-the-parts (SOTP)** | Intrinsic value | For conglomerates and holding companies with listed subsidiaries (with a 20–40% holdco discount) | Add as a 5th valuation method where relevant |

**Market-level check (from the master plan market-context layer):** Nifty and segment P/E vs their 10-year bands, plus market-cap-to-GDP. When the market sits in its top decile, **required MoS goes up by 5 percentage points** across all caps. A value investor needs a bigger margin when the whole market is expensive.

---

## 3. Sector-specific handling

The pipeline picks a **metric profile** by sector (set in `watchlist.yaml`, with a default map):

| Profile | Replace / add | Drop |
|---|---|---|
| **Banks** | P/ABV, ROA, NIM, GNPA/NNPA, CASA, CAR, credit cost | EV/EBITDA, D/E, FCF, Altman Z, Piotroski |
| **NBFC / HFC** | P/B, ROA, spread, GNPA, ALM mismatch, borrowing cost | EV/EBITDA, D/E, Altman Z |
| **Insurance** | P/EV (life), VNB margin, combined ratio (general) | Most standard ratios |
| **Cyclicals** (metals, cement, sugar, chemicals) | **Normalised P/E** (10-year average EPS), EV/EBITDA on mid-cycle margin, EV per tonne | Raw TTM P/E and PEG |
| **IT services / asset-light** | FCF yield, cash conversion, attrition (qualitative) | — |
| **Utilities / PSU** | Dividend yield, regulated ROE, government-policy risk (qualitative) | PEG (low growth) |
| **Loss-making / turnaround** | EV/Sales, path to profitability (qualitative) | P/E, PEG. Confidence is forced to Low |
| **Airlines and lease-heavy businesses** *(v0.6)* | **EV/EBITDAR** (EV includes lease liabilities under Ind AS 116) vs history and peers; **lease-adjusted net debt ÷ EBITDAR** (flag > 4×, a starting point); cash and equivalents as % of TTM revenue (liquidity runway); operating KPIs: ASK growth, yield (RASK), **CASK ex-fuel**, load factor; fuel-price and INR sensitivity (informational). P/E only on **normalised** EPS (the cyclical rule) | Raw D/E thresholds (lease liabilities make every airline fail them), raw TTM P/E and PEG, Altman Z, Piotroski |
| **Conglomerates and holding companies with listed subsidiaries** *(v0.6)* | **SOTP as the primary intrinsic-value method:** core business valued on its own P/E or EV/EBITDA vs history, **plus listed stakes at market value × stake %**, less a **holdco discount** (default 20%, range 20–40% in config), plus unlisted businesses at book or a peer multiple. Valuation and balance-sheet sub-scores use the **standalone core business**; consolidated P/E is shown for information | Consolidated D/E and EV/EBITDA (a lending subsidiary's borrowings distort both); the "always score consolidated" rule of §2.7 is replaced by "score the core standalone, show consolidated" |
| **Order-book businesses** (defence, shipbuilding, EPC, capital goods) *(v0.6)* | **Order book ÷ TTM revenue** (cover), order-inflow growth, **execution rate** (revenue ÷ opening order book), EBITDA margin on execution; **net cash excluding customer advances** (advances are not free cash); P/E on a 2-year average EPS and vs a **3-year** median plus listed peers (a sector-wide re-rating distorts 5–10-year bands); for PSUs: government stake, dividend policy, offer-for-sale overhang (event) | 5- and 10-year P/E medians as the main anchor; raw cash as net cash |
| **Capital-market intermediaries** (brokers, exchanges, AMCs, depositories) *(v0.6)* | P/E vs peers, ROE, cost-to-income, revenue mix (share of F&O / transaction income), active clients and ARPU (brokers), AUM and yield (AMCs); **regulatory sensitivity** (SEBI rules on F&O, fees) as a qualitative risk | D/E and interest coverage (client money and margin-funding borrowings are operating, not leverage), EV/EBITDA, Altman Z, Piotroski |
| **New-age / pre-profit growth** (platforms, EV makers, logistics networks) *(v0.6; extends the loss-making row)* | EV/Sales vs revenue growth and gross or contribution margin; EBITDA-margin trajectory (last 6 quarters); **cash runway** = net cash ÷ trailing 12-month cash burn; **market-implied revenue CAGR** (a reverse DCF on revenue at a configured steady-state margin and exit multiple, informational); dependence on subsidies or incentives (qualitative) | P/E, PEG, Graham Number, earnings-based DCF, Altman Z. The "negative CFO in 3 of 5 years" veto becomes a **flag** while runway ≥ 24 months, and a veto below it |

### 3.1 Limited-history classes *(v0.6, plan 13 D24)*

History is a second axis, independent of the sector profile. Every metric declares the minimum history it needs: **trading days since listing** for price-derived metrics (P/E bands, P/B percentiles, EV/EBITDA history) and **years of annual data** for fundamentals (pre-listing years from the offer document count, as filed).

| Class | Listed for (at the as-of date) | Value lens treatment |
|---|---|---|
| **H2: full** | ≥ 60 months | As specified above |
| **H1: partial** | 24–59 months | Own-history bands use what exists (3-year median from 36 months; below that, sector and peers only). Confidence capped at **Med** |
| **H0: limited** | < 24 months | No own-history valuation bands; valuation vs sector and peers only; confidence **Low**. **The value lens is informational** (next rule) |

**When the value lens is informational** (H0, or the new-age/pre-profit profile, or less than 50% of the valuation sub-score's weight is computable):
- The value score and metrics are still shown, each missing one as **❔ N/A with its reason** ("listed 11 months; needs 36"), never as zero (UX-05).
- The decision matrix (plan 00 §5) uses the **"Fair value (45–70)" row** for this stock, so the verdict is driven by momentum and vetoes only, and carries the label **"limited history"**.
- **Vetoes still apply in full**; governance vetoes need no history.
- Intrinsic value is shown only where a method's inputs exist (for pre-profit companies, the market-implied revenue CAGR); MoS is N/A otherwise.

### 3.2 Pilot mapping (D3)

| Stock | Sector profile | History class at M1 (as-of 30 Oct 2026) | Notes |
|---|---|---|---|
| HDFCBANK | Banks | H2 | Merger with HDFC Ltd (July 2023) handled explicitly in history (plan 14 §4.1) |
| INDIGO | Airlines / lease-heavy (+ cyclical normalisation) | H2 | EV/EBITDAR and lease-adjusted leverage replace P/E and D/E |
| M&M | Conglomerate / holdco (SOTP) | H2 | Core auto and farm business scored standalone; listed stakes (e.g. Mahindra Finance, Tech Mahindra, Mahindra Lifespace) in the SOTP |
| MAZDOCK | Order-book (defence shipbuilding, PSU) | H2 | Peers for relative valuation: listed shipbuilders (e.g. Cochin Shipyard, GRSE) |
| GROWW | Capital-market intermediary (broker) | H0 | Value informational |
| ATHERENERG | New-age / pre-profit (EV two-wheelers) | H0 | Value informational; runway and implied revenue CAGR shown |
| SHADOWFAX | New-age / pre-profit or early-profit (logistics), chosen automatically from TTM profit | H0 | Value informational |

The profile is chosen from the sector map and can be overridden in `watchlist.yaml` (audited as `AUD.OVERRIDE.SET`); the history class is computed, never overridden.

### 3.3 Profile rules

1. **One sector profile per stock, plus one history class.** Profiles replace and drop metrics as listed; the five sub-score weights of §4 stay the same, and weights re-normalise within a sub-score.
2. **A profile change bumps the lens version** and appears in HISTORY.md, so scores before and after stay comparable (plan 04 §1.5).
3. **Every profile has an oracle case** before it scores a real stock (plan 14 §4.1, §4.4).

---

## 4. Scoring model

```
value_score (0–100) =
    35 × Valuation_subscore
  + 25 × Quality_subscore
  + 15 × BalanceSheet_subscore
  + 10 × Growth_subscore
  + 15 × Governance_subscore
```

- Each sub-score runs from 0 to 1. Metrics inside a sub-score are converted to points by **percentile vs the stock's own history** (valuation) or by **threshold bands** (quality and safety).
- Missing metrics: re-weight within the sub-score, and lower **confidence** by one level for every 15% of weight missing.
- **Veto list** (any hit gives AVOID/SELL regardless of score): pledge above the cap limit, auditor qualification or resignation, GSM listing, negative CFO in 3 of the last 5 years, Altman Z in the distress zone (non-financial), NNPA above threshold (banks).

### Cap-specific weights (`config/value_weights.yaml`)

| Sub-score | Large | Mid | Small | Rationale |
|---|---|---|---|---|
| Valuation | 40 | 35 | 30 | Large caps are well researched, so mispricing mostly shows up as relative valuation |
| Quality | 25 | 25 | 25 | — |
| Balance sheet | 10 | 15 | 20 | Small caps die from their balance sheets |
| Growth | 10 | 10 | 5 | Small-cap growth is noisy and base effects are large |
| Governance | 15 | 15 | 20 | Governance failure is the #1 small-cap risk in India |
| Required MoS | 15% | 25% | 35% | — |
| Min liquidity (avg daily traded value) | — | ₹5 Cr | ₹1 Cr | Below this: flag "illiquid", and confidence is capped at Med |

---

## 5. Value verdict (before combining with momentum)

| Condition | Value view |
|---|---|
| Score ≥ 70 **and** MoS ≥ required **and** no veto | **UNDERVALUED: BUY candidate** |
| Score ≥ 70 but MoS below required | **QUALITY, FAIRLY PRICED: ACCUMULATE on dips / WATCH** |
| Score 45–70 | **FAIR: HOLD** |
| Score < 45, or price > intrinsic-value high end by 20% or more | **OVERVALUED: REDUCE / SELL** |
| Any veto | **AVOID / SELL** |

**Value SELL triggers** (for stocks you hold). Value investors sell for three reasons, and the report checks all three:

1. **Fully valued:** price above the top of the intrinsic-value range, or P/E above the 90th percentile of its 10-year history.
2. **Thesis broken:** ROCE down 2 years in a row, a governance event, sustained margin collapse, or a veto triggered.
3. **Better opportunity:** another watchlist stock has a much higher score and MoS (flagged in the segment summary).

---

## 6. Qualitative analysis (LLM-assisted, human-owned)

The **Qualitative Agent** reads concall transcripts, annual-report MD&A, investor presentations and recent news, then returns a **Pydantic-validated** scorecard. **Each rating needs at least one cited source**; without one, the rating is set to "insufficient evidence".

**Concall pipeline (v0.2):**

1. *(v0.4, D7)* The **transcript filed on BSE** (found through Screener's Concalls list; extraction and validation ported from Drishti) is the source for each quarter's concall. concall.in summaries are optional context only.
2. Every number or guidance statement must be an **exact quote** that is string-matched in the transcript text. Unverified items are shown with a ⚠️ and never feed confidence adjustments.
2a. *(v0.4, D13)* When the stock has a structured THESIS.md, the agent assesses each **key metric** (CONFIRMED / NEUTRAL / STRESSED / BROKEN) and each **exit condition**. It can only **flag**: BROKEN needs a metric-based breaker or your confirmation (plan 05 §2.4).
3. Guidance is stored as structured records (`{metric, target, period, said_on, source}`), so the next quarters can automatically score **guidance vs delivery**.
4. A **QoQ tone diff** compares this quarter's management language with last quarter's (for example "confident" → "cautiously optimistic", new risks mentioned, topics dropped).
5. **Trigger:** a new transcript appearing for a stock kicks off an **event-driven qualitative refresh** for that stock only, without waiting for the monthly run (plan 03 §5b).

| Dimension (1–5) | Guiding questions |
|---|---|
| **Moat** | Brand, cost advantage, switching costs, network effects, regulatory licences. Is it widening or narrowing? |
| **Management & capital allocation** | Track record of guidance vs delivery, acquisitions, dividend and buyback policy, equity dilution |
| **Concall tone & guidance** | Change in tone vs last quarter, questions dodged, guidance raised or cut |
| **Industry tailwinds / headwinds** | Policy (PLI, import duties), demand cycle, disruption risk |
| **Event risk** | Litigation, regulatory action, key-person risk, concentration (customer or supplier) |

- The qualitative score is **shown alongside** the value score and **does not change it**. It can adjust **confidence** up or down by one level. This keeps the numeric score reproducible.
- **THESIS.md** holds your own thesis ("why I own it" and "what would make me sell"). The agent checks every month whether a sell condition you wrote has been met, and says so explicitly.

---

## 7. Entry-Timing Overlay (where your DMAs live)

This overlay doesn't change the value score. It changes **how** you act on a value BUY:

| Price state | Overlay tag | Action suggestion |
|---|---|---|
| Price > 200 DMA and 50 DMA rising | **Trend supportive** | Lump sum or 2 tranches |
| Price < 200 DMA, 50 DMA flattening or turning up | **Base forming** | 3 tranches over 6–8 weeks |
| Price < 200 DMA, 50 DMA falling, making new 52-week lows | **Falling knife** | 4 tranches over 3 months, or wait for a 50 DMA turn. Re-check that the fall isn't a thesis break |
| Price > 200 DMA by more than 30% | **Extended** | Wait for a pullback toward the 50 DMA |

This gives the value lens the timing discipline you were after with the DMAs, without letting trend-following override valuation.

---

## 8. Time-series analysis (HISTORY.md, value section)

Each month the pipeline appends a row to `history.csv` and regenerates these views:

| View | Content |
|---|---|
| **Valuation band chart (table)** | Current P/E, P/B and EV/EBITDA vs 5-year and 10-year percentile bands (10th, 25th, 50th, 75th, 90th) |
| **Score trajectory** | Value score and sub-scores for the last 12 months, with arrows |
| **Fundamental trend (quarterly)** | Revenue, EBITDA margin, PAT, ROCE and CFO for the last 12 quarters; year-over-year and quarter-over-quarter |
| **Re-rating decomposition** | Price change split into **EPS change vs multiple change** (P/E expansion). *Multiple expansion with flat EPS is a warning; EPS growth with a flat multiple is healthy.* |
| **Ownership trend** | Promoter, FII, DII and pledge over the last 8 quarters |
| **Automatic trend flags** | For example "ROCE declining 3 consecutive years", "Margin compression 4 quarters", "P/E at 10-year high", "Promoter selling 3 quarters", "MoS crossed into BUY zone this month" |

---

## 9. Output contract (JSON snapshot, value section)

```json
"value": {
  "profile": "non_financial",
  "score": 58, "score_prev": 54,
  "subscores": {"valuation": 0.52, "quality": 0.78, "balance_sheet": 0.81, "growth": 0.60, "governance": 0.70},
  "metrics": {
    "pe_ttm":      {"value": 38.2, "median_5y": 42.1, "pctile_10y": 0.34, "sector_median": 45.0, "source": "screener", "asof": "2026-09-23"},
    "peg_3y":      {"value": 1.45, "eps_cagr_3y": 0.263, "source": "derived"},
    "roce_5y_avg": {"value": 0.24, "latest": 0.26}
  },
  "intrinsic_value": {"low": 6100, "mid": 6900, "high": 7800, "methods": ["reverse_dcf","dcf_2stage","hist_multiple"]},
  "implied_growth_reverse_dcf": 0.19,
  "margin_of_safety": 0.04, "mos_required": 0.25,
  "red_flags": [], "vetoes": [],
  "entry_overlay": "trend_supportive",
  "value_view": "QUALITY_FAIRLY_PRICED",
  "confidence": "High",
  "fundamentals_asof": "Q1FY27"
}
```

---

## 10. Build checklist (value lens)

- [ ] Metric library (`analytics/value.py`): pure functions with unit tests on known companies
- [ ] Sector-profile map and per-cap weight YAML
- [ ] (v0.6, D24) Profiles for airlines/lease-heavy, conglomerates (SOTP), order-book, capital-market intermediaries and new-age/pre-profit; history classes H0–H2 with per-metric minimum history; value-informational rule wired into the verdict policy
- [ ] 10-year history bands (P/E, P/B, EV/EBITDA) from price × trailing EPS series
- [ ] Reverse-DCF solver (bisection on implied growth)
- [ ] Veto engine and red-flag rules (config-driven)
- [ ] Qualitative Agent: prompt YAML, Pydantic schema, citation enforcement
- [ ] Re-rating decomposition and trend-flag rules
- [ ] Golden tests: 1 bank, 1 cyclical, 1 consumer compounder, against the independent oracle (plan 14 §4.1, D18)
- [ ] (v0.2) ROIIC, cash conversion cycle, other-income share, accruals, dilution, net-cash metrics
- [ ] (v0.2) Insider-trading and takeover-code disclosure parser, AMFI MF-holdings loader, credit-rating watcher
- [ ] (v0.4) Transcript provider (Screener Concalls → BSE-filed PDF) + exact-quote verifier; guidance-tracking store; thesis-aware assessment
- [ ] (v0.2) SOTP module for holding companies; market-level MoS adjustment

---

## 11. Strengthening the value lens (v0.3)

| # | Enhancement | What it changes | Why it makes the analysis stronger |
|---|---|---|---|
| 1 | **Stock archetype classification** (Peter Lynch's six types, adapted: Slow grower, Stalwart, Fast grower, Cyclical, Turnaround, Asset play) | Each stock is tagged automatically from growth, volatility and ROCE history (you can override the tag in THESIS.md). The archetype picks the **metric profile, weights and sell rules** | A Stalwart should be judged on P/E vs history; a Cyclical on normalised earnings and bottom-of-cycle P/B; a Turnaround on balance-sheet repair. Judging them all the same way is the most common value-analysis error |
| 2 | **Expected return (IRR) instead of just margin of safety** | Probability-weighted bull/base/bear scenarios give an expected 3–5-year CAGR, compared with **your hurdle rate** (configurable; **locked at 15%**, plan 13 D12) | Converts "cheap" into "worth owning vs alternatives", including a liquid fund or index fund. It also ranks opportunities across sectors fairly |
| 3 | **Value-trap detector** (composite flag) | Flags stocks that are cheap *and* have at least 3 of these: falling ROCE, falling margins, negative estimate revisions, promoter selling, negative 12-month RS, rising debtor days | Most value losses come from traps, not from overpaying. This turns scattered warnings into one explicit alarm |
| 4 | **Owner earnings** (Buffett): PAT + D&A − maintenance capex − working-capital build | Used alongside PAT for P/E and DCF | Closer to real distributable cash; exposes capital-hungry businesses |
| 5 | **Normalised margins and earnings for cyclicals** | 10-year average margin × current revenue = normalised EPS | Prevents "cheap at the peak" mistakes |
| 6 | **Sector-relative z-scores** | Valuation and quality measured as z-scores within the sector | Fair comparisons across very different industries |
| 7 | **Thesis drift tracking** | The Qualitative Agent compares the current story with the original THESIS.md each quarter ("you bought for export growth; exports are now 12% of revenue vs 30%") | Catches slow thesis erosion that no single metric flags |
| 8 | **Calibration** | Quarterly check that high value scores lead to higher 12- and 24-month forward returns (value works slowly, so judge it on longer horizons) | Tells you whether the weights work, and which sub-scores carry the signal |

*Personal analytical use only; not investment advice. Thresholds are starting points, to be calibrated.*
