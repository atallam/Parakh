"""Builds the real agent runner for scheduled jobs and the eval CLI (plan 15 §6; ADR-011).

Jobs got `runner=None` until now, so every agent step was skipped. `build_runner` returns the
Claude Agent SDK runner only when a key is present and the SDK is installed (`uv sync --extra
agents`); otherwise it returns None and the job carries on without agents ("qualitative pending").
"""

from __future__ import annotations

import os

import structlog

from parakh.agents.runtime.base import AgentRunner
from parakh.configs import ConfigBundle

log = structlog.get_logger(__name__)


def prompt_names(bundle: ConfigBundle) -> list[str]:
    """Prompt families of the enabled agents: 'qualitative.v1' -> 'qualitative'."""
    return sorted(
        {
            a.prompt_id.rsplit(".", 1)[0]
            for a in bundle.agents.agents.values()
            if a.enabled and a.prompt_id
        }
    )


def build_runner(bundle: ConfigBundle) -> AgentRunner | None:
    from parakh.config import get_settings

    key = get_settings().anthropic_api_key
    if key is None or not key.get_secret_value():
        log.info("agents.runner_off", reason="no ANTHROPIC_API_KEY")
        return None
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        log.warning(
            "agents.runner_off", reason="agents extra not installed (uv sync --extra agents)"
        )
        return None
    os.environ.setdefault("ANTHROPIC_API_KEY", key.get_secret_value())  # the SDK process reads it
    from parakh.agents.roster import sdk_runner

    return sdk_runner(*prompt_names(bundle))
