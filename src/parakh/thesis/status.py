# pyright: reportArgumentType=false, reportOperatorIssue=false, reportAttributeAccessIssue=false
# why: pandas stubs type a datetime index element as a union; it is a Timestamp at run time (tested)
"""Thesis status: INTACT / WATCH / BROKEN / NOT SET (F23; plan 05 §2.4 status rules, D13).

Inputs that can set a status in Phase 2:

| Input                                         | Sets                                      |
|-----------------------------------------------|-------------------------------------------|
| a `check: metric` breaker that is met          | BROKEN (deterministic, with its evidence) |
| your override (reason + expiry, plan 10 §8)    | any status                                |
| everything else                                | INTACT, with unchecked items shown as ❔  |

An `llm_flag` breaker and a key metric need the concall agent (Phase 4); until then they show as
❔ "not machine-checked", so an INTACT status never claims more than was actually checked (UX-05).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from parakh.analytics.fundamentals_view import Fundamentals
from parakh.configs.lens_models import Override
from parakh.thesis import rules
from parakh.thesis.model import ParsedThesis

STATUSES = ("INTACT", "WATCH", "BROKEN", "NOT_SET")
BUILTIN_UNITS = {
    "price": "inr",
    "value_score": "score",
    "momentum_score": "score",
    "revenue_growth_yoy_pct": "pct",
    "net_profit_growth_yoy_pct": "pct",
    "operating_margin_pct": "pct",
}
TIMELINE_KEEP = 24


def variable_names(metric_ids: Iterable[str]) -> dict[str, str]:
    """Variable name → MET id. A name shared by two lenses stays plain for value, `momentum_` for momentum."""
    out: dict[str, str] = {}
    for mid in sorted(metric_ids):
        parts = mid.split(".")
        name = parts[-1]
        if name in out or name in BUILTIN_UNITS:
            name = f"{parts[1]}_{name}"
        out[name] = mid
    return out


@dataclass
class ThesisContext:
    metrics: dict[str, float | None]  # MET.* → value
    fund: Fundamentals
    price: float | None = None
    value_score: float | None = None
    momentum_score: float | None = None
    names: dict[str, str] = field(default_factory=dict)


def _yoy_pct(series: pd.Series) -> float | None:
    if len(series) < 5:
        return None
    last, then = series.index[-1], series.index[-5]
    if not 340 <= (pd.Timestamp(last) - pd.Timestamp(then)).days <= 390 or series.iloc[-5] <= 0:
        return None
    return float((series.iloc[-1] / series.iloc[-5] - 1) * 100)


def lookup_for(ctx: ThesisContext) -> Callable[[str], float | None]:
    sales = ctx.fund.quarterly("quarterly_pl", "Sales")
    profit = ctx.fund.quarterly("quarterly_pl", "Net profit")
    opm = ctx.fund.quarterly("quarterly_pl", "Operating Profit")
    margin = None
    if len(sales) and len(opm) and sales.index[-1] == opm.index[-1] and sales.iloc[-1] > 0:
        margin = float(opm.iloc[-1] / sales.iloc[-1] * 100)
    builtin = {
        "price": ctx.price,
        "value_score": ctx.value_score,
        "momentum_score": ctx.momentum_score,
        "revenue_growth_yoy_pct": _yoy_pct(sales),
        "net_profit_growth_yoy_pct": _yoy_pct(profit),
        "operating_margin_pct": margin,
    }

    def lookup(name: str) -> float | None:
        if name in builtin:
            return builtin[name]
        mid = ctx.names.get(name)
        return None if mid is None else ctx.metrics.get(mid)

    return lookup


def validate_rules(parsed: ThesisParsedLike, names: dict[str, str]) -> list[str]:
    """Rule syntax and variable names, checked when THESIS.md is validated (not only at run time)."""
    problems = []
    known = set(names) | set(BUILTIN_UNITS)
    if parsed.front is None:
        return problems
    for b in parsed.front.breakers:
        if b.check != "metric" or not b.rule:
            continue
        try:
            unknown = rules.check_variables(b.rule, known)
        except rules.RuleError as exc:
            problems.append(f"{b.id}: {exc}")
            continue
        if unknown:
            problems.append(
                f"{b.id}: unknown variable(s) {', '.join(unknown)} (see `parakh thesis variables`)"
            )
    return problems


ThesisParsedLike = ParsedThesis


def evaluate_thesis(
    parsed: ParsedThesis,
    ctx: ThesisContext,
    asof: dt.date,
    prev: dict[str, Any] | None,
    period: str,
    override: Override | None = None,
) -> dict[str, Any]:
    """The thesis block of a snapshot. `prev` is last month's block (for the status timeline)."""
    timeline = list((prev or {}).get("timeline", []))
    prev_status = (prev or {}).get("status")
    block: dict[str, Any] = {
        "status": "NOT_SET",
        "status_source": "none",
        "present": parsed.exists,
        "valid": False,
        "errors": list(parsed.errors),
        "thesis_version": None,
        "original": None,
        "review_by": None,
        "review_due": False,
        "key_metrics": [],
        "breakers": [],
        "unchecked": 0,
        "checked": 0,
        "banner": None,
        "changed_from": None,
        "timeline": timeline,
        "sizing_rationale": None,
    }
    front = parsed.front
    if front is not None:
        extra = validate_rules(parsed, ctx.names)
        block["errors"].extend(extra)
        block["valid"] = not extra
    if front is None or not block["valid"]:
        block["banner"] = (
            "no thesis written yet"
            if not parsed.exists
            else "THESIS.md could not be read: " + "; ".join(block["errors"][:3])
        )
        return _finish(block, prev_status, period, override)

    block |= {
        "status": "INTACT",
        "status_source": "no metric breaker met",
        "thesis_version": front.thesis_version,
        "original": {
            "written_on": front.original.written_on.isoformat(),
            "statement": front.original.statement,
        },
        "review_by": front.review_by.isoformat() if front.review_by else None,
        "review_due": bool(front.review_by and asof > front.review_by),
        "sizing_rationale": front.sizing_rationale,
    }
    lookup = lookup_for(ctx)
    broken: list[str] = []
    for b in front.breakers:
        row: dict[str, Any] = {"id": b.id, "text": b.text, "check": b.check, "rule": b.rule}
        if b.check == "metric":
            assert b.rule is not None
            res = rules.evaluate(b.rule, lookup)
            row["evidence"] = res.used
            if res.value is True:
                row["state"] = "FLAGGED"
                broken.append(b.id)
                block["checked"] += 1
            elif res.value is False:
                row["state"] = "CLEAN"
                block["checked"] += 1
            else:
                row["state"] = "UNKNOWN"
                row["reason"] = "no value for " + ", ".join(res.missing)
                block["unchecked"] += 1
        else:
            row["state"] = "UNKNOWN"
            row["reason"] = "needs the concall agent (Phase 4): not machine-checked yet"
            block["unchecked"] += 1
        block["breakers"].append(row)
    for km in front.key_metrics:
        block["key_metrics"].append(
            {
                "id": km.id,
                "text": km.text,
                "state": "UNKNOWN",
                "reason": "tracked by the concall agent (Phase 4)",
            }
        )
        block["unchecked"] += 1
    if broken:
        block["status"] = "BROKEN"
        block["status_source"] = "metric breaker: " + ", ".join(broken)
    return _finish(block, prev_status, period, override)


def _finish(
    block: dict[str, Any], prev_status: str | None, period: str, override: Override | None
) -> dict[str, Any]:
    if override is not None and override.field == "thesis_status":
        block["status"] = override.value
        block["status_source"] = (
            f"owner override {override.id} until {override.expires_on}: {override.reason}"
        )
    if prev_status is not None and prev_status != block["status"]:
        block["changed_from"] = prev_status
    timeline = [t for t in block["timeline"] if t.get("period") != period]  # idempotent per month
    if not timeline or timeline[-1]["status"] != block["status"]:
        timeline.append(
            {
                "period": period,
                "status": block["status"],
                "from": prev_status,
                "source": block["status_source"],
            }
        )
    block["timeline"] = timeline[-TIMELINE_KEEP:]
    return block
