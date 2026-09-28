"""Tools are tested without any LLM (C5.1)."""

import pytest
from structlog.testing import capture_logs

from parakh.mcp.toolsets.text_stats import word_count


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0), ("one", 1), ("two  words", 2), ("line\nbreak\ttab", 3), ("नमस्ते दुनिया", 2)],
)
def test_word_count(text: str, expected: int) -> None:
    assert word_count(text) == expected


def test_tool_calls_are_logged() -> None:
    with capture_logs() as logs:
        word_count("a b")
    assert logs[0]["tool_called"] == "word_count"
    assert logs[0]["success"] is True
    assert "latency_ms" in logs[0]
