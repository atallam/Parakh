---
title: Automation, Notifications & Continuous Momentum Watch — Plan
version: 1.0 (agentic: Monthly Reviewer agent replaces the Claude scheduled-task review; Event Triage agent in §5b; agents send only through `notify.queue` — plan 15, ADR-003/008 amended; v0.9: Task Scheduler paths fixed to C:\dev\parakh; v0.8 baseline: ADR-003 and ADR-008 accepted, workflow secrets via AWS SSM + OIDC, concall source = BSE-filed transcripts — plan 13; v0.7: §4 rewritten: channel comparison incl. WhatsApp, ADR-008, routing matrix, two-way actions; v0.6: audit hooks → plan 10; v0.4: watchlist; v0.3: ownership routing; v0.2: §0, §5b)
date: 2026-09-24
parent: 00_MASTER_PLAN.md
---

# Automation, Notifications and Continuous Watch

## 0. How it works, in plain terms

The system runs **three automatic jobs**. You don't start any of them; you only read what arrives on your phone.

| Job | When it runs | What it does | What you receive |
|---|---|---|---|
| **1. Monthly Analyst** | 2nd of every month, 09:30 IST | Scores every stock (value, momentum, qualitative), writes the reports, updates each stock's history | **One** Telegram message: upgrades, downgrades, new red flags, and a link to the segment summaries. Right after, the **Monthly Reviewer agent** sends a short "top 5 things to look at" message, with the full review in the monthly email (plan 15 §5) |
| **2. Daily Momentum Watcher** | Every trading day, 18:30 IST | Compares today's closing-price signals with yesterday's saved state | A message **only if something changed** (confirmed over 2 closes, not repeated within 10 days). Nothing changed means no message |
| **3. Event Watcher** *(v0.2)* | Every trading day, 19:00 IST | Checks exchange filings: new results or concall transcript, promoter buy/sell or pledge change, auditor or CFO exit, credit-rating action, ASM/GSM inclusion | An alert for high-severity events. A new concall **refreshes that stock's report automatically**. *(v1.0)* The **Event Triage agent** reads the filings the rules flagged and adds a one-line "why it matters" (§5b) |

**Safety nets:** a ❌ message if any job fails, and a Sunday "all jobs healthy" heartbeat. **Silence never means broken.**

**Where it runs:** GitHub Actions in a private repo, so your laptop can be off. Reports are committed to the repo and synced to your OneDrive folder. Windows Task Scheduler is the fallback.

**Severity routing:**

| Severity | Examples | When you hear about it |
|---|---|---|
| 🔴 **High** | Death Cross, 200 DMA breakdown, surveillance inclusion, auditor resignation, pledge spike | Immediately |
| 🟡 **Medium / Low** | 50 DMA pullback, over-extension, sector rotation | Batched into that evening's single digest |

**Ownership-aware routing (v0.3):** *exit and warning* signals on stocks **you own** are always sent immediately. *Entry* signals on stocks you don't own go into the digest, unless they're High severity *and* the stock is in the top 10% of its cap. Every alert shows 🟢 OWNED with your weight and P&L % where relevant. Quantities and ₹ amounts appear only if you set `notify.include_amounts: true` (plan 12 §8). Holdings come from plan 05 §2.

**Channels (ADR-008 accepted 2026-09-24, plan 13 D5):** Telegram is primary, with buttons to approve suggestions and mark alerts useful or noise. Email carries the monthly archive and the full narrative review from the Monthly Reviewer agent *(v1.0; the Claude push lane was retired because the cloud task can't reach the local-only MCP server, ADR-012)*, and ntfy is an optional loud lane for 🔴 alerts on owned stocks (not enabled at baseline). WhatsApp was evaluated and deferred. Details in §4.

**Watchlist automation (v0.4, plan 06):**
- **Monthly run:** updates the System Watchlist, raises flags on My Watchlist and suggests promotions. The monthly Telegram message includes a "🗂 Watchlist review: N pending" line pointing to the Streamlit Watchlist Review page.
- **Daily and event watchers:** can add a stock **urgently** to the System Watchlist on a High-severity setup (at most 3 per cap per week), so its deep dive runs that night.
- **Target price reached:** a My Watchlist stock hitting your target entry price is sent immediately.

**Where the files land (v0.3):** the code repo lives outside OneDrive (see plan 04 §4 #11). Each run **publishes** the rendered reports into the OneDrive `Stock Analysis` cap folders.


## 1. Price-driven jobs and cadences (the event-driven job is in §5b)

| Job | What it does | Cadence | Runtime |
|---|---|---|---|
| **Monthly Analyst** | Full value + momentum + qualitative scoring, reports, history, segment summaries | Once a month, after month-end close | 5–15 min |
| **Daily Momentum Watcher** | Recomputes DMAs, RS and signals M01–M26; compares with yesterday's saved state; alerts **only on state changes** | Every trading day, ~18:30 IST (after NSE close at 15:30 and bhavcopy publication) | < 2 min |

**Why end-of-day and not real-time?** Every signal in this framework (DMAs, RS, stages, crosses) is defined on **closing prices**. Intraday ticks create false crosses that reverse by the close. End-of-day is the right resolution for this style; see §6 for true real-time options if you ever want them.

---

## 2. Where it runs: options compared

| Option | Laptop must be on? | Cost | Pros | Cons | Verdict |
|---|---|---|---|---|---|
| **A. GitHub Actions (cron)** in a *private* repo | **No** | Free tier is generous for this workload | Fully hands-off; logs; retries; reports committed to git (versioned history for free); secrets store | Cron times are UTC and can start a few minutes late; outputs live in GitHub (sync to OneDrive with `git pull`) | **Recommended primary** |
| **B. Windows Task Scheduler** | Yes (or set to run at next wake) | Free | Writes directly into your OneDrive folder; simplest | Misses runs if the PC is off or asleep (set "run as soon as possible after a missed start") | Good fallback, or for purely local work |
| **C. Claude scheduled task** | Cloud: no. Using your PC: yes | Uses your Claude plan | Can do the **qualitative layer** (read the computed JSON and reports, write narrative, check THESIS.md sell conditions); push and email notification built in | Cloud network is restricted (price sites may be blocked), so the number crunching should stay in Python | ~~Recommended for the monthly narrative review~~ *(v1.0: superseded by `AGENT.monthly_reviewer` running inside job A, which can reach `parakh-mcp`; plan 15)* |
| D. Cloud VM / AWS Lambda + EventBridge | No | Low but non-zero | Production-grade | Overkill for personal use | Later, if this becomes a product |

**Recommended setup** (✅ ADR-003 accepted 2026-09-24, plan 13 D6):

1. **GitHub Actions** runs the Python pipeline (monthly + daily) and sends Telegram alerts.
2. *(v1.0, ADR-003 amended)* At the end of the monthly job, the **Monthly Reviewer agent** (Claude Agent SDK, plan 15 §5) reviews the new snapshots through `parakh-mcp` and sends a short "what changed and what needs your attention" message on Telegram, with the full review in the monthly email.
3. A OneDrive copy comes from a scheduled `git pull` (Task Scheduler), or you open the repo when needed.

---

## 3. Scheduling specifics

### A. GitHub Actions (`.github/workflows/`)

```yaml
# monthly.yml — 2nd of every month, 09:30 IST (04:00 UTC)
on:
  schedule:
    - cron: "0 4 2 * *"
  workflow_dispatch: {}          # manual "Run now" button
jobs:
  monthly:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python run.py --mode monthly --cap all
        env:
          # Baseline (ADR-009): secrets come from AWS SSM Parameter Store via GitHub OIDC
          # (aws-actions/configure-aws-credentials with role-to-assume), loaded at job start;
          # GitHub stores only the role ARN. The names below are what the app reads.
          TELEGRAM_BOT_TOKEN: ${{ env.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ env.TELEGRAM_CHAT_ID }}
          ANTHROPIC_API_KEY:  ${{ env.ANTHROPIC_API_KEY }}
      - run: |
          git config user.name "stock-bot"
          git config user.email "stock-bot@users.noreply.github.com"
          git add large_cap mid_cap small_cap
          git commit -m "Monthly analysis $(date +%Y-%m)" || echo "nothing to commit"
          git push
```

```yaml
# daily_watch.yml — Mon–Fri 18:30 IST (13:00 UTC)
on:
  schedule:
    - cron: "0 13 * * 1-5"
```

- The script checks the **NSE holiday calendar** and exits quietly on market holidays.
- Why the 2nd of the month: the 1st can be a holiday or have late data; the script uses the **last trading day of the previous month** as the as-of date either way.
- GitHub pauses scheduled workflows in *public* repos after 60 days without activity. The monthly commit keeps the repo active, and a private repo is recommended anyway.

### B. Windows Task Scheduler (PowerShell)

Fallback only (ADR-003). Paths follow plan 13 D10: the venv and code live in `C:\dev\parakh`, never in OneDrive.

```powershell
# Monthly: first Saturday of every month at 10:00
schtasks /Create /TN "StockAnalysis-Monthly" /SC MONTHLY /MO FIRST /D SAT /ST 10:00 `
  /TR "\"C:\dev\parakh\.venv\Scripts\python.exe\" \"C:\dev\parakh\run.py\" --mode monthly --cap all"

# Daily watch: weekdays at 18:30
schtasks /Create /TN "StockAnalysis-DailyWatch" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:30 `
  /TR "\"C:\dev\parakh\.venv\Scripts\python.exe\" \"C:\dev\parakh\run.py\" --mode watch --cap all"
```

Afterwards, in Task Scheduler → task → Settings, tick **"Run task as soon as possible after a scheduled start is missed"**, and under Conditions tick **"Wake the computer to run this task"**.

### C. Monthly Reviewer agent (replaces the Claude scheduled task, v1.0)

The last step of `monthly.yml` runs `parakh agents run monthly_reviewer --run-id <run_id>`. The agent starts `parakh-mcp` as a local subprocess (stdio, ADR-012) and may use only its allow-listed tools (plan 15 §5):

- `reports.what_changed` → the verdict changes, red flags, thesis status changes and pending proposals, owned stocks first.
- `reports.get_stock` and `analytics.explain_verdict` for the stocks it picks.
- `portfolio.get_thesis` to check each sell condition; `data.quality` for warnings.
- `notify.queue(template_id="monthly_review", …)` to deliver it: a ≤ 10-line Telegram message and a full section in the monthly email.

It can't change a verdict, a thesis or a watchlist, and it can't send anything that bypasses routing (AG-03, AG-05). If it fails or runs out of budget, the monthly summary still goes out and says "review pending".

---

## 4. Notifications and channels (ADR-008, v0.7)

### 4.1 Channel comparison (checked 2026-09-24)

| Channel | Setup | Cost | Rich content | Two-way actions | Needs a public server for replies? | Fit |
|---|---|---|---|---|---|---|
| **Telegram bot** | 10 min (@BotFather → token → chat id) | Free | HTML/Markdown, images, PDFs; silent sends (`disable_notification`) | **Inline buttons + commands** | **No**: long polling (`getUpdates`) works from a scheduled job; a webhook is optional | ✅ **Primary** |
| **Email** (Gmail SMTP + app password) | 10 min | Free | Full HTML digest, attachments (.ics, CSV) | No | No | ✅ Monthly digest and archive; duplicate of failure alerts |
| **Claude scheduled-task push** | Built in | Your Claude plan | Narrative | No | No | ⏹ *Retired in v1.0*: the monthly narrative review now comes from the Monthly Reviewer agent on Telegram + email (§3C) |
| **ntfy** (ntfy.sh or self-hosted) | 5 min | Free | Priorities up to *max/urgent*; up to 3 action buttons (view / http); Markdown only in the web app | Limited (http buttons need a reachable endpoint) | Only for http actions | 🟡 Optional loud lane for 🔴 High on owned stocks |
| **WhatsApp Business Platform** (Meta Cloud API, official) | Hours to days: Meta Business portfolio, developer app, a **dedicated number not used on your personal WhatsApp**, and **pre-approved message templates** | Per-message pricing since 1 Jul 2025. Utility-template rate in India ≈ ₹0.115 per message before GST and any reseller markup (per an Indian rate card; Meta's page is authoritative). About ₹10–20 a month at this volume. INR billing for Indian accounts must be in place by 31 Dec 2026 | Plain text + template variables; reply buttons / lists | Reply buttons; free-form replies only within 24 h of your last message to the bot | **Yes**: webhook on a public HTTPS endpoint | ⏸ **Deferred** (§4.4) |
| **WhatsApp via unofficial libraries** (whatsapp-web.js, Baileys) automating your personal number | 30 min | Free | Anything | Yes | Needs an always-on session | ❌ **Don't**: against WhatsApp's terms and risks a ban on your personal number |
| **Windows toast** | 2 min | Free | 1–2 lines | No | No | Local Task Scheduler runs only |

Notes:
- Meta's **test number** sends only to recipients you register in the developer portal, and templates made on it can't be reused on a production number. It's fine for a trial, not as the permanent setup.
- From **15 Jan 2026**, Meta's WhatsApp Business Solution terms ban *general-purpose* AI chatbots; business-specific notifications and automations remain allowed. A mirror of this framework's alerts is the allowed kind. An "ask the AI anything" chat on WhatsApp is not the design (plan 12 §6).
- Telegram bot chats and WhatsApp Business messages aren't end-to-end encrypted to your bot. That's why amounts are masked by default (`notify.include_amounts: false`, plan 12 §8).

### 4.2 Decision: ADR-008 (✅ Accepted 2026-09-24, plan 13 D5; ntfy lane not enabled at baseline)

**Telegram is the primary channel (alerts, digests, approvals, feedback). Email carries the monthly archive and the full narrative review. *(Amended 2026-09-27: the Claude push lane is retired; the Monthly Reviewer agent's output goes to Telegram and email. Agents never call a channel directly; they go through `notify.queue`, which applies this routing, de-duplication, cool-downs and masking; plan 15 AG-05.)* ntfy is an optional loud lane. WhatsApp is deferred behind the same `Notifier` interface.**

Why Telegram over WhatsApp for this system:
- Free, set up in minutes, no template approvals.
- Buttons and commands without hosting a public webhook.
- Rich formatting for multi-line digests.
- Bot-initiated messages at any time, with no 24-hour window.

WhatsApp's advantage (it's already on your phone) doesn't outweigh approvals, a dedicated number, templates for every message shape and a public webhook for a single-user tool.

**Routing matrix**

| Message | Telegram | Email | ntfy *(opt.)* |
|---|---|---|---|
| Monthly completion summary | ✅ | ✅ full HTML digest + links (+ .ics of upcoming events) | — |
| Monthly narrative review ("top 5", Monthly Reviewer agent) | ✅ short | ✅ full section in the monthly email | — |
| 🔴 High on **owned** stock (exit/warning signal, veto, auditor exit) | ✅ immediate | — | ✅ max priority |
| 🔴 High entry signal, non-owned, top 10% of cap | ✅ immediate | — | — |
| 🟡 / ⚪ evening digest | ✅ (⚪-only digests sent silently) | — | — |
| Watchlist suggestions | ✅ with buttons (up to 5; the rest via the Streamlit page) | — | — |
| ❌ Failure | ✅ | ✅ | ✅ high |
| Weekly heartbeat | ✅ silent | — | — |

All channels sit behind one interface: `src/notify/base.py: Notifier.send(message: NotificationVM, route: Route)`. Adapters are `telegram.py`, `email.py`, `ntfy.py` and later `whatsapp.py`. Every send, and every suppression, is logged in `alerts_log` (plan 10).

### 4.3 Two-way actions: buttons, commands and where replies are processed

| Action | Where | Effect |
|---|---|---|
| 👍 Useful / 👎 Noise | Every alert | `AUD.ALERT.FEEDBACK`; feeds alert precision (PRD §5) and F17 |
| 🔕 Mute 10d | Every alert | Cool-down override for that signal and stock, with expiry (audited) |
| ✅ Approve / ❌ Reject / 💤 Snooze | Watchlist suggestions | The same service calls as the Streamlit page (plan 06 §5), `AUD.WATCHLIST.*` with `channel=telegram` |
| `/today` `/stock <SYMBOL>` `/pending` `/status` `/mute <1d>` `/privacy on\|off` | Commands | Read-only views of the latest snapshot, plus settings |

**Processing, by phase:**
- **Phase 3:** each scheduled job first calls `getUpdates` and applies pending taps. Telegram keeps undelivered updates for up to 24 hours, so a tap made on Friday night can be lost by Monday's run. That's acceptable for feedback in the first live weeks, but not for approvals, which is why Phase 4 adds the listener below.
- **Phase 4** (when approvals arrive): an always-on listener writes taps and commands to a `ui_actions` table, which the services apply with audit events. Two options:
  - A Supabase Edge Function (webhook; ~50 lines of TypeScript, the only non-Python piece).
  - A Python `python-telegram-bot` listener on your PC, started by Task Scheduler at logon.
  
  The Edge Function is recommended because it doesn't need the PC.

**Security:**
- The bot answers only your chat id; anything else is ignored and logged `AUD.ACCESS.BOT_REJECTED`.
- Button payloads carry a short HMAC-signed token that expires with the suggestion (30 days).
- The bot token lives in secrets.

### 4.4 WhatsApp: when it would make sense, and how

**Revisit triggers (any one):**
- (a) You'd rather not keep Telegram installed.
- (b) Telegram delivery proves unreliable for you.
- (c) A future multi-user version needs the channel people already use.

**If triggered:**
1. Register a Meta Business portfolio and developer app with a dedicated number.
2. Create three **utility** templates with variables: `monthly_summary`, `alert_high`, `daily_digest`.
3. Add `notify/whatsapp.py` behind the same `Notifier` interface.
4. Point its webhook at the same callback listener as Telegram (§4.3).
5. Keep it a *mirror*: same content, same masking, framework commands only.

Estimated effort: 1–2 days, plus template approval time.

### 4.5 Message design

Presentation rules are in plan 12 §6: ≤ 10 lines, emoji + word vocabulary, one evidence bullet, *Open ▸* link, amounts masked, buttons.

**Monthly completion (one message per run):**

```
📊 Monthly Analysis — Sep 2026 ✅ (42 stocks, 8m 12s)
Regime: Large Risk-On · Mid Risk-On · Small Neutral
🟢 OWNED: 2 need attention → POLYCAB ⚪ HOLD→🟡 TRIM · XYZ 🔴 EXIT (veto)
⬆️ Upgrades (3): KPITTECH ⚪ HOLD→🟢 BUY, …
⬇️ Downgrades (2): …
🚩 New red flags (1): XYZ — promoter pledge 18% → 27% (veto)
🗂 Review inbox: 18 items · Watchlist: 3 promote, 2 flagged
⚠️ Data: 1 warning · ❔ 2 checks couldn't run
Open inbox ▸
```

**Daily watcher (sent only if something changed):**

```
🔔 Momentum change — 23 Sep 2026
🟢 KPITTECH (mid) M03 52w-high breakout · vol 2.1× · RS pct 91 · Stage 2   Open ▸
🔴 ABCD (small) 🟢 OWNED wt 3.2% · M21 200-DMA breakdown (2nd close) · stop hit   Open ▸
[👍 Useful] [👎 Noise] [🔕 Mute 10d]
```

**Failure alert:** if a run fails or a data source is down, you always get a ❌ message with the error and the step that failed. Silence should never mean it broke.

**Weekly heartbeat (sent silently):** Sunday, "Watcher alive: 5/5 runs OK this week, 0 signals". This confirms the system is healthy during quiet weeks.

---

## 5. Continuous watch: detecting momentum pattern changes

### State machine per stock

```
state/momentum_state.json
{
  "POLYCAB": {
    "asof": "2026-09-22",
    "above_50": true, "above_200": true, "cross": "golden",
    "stage": 2, "trend_template": 8, "rs_pct_bucket": "top20",
    "active_signals": {"M01": {"since": "2026-09-18", "confirmed": true}},
    "pending": {"M20": {"first_seen": "2026-09-22", "closes": 1}}
  }
}
```

**Daily loop:**

1. Load the latest end-of-day data (yfinance → bhavcopy fallback) and **validate** it: the date equals today's trading date, there are no zero or NaN closes, and the two sources match within 1%.
2. Recompute indicators and states for each stock.
3. **Diff** against yesterday's state and emit an event only on a **transition** (for example `above_200: true → false`).
4. **Confirmation:** move from `pending` to `confirmed` after N=2 closes (configurable per signal). Leading signals like M03 can fire on day 1 with a volume filter.
5. **De-duplication and cool-down:** the same signal for the same stock can't re-alert within 10 trading days unless it reverses and re-fires.
6. **Severity routing:** High goes out immediately. Medium and Low are batched into the day's single digest.
7. Save the new state and append events to each stock's **signal log** (feeds HISTORY.md and signal-outcome tracking).

This gives you **"notify me when a momentum pattern changes"** without constant polling, using one run per trading day.

### Watch scope

- **Default:** every stock in `watchlist.yaml`.
- **Optional "discovery mode":** scan *all* constituents of Nifty Midcap 150 and Smallcap 250 for M01, M02, M03 and M05. This surfaces new candidates that aren't on your watchlist yet (one daily digest, "3 new stocks entered Stage 2").

---

## 5b. Event Watcher (v0.2)

A separate daily job (19:00 IST), because filings arrive on a different rhythm from prices.

| Event | Source | Action |
|---|---|---|
| Results filed / **concall transcript filed** | NSE/BSE announcements; Screener Concalls list (D7) | Re-run value + qualitative for **that stock only**; send a "Results digest" (actual vs expectations, guidance changes, thesis check, verdict impact) |
| Promoter buy or sell, pledge created or released (insider-trading and takeover-code disclosures) | NSE/BSE disclosures | Alert. Promoter buying 🟢, pledge increase 🔴 |
| Auditor resignation, CFO/CEO exit | Announcements | 🔴 immediate; re-check vetoes |
| Credit-rating upgrade or downgrade | Rating-agency releases / announcements | Alert; re-score the balance sheet |
| ASM/GSM inclusion, price-band change | NSE/BSE surveillance lists | 🔴 (M28 / M27) |
| Index inclusion or exclusion announcement | NSE indices / MSCI | 🟡 (M29) |
| Bulk or block deal in a watchlist stock | NSE/BSE | Included in the daily digest |
| Lock-in expiry within 15 days | IPO calendar | 🟡 (M30) |

The Event Watcher shares the **state store, de-duplication and severity routing** of the Momentum Watcher. It keeps `state/events_seen.json` so each filing alerts exactly once.

**Event Triage agent (v1.0, plan 15 §5).** The rules above decide *whether* a filing matters and its maximum severity. For the filings they flag, `AGENT.event_triage` reads the document (as untrusted content, AG-06), writes a one-line "why it matters" and a thesis link, and may:
- queue the alert through `notify.queue` (severity can't exceed the rule's severity for that E-code);
- call `jobs.request_refresh` for a single-stock re-run (at most 5 a day).

If the agent fails or runs out of budget, the rule-based alert still goes out, without the summary line. The agent never suppresses an alert the rules raised.

---

## 6. If you ever want true intraday / real-time

| Option | How | Cost / effort | Recommendation |
|---|---|---|---|
| **Broker APIs**: Zerodha Kite Connect, Upstox, Angel One SmartAPI, Dhan | WebSocket tick stream → compute intraday levels → alert | Some charge for market data; check current pricing. Needs a daily login/token refresh | Only if you move to intraday entries |
| **TradingView alerts** | Set price or indicator alerts in the UI → webhook to Telegram | Paid plans allow more alerts and webhooks | Good no-code complement for a handful of key stocks |
| **Hybrid** | End-of-day watcher (this plan) + a few TradingView price alerts at the exit levels printed in reports | Low | **Best of both** for personal use |

---

## 7. Reliability checklist

- [ ] Idempotent runs: re-running the same month overwrites that month's snapshot and never duplicates history rows
- [ ] Holiday calendar and "data not yet published" detection, with retry after 60 minutes (maximum 3 times)
- [ ] Source fallback with cross-validation, and `data_quality` block written into every snapshot
- [ ] Secrets only in GitHub Secrets / `.env` (python-dotenv); never committed
- [ ] Structured logs (structlog) plus a run summary JSON (`runs/2026-09-02.json`: timings, counts, failures)
- [ ] Failure alert and weekly heartbeat
- [ ] (v0.6) Every job wrapped in `RunContext` / `audited_step`; every alert decision (sent **or suppressed**) logged in `alerts_log`; daily audit integrity check; governance line in the monthly message (plan 10)
- [ ] Tests run in CI before the scheduled job (mocked LLM, golden snapshots; stages in plan 14 §10)
- [ ] OneDrive: keep `data/` cache and any DB out of OneDrive sync (or gitignored) to avoid sync conflicts

---

## 8. Rollout sequence

1. Build Phases 0–2 and run manually for one month-end. Review the reports with you.
2. Add the Telegram notifier and the daily watcher in **dry-run mode** (alerts go to a log file only) for 2 weeks, then tune confirmation and cool-downs. During shadow mode, each entry in `alerts_shadow.md` has a `[ ] noise` checkbox you can tick. When live alerts start, the 👍/👎 buttons (§4.3) are on from day one, so tuning uses recorded feedback rather than impressions.
3. Turn on GitHub Actions schedules.
4. Add the Monthly Reviewer and Event Triage agents (plan 15 §5), first in shadow mode (output to the log only), then live.
5. After 3 monthly cycles, review signal-outcome stats and recalibrate thresholds.
