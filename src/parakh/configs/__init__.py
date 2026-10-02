"""Load and validate config/*.yaml. `load_all()` fails with every error at once, per file."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from parakh.config import config_dir
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
    sources: list[str] = field(default_factory=list)


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
        sources=list(FILES),
    )
