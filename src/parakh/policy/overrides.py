"""Overrides with a reason and an expiry (plan 10 §8; AC-F21.12).

Overrides live in config/overrides.yaml (changed by pull request or `parakh override add`).
A run applies the active ones, lists them in the monthly summary until they expire, and emits
`AUD.OVERRIDE.EXPIRED` once, in the first run after the expiry date.
"""

from __future__ import annotations

import datetime as dt

from parakh.configs.lens_models import Override, OverridesConfig


def active_for(cfg: OverridesConfig, isin: str, asof: dt.date, field: str) -> Override | None:
    """The newest active override of this field for the stock (a later `set_on` wins)."""
    found = cfg.active(isin, asof, field)
    return max(found, key=lambda o: o.set_on) if found else None


def expired_since(cfg: OverridesConfig, prev_asof: dt.date | None, asof: dt.date) -> list[Override]:
    """Overrides whose expiry fell after the previous run's date and before this one's."""
    lower = prev_asof or dt.date.min
    return [o for o in cfg.overrides if lower <= o.expires_on < asof]


def nearing_expiry(cfg: OverridesConfig, asof: dt.date, days: int = 30) -> list[Override]:
    return [
        o
        for o in cfg.overrides
        if o.set_on <= asof <= o.expires_on and (o.expires_on - asof).days <= days
    ]
