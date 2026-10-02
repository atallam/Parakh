"""Load and validate config/*.yaml. `load_all()` fails with every error at once, per file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from parakh.config import config_dir
from parakh.configs.lens_models import (
    IndicesConfig,
    MomentumConfig,
    OverridesConfig,
    PortfolioConfig,
    RegimeConfig,
    ValueConfig,
    VerdictPolicy,
)
from parakh.configs.models import (
    AgentsConfig,
    BackupConfig,
    DataQualityConfig,
    FlagsConfig,
    LensesConfig,
    ProfileInputsConfig,
    SourcesConfig,
    UiTokens,
    UniverseConfig,
)

FILES: dict[str, type[BaseModel]] = {
    "universe.yaml": UniverseConfig,
    "lenses.yaml": LensesConfig,
    "flags.yaml": FlagsConfig,
    "agents.yaml": AgentsConfig,
    "ui_tokens.yaml": UiTokens,
    "sources.yaml": SourcesConfig,
    "data_quality.yaml": DataQualityConfig,
    "backup.yaml": BackupConfig,
    "profile_inputs.yaml": ProfileInputsConfig,
    "value.yaml": ValueConfig,
    "momentum.yaml": MomentumConfig,
    "regime.yaml": RegimeConfig,
    "verdict_policy.yaml": VerdictPolicy,
    "overrides.yaml": OverridesConfig,
    "portfolio.yaml": PortfolioConfig,
    "indices.yaml": IndicesConfig,
}


class ConfigError(Exception):
    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("invalid config:\n" + "\n".join(f"  - {p}" for p in problems))


def load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_file[M: BaseModel](name: str, model: type[M], root: Path | None = None) -> M:
    path = (root or config_dir()) / name
    try:
        return model.model_validate(load_yaml(path))
    except FileNotFoundError as exc:
        raise ConfigError([f"{name}: file not found at {path}"]) from exc
    except ValidationError as exc:
        raise ConfigError(
            [
                f"{name}: {'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}"
                for e in exc.errors()
            ]
        ) from exc


@dataclass(frozen=True)
class ConfigBundle:
    universe: UniverseConfig
    lenses: LensesConfig
    flags: FlagsConfig
    agents: AgentsConfig
    ui_tokens: UiTokens
    data_sources: SourcesConfig
    data_quality: DataQualityConfig
    backup: BackupConfig
    profile_inputs: ProfileInputsConfig
    value: ValueConfig
    momentum: MomentumConfig
    regime: RegimeConfig
    verdict_policy: VerdictPolicy
    overrides: OverridesConfig
    portfolio: PortfolioConfig
    indices: IndicesConfig
    sources: list[str] = field(default_factory=list)


def _cross_checks(loaded: dict[str, BaseModel], universe: UniverseConfig) -> list[str]:
    """Files that name things in other files must agree (a typo here would silently skip a stock)."""
    out: list[str] = []
    isins = {s.isin for s in universe.pilot}
    value, momentum = loaded["value.yaml"], loaded["momentum.yaml"]
    ovr, idx = loaded["overrides.yaml"], loaded["indices.yaml"]
    assert isinstance(value, ValueConfig) and isinstance(momentum, MomentumConfig)
    assert isinstance(ovr, OverridesConfig)
    assert isinstance(idx, IndicesConfig)
    verdicts = set(loaded["verdict_policy.yaml"].verdict_order)  # type: ignore[attr-defined]
    for sec in universe.pilot:
        if sec.profile not in value.profiles:
            out.append(
                f"universe.yaml: {sec.symbol} profile {sec.profile!r} has no entry in value.yaml"
            )
    for o in ovr.overrides:
        if o.isin not in isins:
            out.append(f"overrides.yaml: {o.id} names an ISIN outside the pilot: {o.isin}")
        if o.field == "profile" and o.value not in value.profiles:
            out.append(f"overrides.yaml: {o.id} profile {o.value!r} has no entry in value.yaml")
        if o.field == "verdict" and o.value.upper().replace(" ", "_") not in verdicts:
            out.append(
                f"overrides.yaml: {o.id} verdict {o.value!r} is not one of {sorted(verdicts)}"
            )
        if o.field == "thesis_status" and o.value not in ("INTACT", "WATCH", "BROKEN"):
            out.append(
                f"overrides.yaml: {o.id} thesis_status {o.value!r} must be INTACT, WATCH or BROKEN"
            )
    known = {i.name for i in idx.indices}
    for cap, spec in momentum.cap_settings.items():
        for bench in (spec.benchmark, spec.secondary_benchmark):
            if bench not in known:
                out.append(f"indices.yaml: no entry for {bench} (momentum.yaml {cap} benchmark)")
    return out


def load_all(root: Path | None = None) -> ConfigBundle:
    loaded: dict[str, BaseModel] = {}
    problems: list[str] = []
    for name, model in FILES.items():
        try:
            loaded[name] = load_file(name, model, root)
        except ConfigError as exc:
            problems.extend(exc.problems)
    if problems:
        raise ConfigError(problems)
    universe = loaded["universe.yaml"]
    assert isinstance(universe, UniverseConfig)
    if not universe.golden:
        problems.append("universe.yaml: no golden stocks marked (plan 13 D18)")
    registry = loaded["sources.yaml"]
    assert isinstance(registry, SourcesConfig)
    for sec in universe.pilot:
        for prev in sec.previous_isins:
            if prev.source not in registry.ids():
                problems.append(
                    f"universe.yaml: {sec.symbol} previous ISIN {prev.isin} cites unknown source {prev.source}"
                )
    profile = loaded["profile_inputs.yaml"]
    assert isinstance(profile, ProfileInputsConfig)
    known = {sec.isin for sec in universe.pilot}
    for isin in [*profile.filing_items, *profile.listed_stakes]:
        if isin not in known:
            problems.append(f"profile_inputs.yaml: {isin} is not in the universe")
    problems.extend(_cross_checks(loaded, universe))
    if problems:
        raise ConfigError(problems)
    return ConfigBundle(
        universe=universe,
        lenses=loaded["lenses.yaml"],  # type: ignore[arg-type]
        flags=loaded["flags.yaml"],  # type: ignore[arg-type]
        agents=loaded["agents.yaml"],  # type: ignore[arg-type]
        ui_tokens=loaded["ui_tokens.yaml"],  # type: ignore[arg-type]
        data_sources=registry,
        data_quality=loaded["data_quality.yaml"],  # type: ignore[arg-type]
        backup=loaded["backup.yaml"],  # type: ignore[arg-type]
        profile_inputs=profile,
        value=loaded["value.yaml"],  # type: ignore[arg-type]
        momentum=loaded["momentum.yaml"],  # type: ignore[arg-type]
        regime=loaded["regime.yaml"],  # type: ignore[arg-type]
        verdict_policy=loaded["verdict_policy.yaml"],  # type: ignore[arg-type]
        overrides=loaded["overrides.yaml"],  # type: ignore[arg-type]
        portfolio=loaded["portfolio.yaml"],  # type: ignore[arg-type]
        indices=loaded["indices.yaml"],  # type: ignore[arg-type]
        sources=list(FILES),
    )
