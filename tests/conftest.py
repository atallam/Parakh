"""Shared fixtures. No test ever reaches a real LLM or the network (C5.3)."""

from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field

import pytest
import structlog

from parakh import config
from parakh.llm.client import LLMClient
from parakh.llm.schemas import LLMResponse, LLMUsage


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch):
    """Tests never read your real .env and never trace."""
    monkeypatch.setattr(config, "env_file", lambda: None)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LLM_RETRY_MIN_WAIT_S", "0")
    monkeypatch.setenv("LLM_RETRY_MAX_WAIT_S", "0")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory):
    """Every test gets its own state dir (audit outbox, run manifests); config stays the repo's."""
    from parakh.audit.emit import reset_sink
    from parakh.render.tokens import tokens

    state = tmp_path_factory.mktemp("state")
    monkeypatch.setenv("PARAKH_STATE_DIR", str(state))
    config.get_settings.cache_clear()
    reset_sink()
    tokens.cache_clear()
    yield state
    reset_sink()


@pytest.fixture(autouse=True)
def reset_logging():
    """configure_logging() binds to the current stderr; undo it so later tests log cleanly."""
    yield
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)


@dataclass
class FakeLLM:
    """Replays canned replies in order (the last one repeats). Exceptions are raised."""

    replies: list[str | Exception]
    calls: list[dict[str, str]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def complete(
        self, *, system: str, prompt: str, model: str, max_tokens: int, timeout_s: float
    ) -> LLMResponse:
        with self._lock:
            self.calls.append({"system": system, "prompt": prompt, "model": model})
            reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            text=reply, model="fake", usage=LLMUsage(input_tokens=120, output_tokens=40)
        )

    def client(self, agent_name: str = "test") -> LLMClient:
        return LLMClient(backend=self, agent_name=agent_name)


@pytest.fixture
def fake_llm():
    """fake_llm('{"title": ...}') -> FakeLLM; use .client() and inspect .calls."""

    def make(*replies: str | Exception) -> FakeLLM:
        return FakeLLM(list(replies))

    return make
