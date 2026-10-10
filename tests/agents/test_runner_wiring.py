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


def test_failure_reason_carries_a_scrubbed_message() -> None:
    from parakh.agents.roster import _why

    msg = _why(RuntimeError("cannot start claude\nsecond line"))
    assert msg == "RuntimeError: cannot start claude"
    assert _why(RuntimeError("")) == "RuntimeError"
    assert len(_why(RuntimeError("x" * 500))) < 200


def test_qualitative_task_tells_the_agent_how_to_fetch_the_transcript() -> None:
    """The first priced eval failed because the agent got a hash, not isin + doc_type."""
    from parakh.agents.qualitative import run_qualitative  # noqa: F401
    from parakh.agents.runtime.base import AgentTask

    seen: list[AgentTask] = []

    class Spy:
        def run(self, spec, task, ctx):  # type: ignore[no-untyped-def]
            from parakh.agents.runtime.base import AgentResult

            seen.append(task)
            return AgentResult(agent_run_id=task.task_id, agent_id=spec.agent_id, status="failed")

    import dataclasses

    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.services.documents import CachedDoc

    bundle = load_all()
    bundle = dataclasses.replace(
        bundle,
        flags=bundle.flags.model_copy(
            update={"qualitative": bundle.flags.qualitative.model_copy(update={"enabled": True})}
        ),
    )
    doc = CachedDoc(
        isin="X",
        symbol="X",
        period="2026-07",
        source_url="u",
        sha256="sha256:ab",
        fetched_on="2026-10-10",
        pages=1,
        text="t",
        notes=[],
    )  # type: ignore[call-arg]
    ctx = RunContext.create(mode="t", actor_type="system", actor_id="t")
    run_qualitative(Spy(), bundle, ctx, get_sink(), isin="X", symbol="X", doc=doc)  # type: ignore[arg-type]
    assert seen and seen[0].inputs["doc_type"] == "transcript"


def test_long_transcript_comes_in_parts_that_cover_all_text(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from parakh.mcp.toolsets import data

    text = "".join(f"line {i} of the call. " for i in range(3000))
    doc = type(
        "D",
        (),
        {
            "text": text,
            "sha256": "sha256:abcdefabcdef1234",
            "source_url": "u",
            "period": "2026-07",
            "is_stale": lambda self, *a: False,
        },
    )()
    monkeypatch.setattr(
        data.docs_service.TranscriptStore, "get", lambda self, isin, previous=False: doc
    )
    got, offset, parts = "", 0, 0
    while True:
        out = data._transcript(data.GetDocumentIn(isin="X", doc_type="transcript", offset=offset))
        assert out.untrusted_content is not None
        got += out.untrusted_content.text
        parts += 1
        if out.next_offset is None:
            break
        offset = out.next_offset
    assert got == text and parts > 1
