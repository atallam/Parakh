"""structlog setup: JSON lines with fixed keys (C4.2).

Standard keys: agent_name, tool_called, tokens_in, tokens_out, latency_ms, success.
Fields named like credentials are redacted (C6.2).
Secret-looking values and PII are scrubbed from every string (C6.5).
"""

from __future__ import annotations

import functools
import logging
import re
import sys
import time
from collections.abc import Callable
from typing import Any

import structlog

from parakh.privacy import redact_pii

STANDARD_KEYS = ("agent_name", "tool_called", "tokens_in", "tokens_out", "latency_ms", "success")

REDACTED = "[REDACTED]"
_CREDENTIAL_KEY = re.compile(r"(api_?key|secret|token|password|passwd|authorization|cookie)", re.I)
# Holdings quantities and rupee amounts never reach logs (AC-F21.11, plan 13 P6).
_HOLDINGS_KEY = re.compile(
    r"^(qty|quantity|quantities|shares|units|cost|cost_basis|avg_cost|buy_price|invested"
    r"|value_inr|amount_inr|pnl_inr|market_value|market_value_inr|pan|dp_id|client_id|bo_id)$",
    re.I,
)


def redact_credentials(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """C6.2: any field whose name looks like a credential is replaced, whatever its value."""
    for key in list(event_dict):
        if key != "event" and (_CREDENTIAL_KEY.search(key) or _HOLDINGS_KEY.match(key)):
            event_dict[key] = REDACTED
    return event_dict


_SECRET_VALUES = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),  # Anthropic
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot token
    re.compile(r"eyJ[\w\-]{8,}\.[\w\-]{8,}\.[\w\-]{8,}"),  # JWT (e.g. Supabase keys)
    re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"\b(sk|pk)-(lf|live|test)-[A-Za-z0-9\-]{8,}"),  # Langfuse and similar
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def scrub_text(text: str) -> str:
    for pattern in _SECRET_VALUES:
        text = pattern.sub(REDACTED, text)
    return redact_pii(text)


def scrub_secrets(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """C6.5: scrub secret-looking values and PII from every string in the event."""

    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return scrub_text(value)
        if isinstance(value, dict):
            return {
                k: REDACTED
                if isinstance(k, str) and (_CREDENTIAL_KEY.search(k) or _HOLDINGS_KEY.match(k))
                else clean(v)
                for k, v in value.items()
            }
        if isinstance(value, list | tuple):
            return [clean(v) for v in value]
        return value

    return {key: clean(value) for key, value in event_dict.items()}


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_credentials,
        scrub_secrets,
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer(),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=False,
    )


def logged_tool[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    """Log every tool call with tool_called, latency_ms and success (C4.2)."""
    log = structlog.get_logger(fn.__module__)

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        success = False
        try:
            result = fn(*args, **kwargs)
            success = True
            return result
        finally:
            log.info(
                "tool.call",
                tool_called=fn.__name__,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                success=success,
            )

    return wrapper
