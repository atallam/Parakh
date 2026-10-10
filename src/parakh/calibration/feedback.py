"""Alert feedback and precision per signal (AC-F17.5; plan 03 §4.3).

    summary = alert_precision(alerts_log.rows(), cfg.alerts)

A 👍 or 👎 from Telegram or the Streamlit page lands in the alerts log as a `feedback` row that names
the alert it rates, who rated it (`channel`) and, from the page, an optional reason tag. The latest
rating per alert wins, so changing your mind is allowed. Precision for a signal is the share of rated
alerts judged useful; with fewer than `min_rated` ratings it is shown but flagged as an anecdote, and
the Wilson lower bound is reported beside it so a 3-of-3 does not look like a 100% signal.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from parakh.configs.calibration_models import AlertConfig

ALERT_DECISIONS = {"sent", "shadow", "digest", "digest_sent"}  # an alert you could have seen
SYSTEM_PREFIXES = ("SYS.",)


@dataclass
class SignalPrecision:
    code: str
    alerts: int
    rated: int
    useful: int
    noise: int
    precision_pct: float | None
    lower_bound_pct: float | None  # Wilson 95%
    status: str  # meets target | below target | not enough ratings
    tags: dict[str, int] = field(default_factory=dict)


@dataclass
class PrecisionSummary:
    alerts: int
    rated: int
    useful: int
    noise: int
    coverage_pct: float | None
    precision_pct: float | None
    target_pct: float
    by_channel: dict[str, int]
    signals: list[SignalPrecision]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def wilson_lower(useful: int, n: int, z: float = 1.96) -> float | None:
    if n == 0:
        return None
    p = useful / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / d)


def latest_feedback(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The newest rating per alert_id, from rows in the order they were written."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if (
            r.get("decision") == "feedback"
            and r.get("alert_id")
            and r.get("reason") in ("useful", "noise")
        ):
            out[r["alert_id"]] = r
    return out


def alert_precision(rows: list[dict[str, Any]], cfg: AlertConfig) -> PrecisionSummary:
    alerts: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = str(r.get("code") or "")
        if (
            r.get("decision") in ALERT_DECISIONS
            and r.get("alert_id")
            and not code.startswith(SYSTEM_PREFIXES)
        ):
            alerts.setdefault(r["alert_id"], r)
    fb = latest_feedback(rows)
    per: dict[str, dict[str, Any]] = {}
    channels: Counter[str] = Counter()
    for alert_id, a in alerts.items():
        slot = per.setdefault(a["code"], {"alerts": 0, "useful": 0, "noise": 0, "tags": Counter()})
        slot["alerts"] += 1
        rating = fb.get(alert_id)
        if rating is None:
            continue
        slot["useful" if rating["reason"] == "useful" else "noise"] += 1
        channels[str(rating.get("channel") or "telegram")] += 1
        if rating["reason"] == "noise" and rating.get("tag"):
            slot["tags"][rating["tag"]] += 1
    signals = []
    for code, s in sorted(per.items()):
        rated = s["useful"] + s["noise"]
        prec = 100 * s["useful"] / rated if rated else None
        lo = wilson_lower(s["useful"], rated)
        if rated < cfg.min_rated:
            status = "not enough ratings"
        else:
            status = (
                "meets target"
                if prec is not None and prec >= cfg.target_precision_pct
                else "below target"
            )
        signals.append(
            SignalPrecision(
                code, s["alerts"], rated, s["useful"], s["noise"], prec,
                None if lo is None else 100 * lo, status, dict(s["tags"]),
            )
        )  # fmt: skip
    total = sum(s.alerts for s in signals)
    rated = sum(s.rated for s in signals)
    useful = sum(s.useful for s in signals)
    return PrecisionSummary(
        alerts=total,
        rated=rated,
        useful=useful,
        noise=rated - useful,
        coverage_pct=100 * rated / total if total else None,
        precision_pct=100 * useful / rated if rated else None,
        target_pct=cfg.target_precision_pct,
        by_channel=dict(channels),
        signals=signals,
    )
