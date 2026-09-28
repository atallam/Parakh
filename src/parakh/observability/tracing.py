"""Tracing with Langfuse (C4.1). A no-op when keys are missing, so tests and CI never trace."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from parakh.config import get_settings


def tracing_enabled() -> bool:
    s = get_settings()
    if s.app_env == "test":
        return False
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return False
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key.get_secret_value())
    os.environ.setdefault("LANGFUSE_HOST", s.langfuse_host)
    return True


def observe[F: Callable[..., Any]](name: str) -> Callable[[F], F]:
    """Decorator that traces a function when tracing is configured."""

    def decorate(fn: F) -> F:
        if not tracing_enabled():
            return fn
        try:
            from langfuse import observe as lf_observe  # langfuse v3
        except ImportError:  # pragma: no cover - langfuse v2
            from langfuse.decorators import (  # pyright: ignore[reportMissingImports]
                observe as lf_observe,
            )
        return lf_observe(name=name)(fn)  # pyright: ignore[reportReturnType]

    return decorate
