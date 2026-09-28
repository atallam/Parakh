"""Human-in-the-loop checkpoint (C7.3) and graceful degradation (C3.5)."""

import json

import pytest

from parakh.llm.client import LLMError
from parakh.orchestration.graph import run_pipeline


def reply(confidence: float) -> str:
    return json.dumps({"title": "T", "bullets": ["b"], "confidence": confidence})


@pytest.fixture(autouse=True)
def in_tmp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_confident_output_flows_on(fake_llm) -> None:
    result = run_pipeline("text", client=fake_llm(reply(0.95)).client())
    assert result.needs_review is False


def test_low_confidence_waits_for_a_human(fake_llm) -> None:
    result = run_pipeline("text", client=fake_llm(reply(0.2)).client())
    assert result.needs_review is True
    assert "confidence" in result.review_reason
    from parakh.audit.review_queue import default_queue

    assert len(default_queue().pending()) == 1


def test_llm_outage_degrades_instead_of_crashing(fake_llm) -> None:
    result = run_pipeline("text", client=fake_llm(LLMError("down")).client())
    assert result.summary is None
    assert result.needs_review is True
