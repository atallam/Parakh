---
title: Momentum Investing Lens — Analysis Plan
version: 0.5 (§3.9 limited price history: per-metric minimum sessions, listing-period exclusion, substitutes, signal gating, confidence caps — plan 13 D24; v0.4: baseline: guidance source = BSE-filed transcripts, plan 13 D7; v0.3: §11 strengthening added; v0.2: §3.8, signals M08/M09/M27–M30, regime inputs)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
cadence: Monthly (full scoring & ranking) · Daily end-of-day (signal watch — see 03)
output: momentum_score (0–100), rs_percentile, trend_template (x/8), stage (1–4), active_signals[], exit_levels, regime
---

# Momentum Investing Lens: Analysis Plan

## 1. Philosophy and scope

Momentum investing is based on a well-documented market effect: **stocks that have outperformed over the past 3–12 months tend to keep outperforming over the next few months**, and the effect is strongest when the trend is smooth and confirmed by volume. The job of this lens is to:

1. **Rank** strength *relative to the right benchmark*. This is your core idea, kept as the centrepiece.
2. **Confirm** that the trend structure is healthy (DMAs, stage, proximity to highs).
3. **Detect** when a *new pattern* is forming or an existing one is breaking.
4. **Define exits in advance.** Momentum without exit rules is just hope.

**What changed from your brief:**

- "50 DMA crossing 200 DMA" and "200 DMA crossing 50 DMA" are one pair of events: the **Golden Cross** (50 moves above 200) and the **Death Cross** (50 moves below 200). Both are kept, but downgraded to **confirmation** signals because they lag. Leading signals are added in front of them (§4).
- Benchmark comparison is upgraded to **cap-matched + sector-matched**, **multi-horizon** and **volatility-adjusted**.
- A **market-regime filter** is added. Momentum strategies suffer their worst drawdowns when the broad market turns, so individual signals are discounted when the segment is in a downtrend.

---

## 2. Benchmarks

| Cap | Primary benchmark | Secondary | Sector |
|---|---|---|---|
| Large | **Nifty 100** (matches SEBI's top-100 definition) | Nifty 50 | Sector index (Nifty Bank, IT, Pharma, Auto, FMCG, Metal, Realty, Energy …) |
| Mid | **Nifty Midcap 150** | Nifty 500 | Sector index |
| Small | **Nifty Smallcap 250** | Nifty 500 | Sector index |

Measuring against the sector index tells you whether the stock is a **leader in a leading sector** (best), a leader in a lagging sector, or just riding its sector.

---

## 3. Parameter set

### 3.1 Relative strength vs benchmark (weight 30 in v0.2, was 35): your core idea

| Metric | Definition | Why |
|---|---|---|
| **Excess return, 1M / 3M / 6M / 12M** | Stock return − benchmark return | Multi-horizon picture |
| **12-1 momentum** | 12-month return excluding the most recent month | The standard momentum measure in academic research; skipping the latest month avoids short-term reversal |
| **RS line** | Price ÷ benchmark, with its 50-day slope | Rising RS line = outperforming *now* |
| **Mansfield RS** | (RS ÷ 52-week SMA of RS − 1) × 100 | Normalised: > 0 is outperforming its own RS average |
| **RS percentile within segment** | Rank of 12-1 momentum among all index constituents of the cap | "Top 20% of midcaps" means more than "+30%". Requires constituent lists |
| **Sector RS** | Stock vs sector index, and sector vs benchmark | Leader-in-leading-sector check |

### 3.2 Volatility-adjusted momentum (weight 20)

Similar to NSE's Nifty200 Momentum 30 approach:

```
mom_6m_adj  = return_6m  / annualised_volatility_1y
mom_12m_adj = return_12m / annualised_volatility_1y
momentum_z  = average( zscore(mom_6m_adj), zscore(mom_12m_adj) )   ← z-scored within the cap universe
```

Without this adjustment, rankings favour volatile, erratic small caps. With it, the ranking favours **smooth** trends, which persist better.

### 3.3 Trend structure (weight 25): your DMAs live here

| Check | Bullish state |
|---|---|
| Price vs 50 DMA | Above |
| Price vs 200 DMA | Above |
| 50 DMA vs 200 DMA | 50 above 200 (post–Golden Cross) |
| **200 DMA slope** | Rising for ≥ 1 month (a flat or falling 200 DMA weakens every other bullish reading) |
| **Distance from 200 DMA** | Healthy: 5–30% above. **Over-extended** above 30% / 40% / 50% (L/M/S), where mean-reversion risk is high |
| **Minervini Trend Template** (score x/8) | See §3.6 |
| **Weinstein Stage** (1 basing / 2 advancing / 3 topping / 4 declining) | Stage 2 is the only stage to buy in; uses a 30-week (~150 DMA) MA |

### 3.4 52-week high proximity (weight 10)

- `price ÷ 52-week high`. Stocks within **~10–15% of their 52-week high** show stronger continuation (the "52-week-high momentum" effect).
- Stocks more than 30% below their 52-week high score low on momentum, however strong their 1-month bounce.

### 3.5 Volume and participation (weight 10): India-specific edge

| Metric | Why |
|---|---|
| **Up-volume / down-volume ratio (50 days)** | Accumulation vs distribution |
| **Breakout volume** vs 50-day average volume | Breakouts on ≥ 1.5× volume are more reliable |
| **Delivery % (NSE bhavcopy)** and its trend | High delivery % on up-days suggests *investors* are buying rather than intraday traders. This data is published in India and rarely available for the US |
| **OBV trend** | Confirms the price trend |

### 3.6 Minervini Trend Template (reported as x/8)

1. Price > 150 DMA and > 200 DMA
2. 150 DMA > 200 DMA
3. 200 DMA rising for at least 1 month
4. 50 DMA > 150 DMA and > 200 DMA
5. Price > 50 DMA
6. Price ≥ 30% above its 52-week low
7. Price within 25% of its 52-week high
8. RS percentile ≥ 70

8/8 means a textbook Stage-2 uptrend. A stock newly reaching 8/8 is an alert-worthy "pattern forming" event.

### 3.7 Oscillators (informational, not scored)

RSI(14), MACD(12,26,9) and ADX(14) are used **only** to detect divergences and trend strength. In strong uptrends, RSI above 70 is normal and **not** a sell signal for momentum investors.

### 3.8 Additional parameters from the v0.2 gap review

| Parameter | Where it fits | Why it matters |
|---|---|---|
| **Earnings momentum**: results surprise (vs consensus where it exists, otherwise vs the company's own trailing run-rate), YoY acceleration in revenue and EPS growth | Replaces 5 pts of RS weight: **RS 30 / Earnings momentum 5** | Price momentum backed by earnings momentum persists far better. The strongest known combination |
| **Post-earnings drift / results-day reaction**: gap on results day, and whether it *holds* for 5 sessions | Signal M08 | Stocks that gap up on results and hold tend to keep drifting for weeks |
| **Estimate revisions and guidance changes** (Trendlyne consensus where available; guidance raised or cut from BSE-filed concall transcripts, plan 13 D7) | Earnings-momentum sub-score | Upgrades lead price; also links the value and momentum lenses |
| **Institutional footprints**: bulk and block buys, a delivery % spike above the 20-day average, a rising MF scheme count | Volume & participation | Separates institutional accumulation from retail-driven spikes |
| **F&O data** (F&O stocks only): long build-up (price ↑ + OI ↑) vs short covering (price ↑ + OI ↓); F&O ban list | Informational + signal | Long build-up confirms trend; short-covering rallies fade faster |
| **Price-band / circuit trap** (small caps): consecutive upper circuits in 5%/10% bands, low traded value | **Veto on momentum BUY** (M27) | Circuit-driven "momentum" can't be bought or exited at fair prices; a classic small-cap trap in India |
| **Surveillance stage (ASM/GSM)** | Veto / warning (M28) | High-momentum small caps often get put under ASM, which raises margins and dries up liquidity. This often marks a local top |
| **Liquidity / impact cost** | Filter | You must be able to exit at the trailing stop, not 5% below it |
| **Risk profile**: 1-year beta vs benchmark, max drawdown, downside volatility | Position-size suggestion (not the score) | Same score, different risk, so size them differently |
| **Sector rotation (Relative Rotation Graph quadrant)**: sector RS ratio vs RS momentum → Leading / Weakening / Lagging / Improving | Sector context, M07 refinement | "Improving" sectors are where the next leaders emerge |
| **Index rebalancing events** (Nifty semi-annual, MSCI quarterly announcements) | Event signal M29 | Inclusion creates forced passive buying; momentum often starts on the announcement |
| **IPO lock-in expiries** (recent listings) | Event warning M30 | Supply overhang; momentum often stalls around expiry |
| **Market breadth and flows**: % of segment above its 200 DMA, advance/decline line, India VIX, 20-day FII/DII net flows | **Regime engine** (§5) | Momentum crashes happen when volatility spikes and breadth collapses |

---

### 3.9 Limited price history *(v0.5, plan 13 D24)*

Young listings (in the pilot: GROWW, ATHERENERG, SHADOWFAX) don't have the price history several measures need. Each metric and signal declares a **minimum number of sessions**; below it the value is **❔ N/A with its reason**, never zero, and weights re-normalise within the sub-score.

**Listing-period exclusion.** The first **20 sessions after listing** are excluded from volatility, 52-week high/low and base detection. Listing-day pops and early price discovery in Indian IPOs otherwise distort all three.

| Measure | Minimum sessions (after the exclusion) | Substitute below the minimum |
|---|---|---|
| Excess return 1M / 3M / 6M | 21 / 63 / 126 | N/A |
| 12M excess return, **12-1 momentum**, Mansfield RS | 252 | Ranked on 6M vol-adjusted momentum only |
| Annualised volatility (for vol-adjusted momentum) | 252 | Volatility since the exclusion window, if ≥ 126 sessions (flagged "short window") |
| 52-week high / low (§3.4, Template items 6–7, M03) | 252 | **Since-listing high / low**, labelled as such, if ≥ 126 sessions |
| 150 DMA, Weinstein stage | 150 | N/A |
| 200 DMA, its slope, distance from it | 200 (slope: 220) | N/A |

**Signal gating.** Signals that depend on a missing measure don't fire: M06, M10, M11, M21 and M24 need the 200 DMA; M01 and M03 use the since-listing high below 252 sessions and say so in the alert.

**Scoring and confidence.**

| Sessions since listing (after the exclusion) | Treatment |
|---|---|
| < 126 | **Momentum lens informational**: shown, not scored into the verdict; the stock's verdict comes from vetoes only (WATCH at best) |
| 126–251 | Scored on available measures; Trend Template reported as **x/y** (y = criteria computable); confidence capped at **Med** |
| ≥ 252 | As specified above |

This is the momentum half of the limited-history rule; the value half is plan 01 §3.1.

## 4. Signal and pattern catalogue

Each signal has an ID, a type and a confirmation rule. **Confirmation:** a signal is only "active" after **2 consecutive closes** beyond the level, or a **1% buffer**. This avoids whipsaws.

### Leading signals (early: "a new pattern is forming")

| ID | Signal | Definition | Severity |
|---|---|---|---|
| **M01** | **RS line new high before price** | RS line makes a 52-week high while price is still below its 52-week high | High (a classic early leadership signal) |
| **M02** | **Stage 1 → 2 transition** | Price breaks out of a base range (≥ 6 weeks, range < 25%) above a flattening or rising 150 DMA on ≥ 1.5× volume | High |
| **M03** | **52-week-high breakout on volume** | Close at a new 52-week high with volume ≥ 1.5× (Large) / 1.75× (Mid) / 2× (Small) of the 50-day average | High |
| **M04** | **Volatility Contraction Pattern (VCP)** | 3 or more successive pullbacks, each shallower than the last, with volume drying up | Medium (a setup, not yet a trigger) |
| **M05** | **Trend Template newly 8/8** | Score moves from ≤ 7 to 8 | High |
| **M06** | **200 DMA reclaim** | Close back above the 200 DMA after ≥ 20 sessions below it, with the 200 DMA flattening | Medium |
| **M07** | **Sector rotation in** | Sector index RS vs benchmark crosses above 0 (Mansfield), or the sector's RRG quadrant moves to Improving/Leading | Medium |
| **M08** | **Earnings gap and hold** *(v0.2)* | Results-day gap ≥ 4% on ≥ 2× volume, and price holds above the gap-day low for 5 sessions | High |
| **M09** | **Institutional accumulation** *(v0.2)* | Bulk or block buy by an institution, or delivery % > 1.5× its 20-day average on an up-day, while RS is rising | Medium |
| **M29** | **Index inclusion announced** *(v0.2)* | Stock announced for inclusion in its cap index, Nifty 50/Next 50, or an MSCI index | Medium |

### Confirmation signals (lagging but reliable)

| ID | Signal | Definition | Severity |
|---|---|---|---|
| **M10** | **Golden Cross** | 50 DMA crosses above 200 DMA *(your "50 crossing 200")* | Medium |
| **M11** | **Death Cross** | 50 DMA crosses below 200 DMA *(your "200 crossing 50")* | High (for holders) |
| **M12** | **50 DMA pullback bounce** | In Stage 2, price touches the 50 DMA (within 2%) and closes back up on rising volume | Medium (add-on entry) |

### Warning and exit signals

| ID | Signal | Definition | Severity |
|---|---|---|---|
| **M20** | **50 DMA breakdown** | 2 closes below the 50 DMA on above-average volume | Medium (tactical exit / tighten stop) |
| **M21** | **200 DMA breakdown** | 2 closes below the 200 DMA | High (strategic exit) |
| **M22** | **Stage 2 → 3 (topping)** | 150 DMA flattens, price chops around it, with distribution days increasing | High |
| **M23** | **Bearish RSI divergence** | Price makes a higher high while RSI makes a lower high, near a 52-week high | Medium |
| **M24** | **Over-extension** | Distance from the 200 DMA exceeds the cap threshold | Low/Medium (don't chase; consider trimming) |
| **M25** | **RS percentile drop** | Falls below the 50th percentile after being above 80 | High (the momentum thesis is fading) |
| **M26** | **Climax run** | ≥ 25% gain in ≤ 3 weeks with the largest volume of the advance | Medium (often marks a top) |
| **M27** | **Circuit trap** *(v0.2)* | ≥ 3 upper or lower circuits in 10 sessions in a 5% or 10% price band, or traded value below the liquidity floor | High (**veto on new BUY**) |
| **M28** | **Surveillance inclusion** *(v0.2)* | Stock added to ASM or GSM (or moves up a stage) | High |
| **M30** | **Lock-in expiry approaching** *(v0.2)* | Pre-IPO or anchor-investor lock-in expires within 15 trading days | Medium |

---

## 5. Market-regime filter (segment level)

Computed once per cap segment each run and each day:

| Regime | Rule (for the segment benchmark) | Effect on stock verdicts |
|---|---|---|
| **Risk-On** | Benchmark > 200 DMA **and** 50 DMA > 200 DMA **and** breadth (% of constituents above their 200 DMA) > 55% | Normal |
| **Neutral** | Mixed | Momentum BUYs need trend template ≥ 7/8; position size suggestion halved |
| **Risk-Off** | Benchmark < 200 DMA **and** breadth < 40% | Momentum BUYs capped at **WATCH**; exits tightened |

Small caps typically enter Risk-Off first and fall hardest, so the filter is evaluated **per segment**, not only on the Nifty 50.

**v0.2 regime modifiers:**

- **India VIX** above its 1-year 80th percentile *and* rising: downgrade the regime one level.
- **20-day FII net selling** larger than a threshold (configurable, in ₹ Cr) while DIIs aren't absorbing it: flag "flow headwind".
- **Advance/decline line** diverging from the index (index at a high, A/D falling): flag "narrow rally", which is an early momentum-crash warning.

---

## 6. Scoring model

```
momentum_score (0–100) =                  (v0.2: RS 35 → 30 + EarningsMomentum 5)
    30 × RelativeStrength_subscore
  +  5 × EarningsMomentum_subscore
  + 20 × VolAdjustedMomentum_subscore
  + 25 × TrendStructure_subscore
  + 10 × HighProximity_subscore
  + 10 × VolumeParticipation_subscore
```

### Cap-specific settings (`config/momentum_weights.yaml`)

| Setting | Large | Mid | Small |
|---|---|---|---|
| Primary benchmark | Nifty 100 | Nifty Midcap 150 | Nifty Smallcap 250 |
| Over-extension (above 200 DMA) | 30% | 40% | 50% |
| Breakout volume multiple | 1.5× | 1.75× | 2.0× |
| Trailing stop (from peak close) | 15% or 2.5 × ATR | 20% or 3 × ATR | 25% or 3.5 × ATR |
| Min avg daily traded value | — | ₹5 Cr | ₹1 Cr |
| Weight shift | RS +5, Volume −5 | as base | Vol-adj +5, HighProx −5 |

---

## 7. Momentum verdict (before combining with value)

| Condition | Momentum view |
|---|---|
| Score ≥ 70, Trend Template ≥ 7/8, Stage 2, RS percentile ≥ 70, regime not Risk-Off | **STRONG: BUY candidate** |
| Score 45–70, or Stage 2 with a Trend Template of 5–6 | **NEUTRAL: HOLD / wait for setup** (M02, M03 or M12) |
| Score < 45, or Stage 3/4, or M21/M25 active | **WEAK: REDUCE / SELL / AVOID** |

**Pre-defined exits** (printed in every report for held stocks):

1. **Initial stop:** below the breakout base low or 8–10% below entry (cap-adjusted).
2. **Trailing stop:** per the cap table, whichever is tighter.
3. **Trend exit:** M21 (200 DMA breakdown) or M11 (Death Cross), whichever comes first.
4. **Relative exit:** M25 (RS percentile fading).
5. **Rebalance exit:** at the monthly run, if a stock falls out of the top 30% RS percentile of its segment while a stronger candidate exists.

---

## 8. Time-series analysis (HISTORY.md, momentum section)

| View | Content |
|---|---|
| **RS trajectory** | Excess return vs benchmark over 1M/3M/6M/12M, and RS percentile for each of the last 12 months |
| **Stage timeline** | Month-by-month Weinstein stage (for example 1 → 1 → 2 → 2 → 2 → 3) |
| **Signal log** | Every signal fired, with date, price and outcome 1M/3M later. Over time, this measures how well each signal works *for this stock* |
| **DMA state history** | Golden and Death Cross dates, days since the last cross, and distance from the 200 DMA over time |
| **Score trajectory** | Momentum score and sub-scores for the last 12 months |
| **Regime history** | Segment regime by month |

---

## 9. Output contract (JSON snapshot, momentum section)

```json
"momentum": {
  "benchmark": "NIFTY MIDCAP 150", "sector_index": "NIFTY IT",
  "score": 81, "score_prev": 84,
  "subscores": {"rs": 0.86, "vol_adj": 0.79, "trend": 0.90, "high_prox": 0.85, "volume": 0.55},
  "excess_return": {"1m": 0.021, "3m": 0.094, "6m": 0.187, "12m": 0.312, "12_1": 0.285},
  "rs_percentile": 88, "mansfield_rs": 14.2,
  "dma": {"price": 7120, "dma50": 6890, "dma150": 6410, "dma200": 6200,
          "dma200_slope_20d": 0.031, "pct_above_200": 0.148,
          "last_cross": {"type": "golden", "date": "2026-05-12", "days_since": 135}},
  "trend_template": 8, "stage": 2,
  "pct_from_52w_high": -0.04, "delivery_pct_20d": 0.52,
  "active_signals": ["M01", "M12"],
  "regime": "Risk-On",
  "exit_levels": {"trailing_stop": 5980, "trend_exit_200dma": 6200},
  "momentum_view": "STRONG",
  "asof": "2026-09-23"
}
```

---

## 10. Build checklist (momentum lens)

- [ ] Price and index loader with split and bonus adjustment check (use adjusted close)
- [ ] Indicator library (`analytics/momentum.py`): DMAs, slopes, RS, Mansfield, vol-adjusted z-score, ATR, RSI, OBV
- [ ] Index-constituent loader for segment percentile ranks and breadth
- [ ] Trend Template, Stage classifier and pattern detectors (M01–M26) as pure functions
- [ ] Confirmation / debounce logic, shared with the daily watcher (plan 03)
- [ ] Regime engine per segment
- [ ] (v0.5, D24) Per-measure minimum sessions, 20-session listing exclusion, since-listing high/low substitutes, signal gating, x/y Trend Template
- [ ] Signal-outcome tracker (forward 1M/3M returns after each signal)
- [ ] Phase 5 backtest: 10 years of price data, point-in-time constituents, cost- and slippage-aware
- [ ] (v0.2) Earnings-momentum sub-score; results-day gap detector (M08)
- [ ] (v0.2) Bulk/block deal, delivery-spike and F&O OI loaders (M09)
- [ ] (v0.2) Price-band/circuit and ASM/GSM watchers (M27, M28); index-rebalance and lock-in calendars (M29, M30)
- [ ] (v0.2) Regime modifiers: India VIX, FII/DII flows, A/D line; sector RRG quadrant

---

## 11. Strengthening the momentum lens (v0.3)

| # | Enhancement | What it changes | Why it makes the analysis stronger |
|---|---|---|---|
| 1 | **Dual momentum: absolute + relative** | A BUY also requires the stock's 12-month return to beat the **risk-free / liquid-fund return** (absolute momentum), not just the benchmark | In a falling market, "less bad than the index" still loses money. The absolute filter keeps you out of bear-market "leaders" |
| 2 | **Residual (idiosyncratic) momentum** | RS computed on returns *after removing market beta* (regression vs benchmark) | Research suggests it's more persistent and crashes less than raw momentum. It ranks genuine stock-specific strength above high-beta market ride-alongs |
| 3 | **Path smoothness ("frog-in-the-pan")** | Measures how a stock's return was earned: many small up-days vs a few jumps (e.g. % of positive days, information-discreteness score) | Smooth, gradual trends tend to persist; jump-driven ones reverse. Adds quality to the momentum rank |
| 4 | **Rank buffer to control churn** | Enter at the top 20% RS percentile, exit only below the top 40% (a hysteresis band), similar to how index providers limit turnover | Momentum's biggest hidden cost is turnover |
| 5 | **After-cost, after-tax evaluation** | Backtests and verdict stats include brokerage, STT, slippage and **short-term capital-gains tax** (tax rates in config) | Many high-turnover momentum strategies look great before tax and poor after it. For a personal Indian investor, the after-tax number is the one that matters |
| 6 | **Volatility-scaled position sizing** | Suggested size = portfolio risk budget (e.g. 1% per position) ÷ (entry − stop). Positions are halved when segment volatility is in its top quintile | Research shows volatility scaling significantly reduces momentum crashes |
| 7 | **Multi-timeframe confirmation** | Weekly-chart trend (price above a rising 30-week MA) must agree with the daily signal for High-severity entries | Filters daily noise, especially in small caps |
| 8 | **Signal decay / half-life measurement** | From the signal-outcome log: how many weeks each signal's edge lasts, per cap | Tells you how quickly to act on each alert, and which signals to drop |
| 9 | **Walk-forward validation** | Parameters tuned on rolling in-sample windows and tested out-of-sample; the number of tunable parameters is capped | Guards against a curve-fitted signal set |

*Personal analytical use only; not investment advice. Thresholds are starting points, to be calibrated by backtest.*
