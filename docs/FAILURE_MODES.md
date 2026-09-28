# Failure modes: Parakh

Documented before first deployment (C7.4). Add a row whenever you find a new way this system can fail.

| # | Failure | Detection | Automatic response | What you do |
|---|---|---|---|---|
| F1 | LLM provider down or timing out | `llm.call success=false`, alert `llm_failure` | Retries with backoff, then `LLMUnavailable`; the run degrades (no summary) instead of crashing | Nothing if it recovers; check provider status if alerts repeat |
| F2 | Rate limited (429) | Same as F1 | Backoff retries; `RateLimiter` spaces calls | Lower `MAX_LLM_CALLS_PER_MINUTE` or spread jobs |
| F3 | Model returns invalid or partial JSON | `agent.invalid_output` warnings | Re-asks with the validation error, up to `LLM_MAX_ITERATIONS`, then `AgentFailed` | Look at the prompt version and golden cases |
| F4 | Low-confidence output | `needs_review=true` | Held in the review queue, not acted on | Approve or reject in the queue |
| F5 | Cost runaway (loops, huge inputs) | `cost_usd` per call; `BudgetExceeded` | Run stops calling the LLM at `MAX_USD_PER_RUN` | Raise the budget only with a reason |
| F6 | Prompt regression after a change | Golden tests fail in CI | PR blocked | Fix the prompt or roll back `active` in `prompts/registry.yaml` |
| F7 | Secret or PII in logs or traces | Redaction tests; gitleaks in CI | Credential fields and secret-looking values scrubbed | Rotate the secret if one ever leaks |
| F8 | Missing or wrong configuration | `parakh doctor` | Startup fails with a clear message | Fix `.env` |
| F9 | Audit trail tampered with or corrupted | `AuditTrail.verify()` returns false | Treated as an incident | Restore from backup; investigate |
