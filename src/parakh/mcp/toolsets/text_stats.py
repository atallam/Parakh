"""Example tool with unit tests (C5.1). Replace with real tools."""

from __future__ import annotations

from parakh.observability.logging import logged_tool


@logged_tool
def word_count(text: str) -> int:
    """Number of whitespace-separated words."""
    return len(text.split())
