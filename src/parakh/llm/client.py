"""LLM client: timeouts, retries with exponential backoff, structured logs, cost.

Treat the provider as an unreliable remote service (C7.1): every call has a timeout,
failures are typed, and callers decide how to degrade.
"""

from __future__ import annotations

import time
from typing import Protocol

import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from parakh.config import Settings, get_settings
from parakh.guardrails import Budget, RateLimiter
from parakh.llm.schemas import LLMResponse, LLMUsage
from parakh.observability.alerts import alert
from parakh.observability.cost import CostTracker
from parakh.observability.tracing import observe

log = structlog.get_logger(__name__)


class LLMError(Exception):
    """A provider failure worth retrying (timeout, rate limit, 5xx, connection)."""


class LLMUnavailable(Exception):
    """Retries are exhausted. Callers degrade gracefully instead of crashing (C3.5)."""


class LLMBackend(Protocol):
    def complete(
        self, *, system: str, prompt: str, model: str, max_tokens: int, timeout_s: float
    ) -> LLMResponse: ...


class AnthropicBackend:
    def __init__(self, api_key: str | None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._retryable = (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        )

    def complete(
        self, *, system: str, prompt: str, model: str, max_tokens: int, timeout_s: float
    ) -> LLMResponse:
        start = time.perf_counter()
        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_s,
            )
        except self._retryable as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        text = "".join(getattr(block, "text", "") for block in message.content)
        return LLMResponse(
            text=text,
            model=message.model,
            usage=LLMUsage(
                input_tokens=message.usage.input_tokens, output_tokens=message.usage.output_tokens
            ),
            latency_ms=(time.perf_counter() - start) * 1000,
        )


class LLMClient:
    """One client per agent run. Pass a fake backend in tests."""

    def __init__(
        self,
        backend: LLMBackend | None = None,
        *,
        agent_name: str = "unknown",
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.agent_name = agent_name
        if backend is None:
            key = self.settings.anthropic_api_key
            backend = AnthropicBackend(key.get_secret_value() if key else None)
        self._backend = backend
        self.cost = CostTracker(
            self.settings.llm_price_input_per_mtok, self.settings.llm_price_output_per_mtok
        )
        self.budget = Budget(self.settings.max_usd_per_run)
        self.rate_limiter = RateLimiter(self.settings.max_llm_calls_per_minute)

    @observe(name="llm.complete")
    def complete(
        self, *, prompt_id: str, system: str, prompt: str, max_tokens: int = 1024
    ) -> LLMResponse:
        self.budget.check()
        self.rate_limiter.acquire()
        try:
            response = self._call(system=system, prompt=prompt, max_tokens=max_tokens)
        except LLMError as exc:
            log.error(
                "llm.call",
                agent_name=self.agent_name,
                prompt_id=prompt_id,
                success=False,
                error=str(exc),
            )
            alert("llm_failure", agent_name=self.agent_name, prompt_id=prompt_id, error=str(exc))
            raise LLMUnavailable(str(exc)) from exc
        usd = self.cost.add(response.usage)
        self.budget.spend(usd)
        dev = self.settings.app_env == "dev"
        log.info(
            "llm.call",
            agent_name=self.agent_name,
            prompt_id=prompt_id,
            model=response.model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=round(response.latency_ms, 1),
            cost_usd=round(usd, 6),
            success=True,
            # prompt/response pairs are logged in dev only (C2.2); processors redact secrets
            prompt=prompt if dev else None,
            response=response.text if dev else None,
        )
        return response

    def _call(self, *, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        s = self.settings
        call = retry(
            reraise=True,
            stop=stop_after_attempt(s.llm_retry_attempts),
            wait=wait_exponential(min=s.llm_retry_min_wait_s, max=s.llm_retry_max_wait_s),
            retry=retry_if_exception_type(LLMError),
        )(self._backend.complete)
        return call(
            system=system,
            prompt=prompt,
            model=s.llm_model,
            max_tokens=max_tokens,
            timeout_s=s.llm_timeout_s,
        )
