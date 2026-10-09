"""Variable names a metric breaker's rule may use (`parakh thesis variables`), for the form's validation."""

from __future__ import annotations

from parakh.registry import REGISTRY, discover
from parakh.thesis.status import BUILTIN_UNITS, variable_names


def known_variables() -> set[str]:
    discover()
    return set(variable_names(REGISTRY.metrics.keys())) | set(BUILTIN_UNITS)
