"""Promote or roll back a prompt version by moving the pin in registry.yaml (plan 13 P3).

    rollback("qualitative", reason="quotes failed 30% of checks")      # to the previous history entry
    rollback("qualitative", to="v1", reason="...")

The pin is the only thing that changes; version files are never edited. Every move writes one
`AUD.PROMPT.PROMOTED` or `AUD.PROMPT.ROLLED_BACK` event. Agent caches key on the pin, so a rollback
reuses the old version's cached outputs at no token cost.
"""

from __future__ import annotations

import datetime as dt
import re

import yaml

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.prompts import PROMPTS_DIR, versions

REGISTRY = PROMPTS_DIR / "registry.yaml"


class PinError(ValueError):
    pass


def _entry(name: str) -> dict:  # type: ignore[type-arg]
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["prompts"]
    if name not in reg:
        raise PinError(f"unknown prompt {name!r}; have {', '.join(sorted(reg))}")
    return reg[name]  # type: ignore[no-any-return]


def _set_active(name: str, version: str) -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    pattern = re.compile(rf"(^  {re.escape(name)}:\n    active: )v\d+", re.M)
    if not pattern.search(text):
        raise PinError(f"could not find the pin for {name} in registry.yaml")
    REGISTRY.write_text(pattern.sub(rf"\g<1>{version}", text, count=1), encoding="utf-8")


def _move(name: str, version: str, event: AUD, reason: str, sink: AuditSink | None) -> str:
    if not reason.strip():
        raise PinError("a pin change needs a reason")
    entry = _entry(name)
    current = entry["active"]
    if version not in versions(name):
        raise PinError(f"{name} has no version {version}; have {', '.join(versions(name))}")
    if version == current:
        raise PinError(f"{name} is already pinned to {version}")
    _set_active(name, version)
    (sink or get_sink()).emit(
        RunContext.create(mode="prompt-pin", actor_type="user", actor_id="owner"), event,
        entity_type="prompt", entity_id=name, reason=reason,
        before={"active": current}, after={"active": version},
        details={"date": dt.date.today().isoformat()},
    )  # fmt: skip
    return version


def rollback(
    name: str, *, reason: str, to: str | None = None, sink: AuditSink | None = None
) -> str:
    entry = _entry(name)
    if to is None:
        older = [h["version"] for h in entry.get("history", []) if h["version"] != entry["active"]]
        earlier = [
            v
            for v in older
            if v in versions(name)
            and versions(name).index(v) < versions(name).index(entry["active"])
        ]
        if not earlier:
            raise PinError(f"{name} has no earlier version to roll back to")
        to = earlier[-1]
    assert to is not None
    return _move(name, to, AUD.PROMPT_ROLLED_BACK, reason, sink)


def promote(name: str, version: str, *, reason: str, sink: AuditSink | None = None) -> str:
    return _move(name, version, AUD.PROMPT_PROMOTED, reason, sink)
