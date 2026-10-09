"""What the watchlist engine knows about a stock this month, built from snapshots (plan 06 §3).

The engine never reads a snapshot itself: `facts_for_cap` turns the month's snapshots of one cap into
`Facts`, ranked by the combined value + momentum score, so the rules stay pure and testable.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from parakh.configs.watchlist_models import SmartMoney, WatchlistConfig


@dataclass(frozen=True)
class Facts:
    isin: str
    symbol: str
    cap: str
    combined: float  # mean of the value and momentum scores that exist, 0–100
    rank_pct: float  # position from the top of its cap in percent: 1.0 best, 100.0 worst
    value_score: float | None = None
    momentum_score: float | None = None
    quality_subscore: float | None = None
    value_view: str | None = None
    value_flags: tuple[str, ...] = ()
    vetoes: tuple[str, ...] = ()
    signals: frozenset[str] = frozenset()
    regime: str = "Neutral"
    liquidity_ok: bool = True
    owned: bool = False
    close: float | None = None
    thesis_status: str = "NOT_SET"
    smart_money_hits: int = 0
    corporate_status: str | None = None  # delisted | merged | suspended
    extra: dict[str, Any] = field(default_factory=dict)


def combined_score(snap: dict[str, Any]) -> float:
    vals = [x for x in (snap["value"].get("score"), snap["momentum"].get("score")) if x is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def smart_money_hits(rows: list[dict[str, Any]], isin: str, cfg: SmartMoney, today: dt.date) -> int:
    """Event-history rows that count as conviction buying: right code, a buy, not an ESOP or gift."""
    buy = [re.compile(p) for p in cfg.buy_text]
    skip = [re.compile(p) for p in cfg.exclude_text]
    since = today - dt.timedelta(days=cfg.lookback_days)
    n = 0
    for r in rows:
        if r.get("isin") != isin or r.get("code") not in cfg.event_codes:
            continue
        try:
            day = dt.date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        text = str(r.get("headline", ""))
        if (
            day >= since
            and any(p.search(text) for p in buy)
            and not any(p.search(text) for p in skip)
        ):
            n += 1
    return n


def facts_for_cap(
    snaps: list[dict[str, Any]],
    cfg: WatchlistConfig,
    *,
    event_rows: list[dict[str, Any]] | None = None,
    today: dt.date | None = None,
    corporate: dict[str, str] | None = None,
) -> list[Facts]:
    """Rank one cap's snapshots and return their facts, best first."""
    today = today or dt.date.today()
    ordered = sorted(snaps, key=lambda s: (-combined_score(s), s["symbol"]))
    n = len(ordered)
    out: list[Facts] = []
    for i, s in enumerate(ordered, start=1):
        v, m, verdict = s["value"], s["momentum"], s["verdict"]
        signals = frozenset(m.get("signals") or [])
        details = m.get("details") or {}
        vflags = tuple(str(x).lower() for x in (v.get("flags") or []))
        liquid = not any("illiquid" in f for f in vflags)
        hits = smart_money_hits(event_rows or [], s["isin"], cfg.sources.smart_money, today)
        out.append(
            Facts(
                isin=s["isin"],
                symbol=s["symbol"],
                cap=s["cap"],
                combined=combined_score(s),
                rank_pct=round(i / n * 100, 2),
                value_score=v.get("score"),
                momentum_score=m.get("score"),
                quality_subscore=(v.get("subscores") or {}).get("quality"),
                value_view=v.get("view"),
                value_flags=vflags,
                vetoes=tuple(sorted(set(v.get("vetoes") or []) | set(m.get("vetoes") or []))),
                signals=signals,
                regime=(s.get("regime") or {}).get("regime", "Neutral"),
                liquidity_ok=liquid,
                owned=bool(verdict.get("owned")),
                close=(s.get("price") or {}).get("close"),
                thesis_status=(s.get("thesis") or {}).get("status", "NOT_SET"),
                smart_money_hits=hits,
                corporate_status=(corporate or {}).get(s["isin"]),
                extra={"stage": details.get("stage")},
            )
        )
    return out
