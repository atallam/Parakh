"""LLM failures raise an alert (C4.4); a broken sink never breaks the caller."""

from parakh.agents.summarizer import summarize
from parakh.llm.client import LLMError
from parakh.observability import alerts


def test_llm_failure_alerts(fake_llm) -> None:
    received: list[str] = []

    def broken_sink(kind: str, fields: dict) -> None:
        raise RuntimeError("sink down")

    alerts.register_sink(lambda kind, fields: received.append(kind))
    alerts.register_sink(broken_sink)
    try:
        assert summarize("text", client=fake_llm(LLMError("down")).client()) is None
    finally:
        alerts.clear_sinks()
    assert received == ["llm_failure"]
