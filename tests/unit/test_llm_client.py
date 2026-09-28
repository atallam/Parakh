"""Retries, iteration caps and validation (C3.1-C3.4)."""

import pytest

from parakh.agents.summarizer import AgentFailed, extract_json, summarize
from parakh.llm.client import LLMError

VALID = '{"title": "T", "bullets": ["b"], "confidence": 0.8}'


def test_retries_transient_errors(fake_llm) -> None:
    llm = fake_llm(LLMError("timeout"), LLMError("429"), VALID)
    summary = summarize("text", client=llm.client())
    assert summary is not None
    assert len(llm.calls) == 3


def test_invalid_output_is_retried_with_feedback(fake_llm) -> None:
    llm = fake_llm("not json", VALID)
    summary = summarize("text", client=llm.client())
    assert summary is not None
    assert "invalid" in llm.calls[1]["prompt"]


def test_iteration_cap_is_hard(fake_llm, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_ITERATIONS", "3")
    from parakh.config import get_settings

    get_settings.cache_clear()
    llm = fake_llm('{"title": ""}')
    with pytest.raises(AgentFailed):
        summarize("text", client=llm.client())
    assert len(llm.calls) == 3


def test_extract_json_handles_fences_and_prose() -> None:
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == '{"a": 1}'
    assert extract_json('Here: {"a": 1} done') == '{"a": 1}'


def test_cost_is_tracked(fake_llm) -> None:
    llm = fake_llm(VALID)
    client = llm.client()
    summarize("text", client=client)
    assert client.cost.calls == 1
    assert client.cost.usd > 0
