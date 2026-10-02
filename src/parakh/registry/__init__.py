"""Registries for metrics, signals, rules and lenses (plan 04 §3.1).

Every business concept has a stable ID that appears the same in docs, config, code, tests, logs
and reports. Registering validates the ID pattern and the docstring sections, and the generated
catalogues (docs/METRICS.md, SIGNALS.md, RULES.md) come from here (AC-F18.4).

    @register_metric(id="MET.value.pe_vs_5y_median", unit="ratio",
                     inputs=["prices.close", "fundamentals.eps_ttm"], used_by=["LENS.value"])
    def pe_vs_5y_median(...): ...

    @register_lens("value")
    class ValueLens(Lens): ...
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from parakh.lenses.base import Lens

METRIC_ID = re.compile(r"^MET\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
SIGNAL_ID = re.compile(r"^[ME]\d{2}$")
RULE_ID = re.compile(r"^RULE\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
LENS_ID = re.compile(r"^[a-z][a-z0-9_]*$")
Unit = Literal["ratio", "pct", "x", "cr", "inr", "days", "bps", "count", "score", "bool"]
REQUIRED_DOC_SECTIONS = ("Formula:", "Meaning:", "Pitfalls:", "Source:")


class RegistryError(ValueError):
    pass


def _check_doc(kind: str, ident: str, fn: Callable[..., Any]) -> str:
    doc = (fn.__doc__ or "").strip()
    missing = [s for s in REQUIRED_DOC_SECTIONS if s not in doc]
    if missing:
        raise RegistryError(f"{kind} {ident}: docstring is missing {missing} (plan 04 §3.2)")
    return doc


@dataclass(frozen=True)
class MetricSpec:
    id: str
    unit: str
    inputs: list[str]
    used_by: list[str]
    fn: Callable[..., Any]
    doc: str


@dataclass(frozen=True)
class SignalSpec:
    id: str
    name: str
    lens: str
    severity: Literal["High", "Medium", "Low"]
    fn: Callable[..., Any]
    doc: str


@dataclass(frozen=True)
class RuleSpec:
    id: str
    kind: Literal["veto", "policy", "check", "flag"]
    fn: Callable[..., Any]
    doc: str


@dataclass
class Registries:
    metrics: dict[str, MetricSpec] = field(default_factory=dict)
    signals: dict[str, SignalSpec] = field(default_factory=dict)
    rules: dict[str, RuleSpec] = field(default_factory=dict)
    lenses: dict[str, type[Lens]] = field(default_factory=dict)


REGISTRY = Registries()


def _add[T](table: dict[str, T], ident: str, spec: T, kind: str) -> None:
    if ident in table:
        raise RegistryError(f"{kind} {ident} is registered twice")
    table[ident] = spec


def register_metric(
    *, id: str, unit: Unit, inputs: list[str], used_by: list[str]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not METRIC_ID.match(id):
        raise RegistryError(f"metric id {id!r} must look like MET.<lens-or-common>.<name>")

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _add(
            REGISTRY.metrics,
            id,
            MetricSpec(id, unit, inputs, used_by, fn, _check_doc("metric", id, fn)),
            "metric",
        )
        return fn

    return deco


def register_signal(
    *, id: str, name: str, lens: str, severity: Literal["High", "Medium", "Low"]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not SIGNAL_ID.match(id):
        raise RegistryError(f"signal id {id!r} must look like M<nn> or E<nn>")

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _add(
            REGISTRY.signals,
            id,
            SignalSpec(id, name, lens, severity, fn, _check_doc("signal", id, fn)),
            "signal",
        )
        return fn

    return deco


def register_rule(
    *, id: str, kind: Literal["veto", "policy", "check", "flag"]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if not RULE_ID.match(id):
        raise RegistryError(f"rule id {id!r} must look like RULE.<area>.<name>")

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        _add(REGISTRY.rules, id, RuleSpec(id, kind, fn, _check_doc("rule", id, fn)), "rule")
        return fn

    return deco


def register_lens(lens_id: str) -> Callable[[type[Lens]], type[Lens]]:
    if not LENS_ID.match(lens_id):
        raise RegistryError(f"lens id {lens_id!r} must be snake_case")

    def deco(cls: type[Lens]) -> type[Lens]:
        if not issubclass(cls, Lens):
            raise RegistryError(f"LENS.{lens_id}: {cls.__name__} must subclass Lens")
        cls.lens_id = lens_id
        _add(REGISTRY.lenses, lens_id, cls, "lens")
        return cls

    return deco


DISCOVERY_PACKAGES = (
    "parakh.analytics.metrics",
    "parakh.analytics.signals",
    "parakh.lenses",
    "parakh.policy",
    "parakh.mcp.toolsets",
)


_DISCOVERED = False


def discover() -> Registries:
    """Import every module that registers something, so the registries are complete.

    The package walk touches the file system for every module, so it runs once per process;
    callers on hot paths (report formatting) can call this freely.
    """
    global _DISCOVERED
    if _DISCOVERED:
        return REGISTRY
    for pkg_name in DISCOVERY_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for mod in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
            importlib.import_module(mod.name)
    _DISCOVERED = True
    return REGISTRY
