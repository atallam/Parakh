# ADR-006: UI: Streamlit first, thin UI over a service layer

- **Status:** Accepted
- **Date:** 2026-09-24
- **Deciders:** Avinash (owner)
- **Detailed in:** plan 04 §5.2; plan 12 (docs/plan/)

## Context
- Phase 4 needs approvals, a holdings editor and a dashboard: free, easy to deploy, Python, never public.
- A future wish for animated pages.

## Decision
- **Streamlit** for Phase 4, run locally first. Pages call **services only** (`services/`, `view_models.py`) and contain no business logic; the same rule binds `src/parakh/mcp/` (lint in `tools/lint_rules.py`).
- One design system for every surface: `config/ui_tokens.yaml` + `render/format.py` + `app/ui/components.py` (plan 12). No hex colour outside the tokens file (lint).
- No network or LLM calls during page render; AppTest per page.
- Animation-heavy pages later: FastAPI + React over the same services.

## Consequences
- ➕ Fastest build; surfaces can't disagree because they share view models.
- ➖ Whole-script re-runs; phone access needs hosting behind a login.
- Revisit when: UI animation beyond charts is wanted, common pages exceed ~2 s, or multi-user access is needed (fallback: NiceGUI).
