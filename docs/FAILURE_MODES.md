# Failure modes: Parakh

Documented before first deployment (C7.4). Add a row whenever you find a new way this system can fail.

| # | Failure | Detection | Impact | Automatic response | What you do |
|---|---|---|---|---|---|
| F1 | LLM provider down or timing out | `llm.call success=false`, alert `llm_failure` | Monthly review or triage note missing; rule alerts unaffected | Retries with backoff, then `LLMUnavailable`; the run degrades (no summary) instead of crashing | Nothing if it recovers; check provider status if alerts repeat |
| F2 | Rate limited (429) | Same as F1 | Slower run; notes may be late | Backoff retries; `RateLimiter` spaces calls | Lower `MAX_LLM_CALLS_PER_MINUTE` or spread jobs |
| F3 | Model returns invalid or partial JSON | `agent.invalid_output` warnings | No agent note for that item; the rule result stands | Re-asks with the validation error, up to `LLM_MAX_ITERATIONS`, then `AgentFailed` | Look at the prompt version and golden cases |
| F4 | Low-confidence output | `needs_review=true` | Item waits for you; nothing is acted on | Held in the review queue, not acted on | Approve or reject in the queue |
| F5 | Cost runaway (loops, huge inputs) | `cost_usd` per call; `BudgetExceeded` | Agent notes stop for the run; rules continue | Run stops calling the LLM at `MAX_USD_PER_RUN` | Raise the budget only with a reason |
| F6 | Prompt regression after a change | Golden tests fail in CI | None in production (blocked before merge) | PR blocked | Fix the prompt or roll back `active` in `prompts/registry.yaml` |
| F7 | Secret or PII in logs or traces | Redaction tests; gitleaks in CI | A credential or personal identifier exposed | Credential fields and secret-looking values scrubbed | Rotate the secret if one ever leaks |
| F8 | Missing or wrong configuration | `parakh doctor` | Job does not start; failure alert sent | Startup fails with a clear message | Fix `.env` |
| F9 | Audit trail tampered with or corrupted | `AuditTrail.verify()` returns false | Audit history cannot be trusted | Treated as an incident | Restore from backup; investigate |
| F10 | NSE blocks or rate-limits the announcements, insider or flows feed | Source error reported in the run; filing stays unseen | Events for that source are late; momentum alerts continue | Retries once with fresh cookies; the filing is picked up next run | If it lasts three days, check the feed in a browser and tell me |
| F11 | Telegram send fails or the bot token is revoked | `AUD.ALERT.DELIVERY_FAILED`; failure alert to email | Alerts arrive by email instead of Telegram | Falls back to email; the alert is logged either way | Create a new token with BotFather and update the secret |
| F12 | A scheduled workflow does not run (GitHub outage, disabled workflow) | Sunday heartbeat shows fewer runs than trading days | No watcher or event alerts that day | State is persisted, so the next run catches up on filings within the look-back | Re-run it with the manual trigger; check Actions status |
| F13 | Watcher finishes after 19:30 IST or the monthly summary after 12:00 IST | Service-level breach flagged ⚠️ in the heartbeat | Alerts arrive late | None automatic | Look at the step timings in the run manifest; raise it if it repeats |
| F14 | Price data fails validation (stale, gap, split artefact) | Stock listed as stale in the run summary; state untouched | No signal change for that stock until data is good | Last good state is kept, no estimate is made | Check the price source; refresh the stock |
| F15 | Duplicate or noisy alerts | Shadow log noise boxes; duplicates counted by the daily check | Alert fatigue; you stop trusting the channel | Cool-downs and once-only filing keys; shadow mode before go-live | Tick noise in the log; tune `config/notify.yaml` and `events.yaml` |
| F16 | Audit chain broken or events pending after a sync failure | Daily integrity check; ❌ message | Audit trail not provable until repaired | Pending events are kept locally and retried | Restore from backup and investigate before trusting reports |
| F17 | Agent returns an unsafe note (amount, unlisted stock, injected instruction) | Validation rejects it; `AUD.AGENT.END` shows failed | The monthly summary says "review pending"; triage leaves the alert as is | The rule alert is never changed by an agent | Read the shadow log; roll back the prompt version if it repeats |
| F18 | Muhurat or special session or a missing holiday-calendar year | Calendar gap listed in the run summary | A holiday treated as a trading day: a quiet or late watcher run | Weekends only when a year is missing; special-session bar dropped | Add the year to `config/holidays.yaml` |
| F19 | State branch push conflicts or is lost | Job fails at the save step; ❌ message | Seen filings or cool-downs could repeat once | Job retries the push; state is rebuilt from the run record if needed | Check the `parakh-data` branch and re-run |
