"""What gets told to the owner: the Alert, its routing Decision and the Severity words.

An `Alert` is one thing worth a line in a message: a signal change, a filing, a thesis status
change or a system fault. It carries everything routing needs (ownership, direction, severity)
and nothing private: weight and P&L are percentages, never amounts (plan 12 §8).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from parakh.configs.notify_models import Direction, Valence

Kind = Literal["signal", "event", "thesis", "system", "review"]


class Severity(StrEnum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

    @property
    def rank(self) -> int:
        return {"High": 2, "Medium": 1, "Low": 0}[self.value]

    def capped(self, ceiling: Severity) -> Severity:
        return self if self.rank <= ceiling.rank else ceiling


@dataclass(frozen=True)
class Alert:
    kind: Kind
    code: str  # M21, E04, THESIS.BROKEN, SYS.FAILURE
    severity: Severity
    headline: str  # one evidence line, already free of amounts
    asof: dt.date
    isin: str | None = None
    symbol: str | None = None
    direction: Direction = "info"
    valence: Valence = "neutral"
    owned: bool = False
    weight_pct: float | None = None
    pnl_pct: float | None = None
    top_decile: bool = False
    group: str = ""  # distinguishes repeats of the same code (a filing id, a period)
    source: str = "watcher"  # watcher | events | monthly | agent:<name>
    link: str | None = None
    note: str | None = None  # agent-written "why it matters" (🤖), validated before it gets here
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        return ":".join(p for p in (self.kind, self.isin or "-", self.code, self.group) if p)

    @property
    def cooldown_key(self) -> str:
        """Signals share a cool-down across days; the group never splits one."""
        return ":".join((self.kind, self.isin or "-", self.code))

    def payload_hash(self) -> str:
        body = "|".join(
            str(x)
            for x in (self.dedupe_key, self.severity.value, self.headline, self.asof, self.note)
        )
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Decision:
    action: Literal["send_now", "digest", "suppress"]
    reason: str
    silent: bool = False
    ntfy: bool = False  # also the loud lane (High on an owned stock, when enabled)


def alert_to_dict(alert: Alert) -> dict[str, Any]:
    """JSON-safe form, used by the digest queue and the alerts log."""
    return {
        "kind": alert.kind,
        "code": alert.code,
        "severity": alert.severity.value,
        "headline": alert.headline,
        "asof": alert.asof.isoformat(),
        "isin": alert.isin,
        "symbol": alert.symbol,
        "direction": alert.direction,
        "valence": alert.valence,
        "owned": alert.owned,
        "weight_pct": alert.weight_pct,
        "pnl_pct": alert.pnl_pct,
        "top_decile": alert.top_decile,
        "group": alert.group,
        "source": alert.source,
        "link": alert.link,
        "note": alert.note,
        "extra": alert.extra,
    }


def alert_from_dict(row: dict[str, Any]) -> Alert:
    return Alert(
        kind=row["kind"],
        code=row["code"],
        severity=Severity(row["severity"]),
        headline=row["headline"],
        asof=dt.date.fromisoformat(row["asof"]),
        isin=row.get("isin"),
        symbol=row.get("symbol"),
        direction=row.get("direction", "info"),
        valence=row.get("valence", "neutral"),
        owned=bool(row.get("owned", False)),
        weight_pct=row.get("weight_pct"),
        pnl_pct=row.get("pnl_pct"),
        top_decile=bool(row.get("top_decile", False)),
        group=row.get("group", ""),
        source=row.get("source", "watcher"),
        link=row.get("link"),
        note=row.get("note"),
        extra=row.get("extra") or {},
    )
