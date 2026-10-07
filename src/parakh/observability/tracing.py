"""Tracing with Langfuse Python SDK v4 (C4.1). A no-op when keys are missing or APP_ENV=test.

What a good trace looks like here (https://langfuse.com/docs/observability/best-practices):
- one trace per unit of work: one agent run, or one summary pipeline run;
- every observation has a stable, verb-first name and the most specific type (`agent`, `chain`,
  `generation`, ...); dynamic values (IDs, symbols, models) go in metadata, never in names;
- `generation`s carry model, token usage, and a role-labelled message list as input and output;
- traces of one job share a `session_id` (the audit `run_id`), so a run is searchable in both;
- nothing leaves the process unmasked: `mask_otel_spans` applies the same secret and PII scrub
  as the logs (C6.2, C6.3, P6) to every span, including spans from third-party instrumentors.

Use `observation()` for a unit of work with explicit input and output, `trace_attributes()` for
session and tags, and `flush_tracing()` before a short-lived process exits. Nothing here can
raise into the application: tracing is best-effort.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, Literal

import structlog

from parakh.config import get_settings

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult

log = structlog.get_logger(__name__)

ObservationType = Literal[
    "span", "generation", "agent", "tool", "chain", "retriever", "evaluator", "guardrail"
]

_MAX_ATTRIBUTE_CHARS = 200  # propagate_attributes drops longer values
_AGENT_SDK_INSTRUMENTED = False


def tracing_enabled() -> bool:
    s = get_settings()
    if s.app_env == "test":
        return False
    return bool(s.langfuse_public_key and s.langfuse_secret_key)


class _NullObservation:
    """What `observation()` yields when tracing is off, so callers never branch."""

    def update(self, **_: Any) -> _NullObservation:
        return self


def _mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Scrub secrets and PII from every string attribute before export (C6.2, C6.3)."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    from parakh.observability.logging import scrub_text

    patches = {}
    for identifier, span in params.spans.items():
        replacements = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                cleaned: Any = scrub_text(value)
            elif isinstance(value, tuple | list) and all(isinstance(v, str) for v in value):
                cleaned = [scrub_text(str(v)) for v in value]
            else:
                continue
            if cleaned != (value if isinstance(value, str) else list(value)):
                replacements[key] = cleaned
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches)


@functools.lru_cache(maxsize=1)
def get_langfuse() -> Langfuse | None:
    """The one Langfuse client, built on first use. None when tracing is off."""
    if not tracing_enabled():
        return None
    try:
        from langfuse import Langfuse

        from parakh.audit.context import code_version

        s = get_settings()
        assert s.langfuse_public_key and s.langfuse_secret_key
        return Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key.get_secret_value(),
            base_url=s.langfuse_host,
            environment=s.app_env,  # keeps dev traces out of prod dashboards
            release=code_version(),  # the git SHA that produced the trace
            mask_otel_spans=_mask_otel_spans,
        )
    except Exception as exc:  # noqa: BLE001 - telemetry must never break the app
        log.warning("tracing.init_failed", error=f"{type(exc).__name__}")
        return None


def reset_tracing() -> None:
    """Forget the cached client (tests, or after the settings changed)."""
    get_langfuse.cache_clear()


def flush_tracing() -> None:
    """Send buffered observations. Call before a short-lived process exits."""
    if get_langfuse.cache_info().currsize == 0:  # nothing was ever traced
        return
    client = get_langfuse()
    if client is not None:
        try:
            client.flush()
        except Exception as exc:  # noqa: BLE001
            log.warning("tracing.flush_failed", error=f"{type(exc).__name__}")


@contextmanager
def observation(
    name: str,
    *,
    as_type: ObservationType = "span",
    input: Any = None,  # noqa: A002 - mirrors the Langfuse field name
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Trace one unit of work as a child of the active observation (or a new root).

    Yields an object with `.update(output=..., metadata=..., usage_details=..., level=...)`.
    An exception marks the observation as an error and propagates unchanged.
    """
    client = get_langfuse()
    if client is None:
        yield _NullObservation()
        return
    kwargs: dict[str, Any] = {"name": name, "as_type": as_type, "input": input}
    if metadata:
        kwargs["metadata"] = metadata
    if as_type == "generation":
        kwargs.update(model=model, model_parameters=model_parameters)
    with client.start_as_current_observation(**kwargs) as obs:
        try:
            yield obs
        except BaseException as exc:
            from parakh.observability.logging import scrub_text

            _safely(
                obs.update,
                level="ERROR",
                status_message=scrub_text(f"{type(exc).__name__}: {exc}")[:300],
            )
            raise


def trace_attributes(
    *,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    version: str | None = None,
    trace_name: str | None = None,
) -> AbstractContextManager[Any]:
    """Attach session, tags and metadata to every observation created inside the block.

    Open it at the root of a trace: only observations created after it carry the attributes.
    Metadata values are stringified and must fit 200 characters; longer ones are dropped.
    """
    if get_langfuse() is None:
        return nullcontext()
    from langfuse import propagate_attributes

    clipped = {
        k: str(v)
        for k, v in (metadata or {}).items()
        if v is not None and len(str(v)) <= _MAX_ATTRIBUTE_CHARS
    }
    return propagate_attributes(
        session_id=session_id,
        tags=tags,
        metadata=clipped or None,
        version=version,
        trace_name=trace_name,
    )


def score_current_trace(name: str, value: float, *, comment: str | None = None) -> None:
    """Attach a numeric score (for example the agent's own confidence) to the active trace."""
    client = get_langfuse()
    if client is not None:
        _safely(client.score_current_trace, name=name, value=value, comment=comment)


def enable_agent_sdk_tracing() -> None:
    """Trace the Claude Agent SDK's turns and tool calls as children of the active observation.

    Needs `uv sync --extra agents`. Without the instrumentor the agent run is still traced by
    `run_agent`, just without the per-turn detail.
    """
    global _AGENT_SDK_INSTRUMENTED
    if _AGENT_SDK_INSTRUMENTED or get_langfuse() is None:
        return
    try:
        from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor

        ClaudeAgentSDKInstrumentor().instrument()
        _AGENT_SDK_INSTRUMENTED = True
    except ImportError:
        log.info("tracing.agent_sdk_instrumentor_missing")
    except Exception as exc:  # noqa: BLE001
        log.warning("tracing.agent_sdk_instrument_failed", error=f"{type(exc).__name__}")


def observe[F: Callable[..., Any]](
    name: str, *, as_type: ObservationType = "span", capture_io: bool = False
) -> Callable[[F], F]:
    """Decorator for functions whose arguments are safe to record.

    Arguments and return values are NOT captured unless `capture_io=True`: by default the SDK
    would record every argument, including settings and clients. Prefer `observation()` and set
    the input and output explicitly.
    """

    def decorate(fn: F) -> F:
        traced: Callable[..., Any] | None = None

        def build() -> Callable[..., Any] | None:
            nonlocal traced
            if traced is None and get_langfuse() is not None:
                from langfuse import observe as lf_observe

                traced = lf_observe(
                    name=name, as_type=as_type, capture_input=capture_io, capture_output=capture_io
                )(fn)
            return traced

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                return await (build() or fn)(*args, **kwargs)

            return awrapper  # pyright: ignore[reportReturnType]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return (build() or fn)(*args, **kwargs)

        return wrapper  # pyright: ignore[reportReturnType]

    return decorate


def _safely(call: Callable[..., Any], /, *args: Any, **kwargs: Any) -> None:
    try:
        call(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - telemetry must never break the app
        log.debug("tracing.call_failed", error=f"{type(exc).__name__}")
