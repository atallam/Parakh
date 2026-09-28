"""Prompts live in YAML files beside this module (C1.1) and render with Jinja2 (C2.1).

Layout: prompts/<name>/v<N>.yaml. A prompt change is a new version file, reviewed like code (C1.2).
registry.yaml says which version is live; roll back by pointing `active` at an older one (C2.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined

PROMPTS_DIR = Path(__file__).parent
_jinja = Environment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def versions(name: str) -> list[str]:
    """All versions of a prompt, oldest first (v2 before v10)."""
    found = [p.stem for p in (PROMPTS_DIR / name).glob("v*.yaml")]
    return sorted(found, key=lambda v: int(v[1:]) if v[1:].isdigit() else -1)


def active_version(name: str) -> str:
    registry = yaml.safe_load((PROMPTS_DIR / "registry.yaml").read_text(encoding="utf-8"))
    return registry["prompts"][name]["active"]


def load_prompt(name: str, version: str | None = None) -> dict[str, Any]:
    version = version or active_version(name)
    path = PROMPTS_DIR / name / f"{version}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def render_prompt(name: str, version: str | None = None, **variables: Any) -> tuple[str, str]:
    """Return (system, user) text. Missing variables raise instead of rendering blanks."""
    spec = load_prompt(name, version)
    system = _jinja.from_string(spec.get("system", "")).render(**variables)
    user = _jinja.from_string(spec["user"]).render(**variables)
    return system, user
