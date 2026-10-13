---
title: Watchlist Management — Auto-Curation with Human Approval
version: 0.8 (parked by D26: callout added, behaviour unchanged behind `watchlist.enabled: false`; v0.7: Watchlist Curator agent adds reasoned proposals through `portfolio.propose_watchlist`; approvals unchanged — plan 15; v0.6: §5.3 aligned with D11; v0.5 §5: cards built from plan 12 components; thesis form on approval; Telegram approve/reject/snooze)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
decisions_confirmed_by_owner:
  autonomy: Two lists — "My Watchlist" (changes only with approval) + "System Watchlist" (auto-managed, capacity-limited)
  cadence: Monthly review with the main run + mid-month urgent adds for high-severity setups
  add_sources: [top_combined_score, momentum_setup, value_buy_zone, smart_money_events]
  approval_ui: Streamlit page
supersedes: 05_STORAGE_UNIVERSE_AND_HOLDINGS.md §1 "Promotion rules"
---

# Watchlist Management

> **Parked (D26, 2026-10-14).** Parakh now covers your holdings only (plan 17). This design stays as written and is switched off by `watchlist.enabled: false` (default). My Watchlist can be re-enabled for a handful of names after M1; the System Watchlist, Curator and discovery stay parked.

## 1. Evaluation summary: why this feature exists

| | |
|---|---|
| **Problem** | A manually kept watchlist slowly fills with names you've stopped caring about, while new opportunities surfaced by the full-cap screen never reach deep analysis |
| **Value** | Links the screen to your deep dives; keeps the LLM cost of Tier A predictable; every entry has a reason and a review date; builds a record of which idea sources actually work |
| **Main risks** | Losing your intent (auto-removing a stock you're patiently waiting on); churn and chasing recent winners; alert noise; duplicating the tier-promotion logic |
| **Design answer** | **Two lists**, protected manual entries, capacity limits with a one-in-one-out rule, minimum stay, **one** monthly review, and approvals on a **Streamlit page**. This plan **replaces** the promotion rules in plan 05 rather than adding a second mechanism |
| **Effort** | Low to medium (about 2–3 days including a minimal Streamlit page); reuses scores, signals and storage |
| **Verdict** | ✅ **Build it, in Phase 4** |

---

## 2. The two lists

| | **My Watchlist** (manual) | **System Watchlist** (auto) |
|---|---|---|
| Who changes it | **Only you**, directly or by approving a suggestion | The pipeline, automatically, within the rules below |
| Auto-removal | **Never.** It can only be *flagged* for your review | Yes, by the removal rules in §4 |
| Size limit | None (soft warning above 25 per cap) | Large **10**, Mid **15**, Small **15** (configurable) |
| Coverage tier | Tier A (deep dive) | Tier A (deep dive) |
| Alerts | Entry signals in the digest; High severity immediate | Entry signals in the digest only |
| Typical content | Stocks you're waiting on for a price, sector bets, thesis-driven ideas | Screen winners, fresh setups, smart-money names |

**Coverage tier A is now:** stocks you **own** + **My Watchlist** + **System Watchlist**. This replaces plan 05's promotion rules.

**Lifecycle of a stock:**

```
          Tier B screen (all stocks in cap)
                     │  add rules (§3) — automatic
                     ▼
            ┌──────────────────┐   you approve "Promote"    ┌──────────────┐
            │ System Watchlist │ ─────────────────────────► │ My Watchlist │
            └──────────────────┘                            └──────────────┘
                 │  removal rules (§4) — automatic              │  flagged → you approve "Remove"
                 ▼                                              ▼
            ┌───────────────────────────── Archive ("graveyard") ─────────────────────────┐
            │  still tracked in Tier B · used for the watchlist scorecard & "missed" review │
            └──────────────────────────────────────────────────────────────────────────────┘
   Buy a stock → status "Owned" (holdings take over). Sell it → you're asked: keep on My Watchlist or archive?
```

---

## 3. Addition rules (System Watchlist)

### 3.1 Sources (all four confirmed)

| Source ID | Trigger | Anti-chasing / quality guard |
|---|---|---|
| `SRC.top_combined` | Top 10% of its cap on the combined value + momentum verdict | No veto; liquidity floor met |
| `SRC.momentum_setup` | M02 (Stage 1→2), M03 (52-week-high breakout on volume), M01 (RS line new high first), M05 (Trend Template newly 8/8), M08 (earnings gap and hold) | **Not** over-extended (M24 inactive); not a circuit trap (M27); regime not Risk-Off |
| `SRC.value_zone` | Margin of safety crosses the required level for its cap, with quality sub-score ≥ 0.6 | **Value-trap flag must be off** (plan 01 §11); no governance veto |
| `SRC.smart_money` | Promoter open-market buying, MF scheme count rising 3+ months, index inclusion announced (M29), institutional block buy | Excludes ESOP allotments, gifts and inter-promoter transfers |

### 3.1b Agent proposals (v0.7, plan 15 §5)

After the monthly scoring, `AGENT.watchlist_curator` reads the segment summaries and pending suggestions through `parakh-mcp` and may add **proposals** with a written reason and evidence references (`portfolio.propose_watchlist`). They're a fifth input next to the four rule-based sources:
- Proposals go into the same **Pending review** tab and Telegram cards, marked 🤖 with the agent's one-line reason.
- The same capacity limits, minimum stays and 30-day expiry apply; a proposal never bypasses §3.2 or §4.
- The agent can't approve, reject or remove anything; My Watchlist still changes only with your approval (ADR-005, AG-03).
- Each proposal is audited as `AUD.WATCHLIST.SUGGESTED` with `actor_id=agent:watchlist_curator@<version>`, so the quarterly scorecard (§6) can compare agent proposals with rule-based ones.

### 3.2 Priority when capacity is limited

Candidates are ranked by:

1. **Number of independent sources agreeing.** For example, value zone + smart money outranks either alone; this is the strongest ordering rule.
2. Combined score.
3. Liquidity.

**One-in-one-out:** when the list is full, a new candidate enters only if it beats the **weakest current entry** by ≥ 10 combined-score points, and that entry has served its minimum stay. This stops churn.

### 3.3 Cadence (confirmed)

| When | What happens |
|---|---|
| **Monthly run** | Full review: additions, removals, flags on My Watchlist, and promotion suggestions. **One** review summary |
| **Mid-month urgent adds** (daily watcher / event watcher) | Only for **High-severity** setups (M01, M02, M03, M05, M08, promoter buying). The stock goes straight onto the System Watchlist, so a deep dive runs that night. At most **3 urgent adds per cap per week**, and it's mentioned in the daily digest ("➕ added to System Watchlist: KPITTECH (M03)") |

---

## 4. Removal and flag rules

### 4.1 System Watchlist: automatic removal (after a minimum stay of **2 monthly cycles**, except for vetoes)

| Rule ID | Condition |
|---|---|
| `RM.fade` | Outside the top 20% of its cap for **3 consecutive** monthly runs |
| `RM.veto` | Any red-flag veto (immediate; the minimum stay doesn't apply) |
| `RM.setup_failed` | A momentum-source entry whose setup failed: price back inside the base or below the breakout level for 10 sessions, or M21 fires |
| `RM.value_closed` | A value-zone entry whose price rose above fair value (the opportunity passed without you acting); it's recorded as a "missed" item |
| `RM.bumped` | Displaced by the one-in-one-out rule |
| `RM.cap_migration` | Moved to another cap (re-evaluated for that cap's list) |
| `RM.corporate` | Delisted, merged or suspended |

### 4.2 My Watchlist: flags only (you decide)

| Flag | Condition | Suggested action |
|---|---|---|
| `FLAG.stale_review` | Review date passed (default 6 months after adding) | Re-confirm or remove |
| `FLAG.persistently_weak` | Bottom 40% of its cap for 6 months *and* no progress toward your target entry price | Remove? |
| `FLAG.veto` | Red-flag veto triggered | Remove? (strongly suggested) |
| `FLAG.thesis_broken` | A "sell/abandon if…" condition in THESIS.md was met | Remove? |
| `FLAG.target_hit` 🟢 | Price reached your target entry price or the value BUY zone | **Act now?** (sent through the daily watcher, not the monthly review) |

### 4.3 Promotion suggestions (System → My)

- A System entry that has stayed on the list for ≥ 3 months with its combined score still in the top 20% gets a "Promote to My Watchlist?" suggestion.
- If you reject it twice, it's never suggested again unless its thesis source changes.

---

## 5. Approval UI: Streamlit "Watchlist Review" page (confirmed)

### 5.1 Screens

| Tab | Content |
|---|---|
| **Pending review** | One card per suggestion: symbol, cap, 🏷 source badges, combined / value / momentum scores, a one-line reason, a 12-month sparkline with 50/200 DMA, a link to the report, and **Approve / Reject / Snooze 30 days** buttons (reject reason optional). Bulk-approve checkboxes |
| **My Watchlist** | Table (`st.data_editor`): reason, target entry price, review date, tags, current verdict, flags. Add a stock by name/symbol search (ISIN lookup) with a **required reason**. Remove with a reason |
| **System Watchlist** | Current entries, source, days on list, removal-risk indicator, capacity bar per cap |
| **Archive & Scorecard** | Removed names still tracked; the quarterly watchlist scorecard (§6) |

**Card anatomy (v0.5, plan 12 §4).** Each Pending review card is a `UI.suggestion_card`, built from:
- `UI.verdict_chip`, source badges, and Value/Momentum `UI.score_ring`s with Δ.
- The first `UI.evidence_list` bullet as the one-line reason.
- A `UI.sparkline` (12 months, 50/200 DMA).
- A `UI.range_bar` showing the value BUY zone and your target entry price.
- Tri-state `UI.check_row`s for any veto checks that couldn't run.

**Thesis at the moment of decision (v0.5, UX-08).** Approving an *add to My Watchlist* or a *promotion* opens the thesis form (plan 12 §5.3), pre-filled with the suggestion's reason. You can skip it; skipped entries are counted in the Home banner rather than nagged per row.

### 5.2 Behaviour

- Suggestions expire after **30 days** if you don't act (status `expired`), so they don't pile up.
- Every decision is logged with a timestamp and reason (audit trail, and training data for the scorecard).
- The monthly Telegram summary includes a count: "🗂 Watchlist review: 3 promote, 2 flagged, 4 auto-added, 3 auto-removed → open the Watchlist Review page".
- *(v0.5)* **From your phone:** up to 5 pending suggestions are also sent as Telegram cards with ✅ Approve · ❌ Reject · 💤 Snooze buttons (plan 03 §4.3). They call the same service as the page and are audited as `AUD.WATCHLIST.*` with `channel=telegram`. Anything needing a reason or a thesis opens the Streamlit page instead. This needs the always-on Telegram listener that arrives in Phase 4.
- **Until the Streamlit page ships**, the same actions are available via the CLI: `python run.py watchlist pending | approve 1 3 | reject 2 --reason "too cyclical" | add TCS --reason "…" `.

### 5.3 Where it runs, and the storage consequence

- The pipeline runs on GitHub Actions, and the Streamlit page must read and write the **same** suggestions and watchlist tables. Supabase is live from Phase 1 (plan 13 D11), and the watchlist and suggestion tables are added to it in Phase 4. Price history stays in Parquet/DuckDB.
- **Start local** (`streamlit run app/Home.py` on your PC, pointing at Supabase), which is the most private option. **Option later:** host it (Render, like WealthLens, or Streamlit Community Cloud) behind login, so you can review from your phone. The page must never be public, because it shows holdings.

---

## 6. Watchlist scorecard (quarterly, learning loop)

| Metric | Question it answers |
|---|---|
| Forward 3M/6M/12M return vs cap benchmark, **by add source** | Which idea source works best for *you*? |
| My Watchlist vs System Watchlist hit rates | Does your judgement add value over the screen? |
| Archive "missed" returns (removed names that rallied afterwards) | Are removal rules too aggressive? |
| Approve/reject rates by source | Which suggestions are just noise to you? |
| Time from entering the watchlist to purchase, and the result | Does waiting for your target price pay off? |

Source priorities in §3.2 can then be re-weighted from evidence rather than opinion.

---

## 7. Data model additions (Supabase)

| Table | Key columns |
|---|---|
| `watchlist_entries` | entry_id, isin, list (`my`\|`system`), cap, status (`active`\|`owned`\|`archived`), added_on, added_by, sources[], reason, target_entry_inr, review_on, min_stay_until, removed_on, removal_rule, removal_reason |
| `watchlist_suggestions` | sugg_id, isin, action (`promote`\|`remove_my`\|`add_my`), sources[], evidence (json: scores, signals, links), run_id, status (`pending`\|`approved`\|`rejected`\|`snoozed`\|`expired`), decided_on, decision_note |
| `watchlist_events` | event_id, entry_id, type (added / removed / flagged / promoted / urgent_add), rule_id, run_id, at |

---

## 8. Configuration (`config/watchlist.yaml`)

```yaml
system_watchlist:
  capacity: { large_cap: 10, mid_cap: 15, small_cap: 15 }
  min_stay_cycles: 2                 # why: prevents month-to-month churn
  bump_margin_points: 10             # why: one-in-one-out buffer
  fade_rule: { outside_top_pct: 20, consecutive_runs: 3 }
  urgent_adds: { enabled: true, max_per_cap_per_week: 3, signals: [M01, M02, M03, M05, M08, E_PROMOTER_BUY] }
  sources: [SRC.top_combined, SRC.momentum_setup, SRC.value_zone, SRC.smart_money]
my_watchlist:
  default_review_months: 6
  weak_flag: { bottom_pct: 40, months: 6 }
  soft_size_warning_per_cap: 25
promotion:
  min_months_on_system: 3
  stay_top_pct: 20
  max_rejections_before_mute: 2
suggestions:
  expire_after_days: 30
```

---

## 9. Build checklist

- [ ] Tables + repository methods (Supabase) for entries, suggestions, events
- [ ] Rule engine: add sources, priority, one-in-one-out, removal rules, flags (IDs `SRC.*`, `RM.*`, `FLAG.*` per plan 04 §3.1)
- [ ] Urgent-add hook in the daily and event watchers, with a weekly cap
- [ ] Monthly review summary in the Telegram message and the segment summary
- [ ] CLI fallback (`watchlist pending/approve/reject/add/remove`)
- [ ] **Streamlit Watchlist Review page (minimal version pulled into Phase 4)**; full dashboard remains Phase 6
- [ ] Watchlist scorecard (quarterly)
- [ ] Tests: capacity limits, minimum stay, veto bypass, expiry, "My list never auto-removed" invariant
