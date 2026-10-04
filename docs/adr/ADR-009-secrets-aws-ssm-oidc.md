# ADR-009: Secrets: AWS SSM Parameter Store via GitHub OIDC

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 13 §3 P1 (docs/plan/)

## Context
- The SCAIX Production checklist requires a managed secret store in production.
- Long-lived cloud keys in GitHub are a leak risk.

## Decision
- Scheduled runs read **SSM Parameter Store (SecureString)** through **GitHub OIDC**; GitHub stores only the role ARN, no long-lived AWS keys.
- Locally, `.env` (in OneDrive, one folder above the repo, D19) found through `PARAKH_ENV_FILE` or automatically.
- Paths per environment: `/parakh/staging/…`, `/parakh/prod/…` (plan 14 §3).
- *(4 Oct 2026)* A job sets `PARAKH_SSM_PATH`; `secrets.load_ssm_environment` copies every parameter under that path into the environment before settings are read. The role (`infra/aws/parakh-github-oidc.yaml`) is limited to the `main` branch of the repo and to read access on that path. Setup steps: `docs/AWS_SETUP.md`.
- **Recorded fallback** if no AWS account: GitHub *environment* secrets with required reviewers (a documented deviation from the SCAIX standard).

## Consequences
- ➕ No static cloud credentials anywhere.
- ➖ Needs an AWS account (backlog BL-01, done 4 Oct 2026) and a one-time OIDC role setup.
