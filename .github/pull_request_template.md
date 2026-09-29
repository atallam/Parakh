## What and why

## Checklist
- [ ] Tests added or updated; `uv run pytest` passes
- [ ] No secrets, keys or PII in code, logs, fixtures or screenshots
- [ ] Prompt changed? New version file + `prompts/registry.yaml` + golden tests re-run
- [ ] New failure mode? Added to `docs/FAILURE_MODES.md`
- [ ] `aiscaffold.py check .` still green
- [ ] IDs used consistently (MET./M/E/RULE./LENS./TOOL./AGENT./AUD.); catalogues regenerated (`parakh catalogue`)
- [ ] State changes emit an audit event; pipeline steps use `audited_step` (plan 10 §14)
- [ ] Config, weight or prompt change? Reason in the PR and a `# why:` comment in the YAML
- [ ] Plan doc updated if behaviour changed; CHANGELOG entry added
