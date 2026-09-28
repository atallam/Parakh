"""Pydantic models for everything that crosses the LLM boundary (C3.3)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    text: str
    model: str
    usage: LLMUsage = Field(default_factory=LLMUsage)
    latency_ms: float = 0.0


class AgentOutput(BaseModel):
    """Base class for every structured agent output."""

    confidence: float = Field(
        ge=0.0, le=1.0, description="0-1; low values go to human review (C7.2, C7.3)"
    )


class Summary(AgentOutput):
    title: str = Field(min_length=1, max_length=120)
    bullets: list[str] = Field(min_length=1, max_length=5)
