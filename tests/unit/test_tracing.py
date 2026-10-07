"""Langfuse tracing (C4.1): span shape, masking and the no-op default.

Spans go to an in-memory exporter, so nothing touches the network. What these tests pin down is
what shows up in Langfuse: observation types and names, model and token usage on generations,
nesting, session grouping, and that secrets and PII never leave the process.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from parakh.agents.monthly_reviewer import run_review
from parakh.agents.roster import run_agent
from parakh.agents.runtime.base import AgentResult, AgentSpec, AgentTask
from parakh.agents.summarizer import summarize
from parakh.audit.context import RunContext
from parakh.audit.emit import get_sink
from parakh.llm.client import LLMError, LLMUnavailable
from parakh.mcp.middleware import Gateway
from parakh.observability import tracing
from parakh.orchestration.graph import run_pipeline
from tests.fakes.agent_runner import FakeRunner, Trajectory, Turn
from tests.helpers.notify import bundle

VALID = '{"title": "T", "bullets": ["b"], "confidence": 0.8}'
LOW = '{"title": "T", "bullets": ["b"], "confidence": 0.1}'

Spans = Callable[[], list[ReadableSpan]]


@pytest.fixture
def spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[Spans]:
    """A real Langfuse client wired to an in-memory exporter, behind the same masking hook."""
    exporter = InMemorySpanExporter()
    client = Langfuse(
        public_key=f"pk-lf-test-{uuid.uuid4().hex}",  # one client per key: keep tests isolated
        secret_key="sk-lf-test",
        base_url="http://localhost:1",
        span_exporter=exporter,
        mask_otel_spans=tracing._mask_otel_spans,
        environment="test",
    )
    monkeypatch.setattr(tracing, "get_langfuse", lambda: client)

    def finished() -> list[ReadableSpan]:
        client.flush()
        return list(exporter.get_finished_spans())

    yield finished
    client.shutdown()


def _by_name(spans: list[ReadableSpan], name: str) -> ReadableSpan:
    (found,) = [s for s in spans if s.name == name]
    return found


def _attrs(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


def _is_child(child: ReadableSpan, parent: ReadableSpan) -> bool:
    assert child.parent is not None and parent.context is not None
    return child.parent.span_id == parent.context.span_id


# -- off by default ----------------------------------------------------------------------------
def test_tracing_is_a_no_op_without_keys_or_in_tests() -> None:
    tracing.reset_tracing()
    assert not tracing.tracing_enabled()
    assert tracing.get_langfuse() is None
    with tracing.observation("anything", as_type="agent", input={"x": 1}) as obs:
        obs.update(output="ignored")  # the null handle accepts every call
    with tracing.trace_attributes(session_id="s", tags=["t"]):
        pass
    tracing.flush_tracing()


def test_test_env_never_traces_even_with_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from parakh import config

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-x")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-x")
    config.get_settings.cache_clear()
    tracing.reset_tracing()
    assert not tracing.tracing_enabled()  # APP_ENV=test wins


def test_the_decorator_runs_the_function_untraced_when_off() -> None:
    @tracing.observe("add-numbers")
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3


# -- the LLM client ----------------------------------------------------------------------------
def test_a_completion_is_one_generation_with_model_usage_and_messages(spans, fake_llm) -> None:
    llm = fake_llm(LLMError("timeout"), VALID)  # one retry, then success
    summarize("quarterly note", client=llm.client())

    gen = _by_name(spans(), "generate-completion")
    a = _attrs(gen)
    assert a["langfuse.observation.type"] == "generation"
    assert a["langfuse.observation.model.name"]  # needed for automatic cost
    assert '"input_tokens"' in a["langfuse.observation.usage_details"]
    assert '"output_tokens"' in a["langfuse.observation.usage_details"]
    assert a["langfuse.observation.input"].startswith('[{"role": "system"')  # chat rendering
    assert '"role": "assistant"' in a["langfuse.observation.output"]
    assert a["langfuse.observation.metadata.agent_name"] == "test"  # set by FakeLLM.client()
    assert a["langfuse.observation.metadata.prompt_id"] == "summarize"
    assert a["langfuse.observation.metadata.attempts"] == 2
    assert float(a["langfuse.observation.metadata.cost_usd"]) > 0


def test_a_failed_completion_is_an_error_generation(spans, fake_llm) -> None:
    llm = fake_llm(*[LLMError("503")] * 10)
    with pytest.raises(LLMUnavailable):
        llm.client().complete(prompt_id="summarize", system="s", prompt="p")

    a = _attrs(_by_name(spans(), "generate-completion"))
    assert a["langfuse.observation.level"] == "ERROR"
    assert a["langfuse.observation.metadata.attempts"] >= 2


def test_pii_and_secrets_are_masked_before_export(spans, fake_llm) -> None:
    llm = fake_llm(VALID)
    llm.client().complete(
        prompt_id="summarize",
        system="Key sk-ant-abcdefghijklmnop1234",
        prompt="Mail rahul@example.com, PAN ABCDE1234F, mobile 9876543210",
    )

    text = _attrs(_by_name(spans(), "generate-completion"))["langfuse.observation.input"]
    for leaked in ("rahul@example.com", "ABCDE1234F", "9876543210", "sk-ant-abcdefghijklmnop"):
        assert leaked not in text
    assert "[EMAIL]" in text and "[PAN]" in text


def test_masking_also_covers_error_messages(spans) -> None:
    with pytest.raises(ValueError), tracing.observation("run-job", as_type="chain"):
        raise ValueError("boom sk-ant-abcdefghijklmnop1234")

    a = _attrs(_by_name(spans(), "run-job"))
    assert a["langfuse.observation.level"] == "ERROR"
    assert "sk-ant" not in a["langfuse.observation.status_message"]


# -- the pipeline tree -------------------------------------------------------------------------
def test_the_pipeline_is_one_nested_trace(spans, fake_llm) -> None:
    run_pipeline("Rahul wrote to rahul@example.com about INDIGO", client=fake_llm(VALID).client())

    s = spans()
    root = _by_name(s, "run-summary-pipeline")
    summarise = _by_name(s, "summarize-text")
    gen = _by_name(s, "generate-completion")
    gate = _by_name(s, "review-summary")
    assert root.parent is None
    assert _is_child(summarise, root) and _is_child(gate, root) and _is_child(gen, summarise)
    types = {sp.name: _attrs(sp)["langfuse.observation.type"] for sp in s}
    assert types == {
        "run-summary-pipeline": "chain",
        "summarize-text": "chain",
        "generate-completion": "generation",
        "review-summary": "evaluator",
    }
    assert "rahul@example.com" not in _attrs(root)["langfuse.observation.input"]
    assert '"needs_review": false' in _attrs(root)["langfuse.observation.output"]


def test_low_confidence_output_shows_up_as_needing_review(spans, fake_llm, tmp_path) -> None:
    run_pipeline("text", client=fake_llm(LOW).client())

    out = _attrs(_by_name(spans(), "review-summary"))["langfuse.observation.output"]
    assert '"needs_review": true' in out


def test_the_summarizer_chain_records_degraded_output(spans, fake_llm) -> None:
    summarize("text", client=fake_llm(*[LLMError("503")] * 10).client())

    out = _attrs(_by_name(spans(), "summarize-text"))["langfuse.observation.output"]
    assert "llm_unavailable" in out


# -- agent runs --------------------------------------------------------------------------------
def _ctx() -> RunContext:
    return RunContext.create(mode="monthly-notify", actor_type="scheduler", actor_id="t")


def test_an_agent_run_is_one_agent_observation_grouped_by_run_id(spans) -> None:
    ctx = _ctx()
    good = {
        "items": [{"symbol": "INDIGO", "tag": "act", "note": "Verdict moved HOLD to REDUCE"}],
        "narrative": "INDIGO weakened this month.\n\nNothing else changed.",
    }
    runner = FakeRunner(
        Gateway.for_client("agent:monthly_reviewer"),
        {f"{ctx.run_id}.review": Trajectory([Turn("mcp__parakh__reports_what_changed")], good)},
    )
    run_review(runner, bundle(), ctx, get_sink(), period="2026-09", allowed_symbols={"INDIGO"})

    run = _by_name(spans(), "run-monthly-reviewer")
    a = _attrs(run)
    assert a["langfuse.observation.type"] == "agent"
    assert a["session.id"] == ctx.run_id  # same ID as the audit trail
    assert set(a["langfuse.trace.tags"]) == {"agent", "monthly-reviewer"}
    assert a["langfuse.trace.name"] == "run-monthly-reviewer"
    assert a["langfuse.trace.metadata.agent_id"] == "AGENT.monthly_reviewer"
    assert '"status": "ok"' in a["langfuse.observation.output"]
    assert "langfuse.observation.level" not in a


class _Stub:
    def __init__(self, result: AgentResult | Exception) -> None:
        self.result = result

    async def run(self, spec: AgentSpec, task: AgentTask, ctx: RunContext) -> AgentResult:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _spec() -> AgentSpec:
    return AgentSpec.from_config(
        "AGENT.monthly_reviewer", bundle(), version="1.0.0", output_model=BaseModel
    )


@pytest.mark.parametrize(
    ("result", "level"),
    [
        (
            AgentResult(agent_run_id="r", agent_id="a", status="pending", reason="turn limit"),
            "WARNING",
        ),
        (RuntimeError("sdk crashed"), "ERROR"),
    ],
)
def test_unfinished_agent_runs_are_flagged_by_level(spans, result, level) -> None:
    ctx = _ctx()
    task = AgentTask(task_id=f"{ctx.run_id}.review", kind="monthly_review")
    run_agent(_Stub(result), _spec(), task, ctx, get_sink(), bundle())

    a = _attrs(_by_name(spans(), "run-monthly-reviewer"))
    assert a["langfuse.observation.level"] == level
    assert a["langfuse.observation.status_message"]


def test_agent_confidence_becomes_a_score(spans, monkeypatch: pytest.MonkeyPatch) -> None:
    scored: list[tuple[str, float]] = []
    monkeypatch.setattr(tracing, "score_current_trace", lambda n, v, **_: scored.append((n, v)))
    from parakh.agents import roster

    monkeypatch.setattr(roster, "score_current_trace", tracing.score_current_trace)
    ctx = _ctx()
    ok = AgentResult(agent_run_id="r", agent_id="a", status="ok", output={"confidence": 0.7})
    task = AgentTask(task_id=f"{ctx.run_id}.review", kind="monthly_review")
    run_agent(_Stub(ok), _spec(), task, ctx, get_sink(), bundle())

    assert scored == [("agent-confidence", 0.7)]


# -- helpers -----------------------------------------------------------------------------------
def test_long_metadata_is_dropped_not_sent(spans) -> None:
    attributes = tracing.trace_attributes(metadata={"short": "ok", "long": "x" * 300, "none": None})
    with attributes, tracing.observation("run-job"):
        pass

    a = _attrs(_by_name(spans(), "run-job"))
    assert a["langfuse.trace.metadata.short"] == "ok"
    assert "langfuse.trace.metadata.long" not in a and "langfuse.trace.metadata.none" not in a
