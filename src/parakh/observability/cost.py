"""Token cost per workflow run (C4.3). Prices are per million tokens; keep them current in .env."""

from __future__ import annotations

from parakh.llm.schemas import LLMUsage


class CostTracker:
    def __init__(self, price_input_per_mtok: float, price_output_per_mtok: float) -> None:
        self.price_input = price_input_per_mtok
        self.price_output = price_output_per_mtok
        self.input_tokens = 0
        self.output_tokens = 0
        self.usd = 0.0
        self.calls = 0

    def add(self, usage: LLMUsage) -> float:
        usd = (
            usage.input_tokens * self.price_input + usage.output_tokens * self.price_output
        ) / 1_000_000
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.usd += usd
        self.calls += 1
        return usd

    def summary(self) -> dict[str, float]:
        return {
            "calls": self.calls,
            "tokens_in": self.input_tokens,
            "tokens_out": self.output_tokens,
            "cost_usd": round(self.usd, 6),
        }
