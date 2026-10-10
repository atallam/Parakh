"""The real runner is built only with a key and the SDK; jobs and the eval CLI use it (no network)."""

from __future__ import annotations

import sys

from parakh import config
from parakh.agents.runtime import factory
from parakh.cli import main
from parakh.configs import load_all


def test_prompt_names_are_families_of_enabled_agents() -> None:
    names = factory.prompt_names(load_all())
    assert names == sorted(set(names))
    assert names and all("." not in n for n in names)


def test_no_key_means_no_runner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config.get_settings.cache_clear()
    assert factory.build_runner(load_all()) is None


def test_key_without_sdk_means_no_runner(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    config.get_settings.cache_clear()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)  # import raises ImportError
    assert factory.build_runner(load_all()) is None


def test_runner_built_when_key_and_sdk_present(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import types

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    config.get_settings.cache_clear()
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", types.ModuleType("claude_agent_sdk"))
    seen: list[tuple[str, ...]] = []
    from parakh.agents import roster

    monkeypatch.setattr(roster, "sdk_runner", lambda *n: seen.append(n) or object())
    assert factory.build_runner(load_all()) is not None
    assert seen and "qualitative" in seen[0]


def test_eval_without_runner_exits_2(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(factory, "build_runner", lambda bundle: None)
    assert main(["agents", "eval"]) == 2
    assert "no agent runner" in capsys.readouterr().err


def test_cli_parses_new_commands(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from parakh import cli_agents

    got: dict[str, object] = {}
    monkeypatch.setattr(cli_agents, "concalls_fetch", lambda s: got.setdefault("c", s) and 0)
    monkeypatch.setattr(cli_agents, "agents_eval", lambda s, d: got.setdefault("e", (s, d)) and 0)
    main(["concalls", "fetch", "--symbol", "INDIGO", "--symbol", "M&M"])
    main(["agents", "eval", "--symbol", "INDIGO", "--no-devils-advocate"])
    assert got["c"] == ["INDIGO", "M&M"]
    assert got["e"] == (["INDIGO"], False)
