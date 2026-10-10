"""The quarterly calibration report: one page that says whether the framework's weights still stand.

    report = build_report(quarter="2026-Q4", cfg=cal, framework_version="1.0.0", parts=Parts(...))
    report.recommendations      # CONFIRM | REVIEW | INSUFFICIENT per lens, with the reason
    report.to_markdown()        # written to docs/calibration/<quarter>.md and the governance review

It only assembles and judges what the other modules computed; it computes no returns itself. The
recommendation is advice to a person: CONFIRM means the evidence supports the current weights, REVIEW
means a lens's high scores earned less than its low scores (change the weights through a PR, a framework
version bump and a history re-score), INSUFFICIENT means there is not yet enough data to say. Nothing
here edits a score, weight or verdict (AG-03). An honest "insufficient" is a result, not a gap.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from parakh.configs.calibration_models import CalibrationConfig

CONFIRM, REVIEW, INSUFFICIENT = "CONFIRM", "REVIEW", "INSUFFICIENT"


@dataclass
class Parts:
    backtest: dict[str, Any] | None = None
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    quintiles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # lens → per horizon
    alerts: dict[str, Any] | None = None
    scorecard: dict[str, Any] | None = None
    journal: dict[str, Any] | None = None
    drift: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None
    restore: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Recommendation:
    lens: str
    decision: str
    reason: str


@dataclass
class CalibrationReport:
    quarter: str
    generated_on: str
    framework_version: str
    calibration_version: str
    parts: Parts
    recommendations: list[Recommendation]

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=1, default=str, ensure_ascii=False) + "\n"

    @property
    def overall(self) -> str:
        decisions = {r.decision for r in self.recommendations}
        return REVIEW if REVIEW in decisions else CONFIRM if CONFIRM in decisions else INSUFFICIENT

    def to_markdown(self) -> str:
        return _markdown(self)


def recommend(lens: str, rows: list[dict[str, Any]], primary: int) -> Recommendation:
    """Judge a lens on its primary horizon; the other horizons are context, not a vote."""
    row = next((r for r in rows if r.get("horizon_months") == primary), None)
    if row is None:
        return Recommendation(lens, INSUFFICIENT, "no calibration at the primary horizon yet")
    verdict = row.get("verdict")
    if verdict == "confirmed":
        return Recommendation(lens, CONFIRM, row.get("reason", ""))
    if verdict == "reversed":
        return Recommendation(
            lens,
            REVIEW,
            f"{row.get('reason', '')}; top-minus-bottom spread {row.get('spread_pct'):.1f}%",
        )
    return Recommendation(lens, INSUFFICIENT, row.get("reason", "") or "inconclusive")


def build_report(
    *,
    quarter: str,
    cfg: CalibrationConfig,
    framework_version: str,
    parts: Parts,
    today: dt.date | None = None,
) -> CalibrationReport:
    recs = [
        recommend(lens, rows, cfg.quintiles.primary_horizon_months)
        for lens, rows in sorted(parts.quintiles.items())
    ]
    if not recs:
        recs = [Recommendation("all", INSUFFICIENT, "no scored history has been calibrated yet")]
    return CalibrationReport(
        quarter=quarter,
        generated_on=(today or dt.date.today()).isoformat(),
        framework_version=framework_version,
        calibration_version=cfg.version,
        parts=parts,
        recommendations=recs,
    )


def quarter_of(day: dt.date) -> str:
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


# -- rendering ------------------------------------------------------------------------------------
def _f(x: Any, nd: int = 1, suffix: str = "") -> str:
    return "n/a" if x is None else f"{x:.{nd}f}{suffix}"


def _total(p: dict[str, Any]) -> float | None:
    start, end = p.get("start_inr"), p.get("end_inr")
    return 100 * (end / start - 1) if start and end else None


def _perf_row(label: str, p: dict[str, Any] | None) -> str:
    if not p:
        return f"| {label} | n/a | n/a | n/a | n/a |"
    return (
        f"| {label} | {_f(p.get('cagr_pct'), 1, '%')} | {_f(p.get('sharpe'), 2)} | "
        f"{_f(p.get('max_drawdown_pct'), 1, '%')} | {_f(_total(p), 0, '%')} |"
    )


def _markdown(r: CalibrationReport) -> str:
    p = r.parts
    out = [
        f"# Calibration report {r.quarter}",
        "",
        f"Framework {r.framework_version} · calibration config {r.calibration_version} · generated {r.generated_on}",
        "",
        "## Recommendation",
        "",
        f"**{r.overall}.** Nothing below changes a weight by itself; a change goes through a PR, a framework "
        "version bump and a re-score of history.",
        "",
        "| Lens | Decision | Why |",
        "|---|---|---|",
        *[f"| {x.lens} | {x.decision} | {x.reason} |" for x in r.recommendations],
        "",
    ]
    bt = p.backtest
    out += ["## Price-only momentum backtest", ""]
    if not bt:
        out += ["Not run this quarter.", ""]
    elif bt.get("status") != "ok":
        out += [f"Status: **{bt.get('status')}**. " + " ".join(bt.get("reasons", [])), ""]
    else:
        out += [
            "| Series | CAGR | Sharpe | Max drawdown | Total return |",
            "|---|---|---|---|---|",
            _perf_row("Gross", bt.get("gross")),
            _perf_row("After costs", bt.get("after_cost")),
            _perf_row("After costs and tax", bt.get("after_tax")),
            _perf_row("Benchmark", bt.get("benchmark")),
            "",
        ]
    for w in (bt or {}).get("warnings", []):
        out.append(f"- Warning: {w}")
    out.append("")
    out += ["## Score quintiles", ""]
    if not p.quintiles:
        out += ["No lens has scored history to calibrate yet.", ""]
    for lens, rows in sorted(p.quintiles.items()):
        out += [
            f"### {lens}",
            "",
            "| Horizon | Months used | Spread | IC | IC t | Verdict |",
            "|---|---|---|---|---|---|",
        ]
        for c in rows:
            out.append(
                f"| {c.get('horizon_months')}M | {c.get('periods_used')} | {_f(c.get('spread_pct'), 1, '%')} | "
                f"{_f(c.get('ic_mean'), 3)} | {_f(c.get('ic_t'), 1)} | {c.get('verdict')} |"
            )
        out.append("")
    out += ["## Signal outcomes", ""]
    if not p.outcomes:
        out += ["No signal has fired and matured yet.", ""]
    else:
        out += [
            "| Signal | Source | Fired | 1M matured | 1M hit rate | 3M matured | 3M hit rate | Evidence |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for o in p.outcomes:
            h1, h3 = o["horizons"].get("1M", {}), o["horizons"].get("3M", {})
            out.append(
                f"| {o['code']} | {o['source']} | {o['observations']} | {h1.get('matured')} | "
                f"{_f(h1.get('hit_rate_pct'), 0, '%')} | {h3.get('matured')} | "
                f"{_f(h3.get('hit_rate_pct'), 0, '%')} | {h3.get('evidence') or h1.get('evidence')} |"
            )
        out.append("")
    out += ["## Alert precision", ""]
    a = p.alerts
    if not a or not a.get("alerts"):
        out += ["No alerts yet.", ""]
    else:
        out += [
            f"{a['rated']} of {a['alerts']} alerts rated ({_f(a.get('coverage_pct'), 0, '%')}); "
            f"precision {_f(a.get('precision_pct'), 0, '%')} against a target of {a['target_pct']:.0f}%.",
            "",
            "| Signal | Alerts | Rated | Useful | Precision | Lower bound | Status |",
            "|---|---|---|---|---|---|---|",
            *[
                f"| {s['code']} | {s['alerts']} | {s['rated']} | {s['useful']} | "
                f"{_f(s.get('precision_pct'), 0, '%')} | {_f(s.get('lower_bound_pct'), 0, '%')} | {s['status']} |"
                for s in a["signals"]
            ],
            "",
        ]
    out += ["## Watchlist scorecard", ""]
    sc = p.scorecard
    if not sc or not sc.get("by_source"):
        out += ["No watchlist history yet.", ""]
    else:
        out += [
            "| Source | Entries | 3M mean | 3M excess | 3M hit rate | Note |",
            "|---|---|---|---|---|---|",
        ]
        for g in sc["by_source"]:
            c = g["cells"].get("3M", {})
            out.append(
                f"| {g['name']} | {g['entries']} | {_f(c.get('mean_pct'), 1, '%')} | "
                f"{_f(c.get('mean_excess_pct'), 1, '%')} | {_f(c.get('hit_rate_pct'), 0, '%')} | {g.get('note', '')} |"
            )
        out.append("")
    out += ["## Decision journal", ""]
    j = p.journal
    if not j or not j.get("entries"):
        out += ["No entries yet.", ""]
    else:
        out += [
            f"{j['entries']} entries, {j['reviewed']} reviewed, {j['open']} open. "
            f"Judged right: {_f(j.get('right_pct'), 0, '%')}. Verdicts: {j['by_verdict']}",
            "",
        ]
    out += ["## Governance checks", ""]
    for title, part in (
        ("Drift", p.drift),
        ("Replay determinism", p.replay),
        ("Backup restore", p.restore),
    ):
        out.append(f"- {title}: " + (f"**{part.get('status')}**" if part else "not run"))
    out.append("")
    if p.notes:
        out += ["## Notes", "", *[f"- {n}" for n in p.notes], ""]
    return "\n".join(out)


REVIEW_TEMPLATE = """# Governance review {quarter}

Reviewer: Avinash Tallam · Date: {date} · Framework {version}

Attach or link the calibration report ({quarter}). Tick each item; write one line for anything not ticked.

## Evidence
- [ ] Calibration report {quarter} read; recommendation per lens: {summary}
- [ ] Replay determinism passed this quarter (or the diff explained)
- [ ] Drift checks reviewed; any alert explained
- [ ] Backup restore test passed; newest backup within {age} days
- [ ] Audit chain verified (`parakh audit verify`)

## Change control
- [ ] Every weight, threshold, policy or prompt change this quarter went through a PR with a version bump
- [ ] Overrides: none expired unnoticed; each active one still justified
- [ ] Model inventory (`docs/MODELS.md`) and model cards current

## Alerts and agents
- [ ] Alert precision per signal reviewed; signals below target tuned or demoted
- [ ] Agent shadow logs reviewed; no agent output contained amounts or quantities

## Decision
- Weights: CONFIRMED / CHANGED (new framework version: ______)
- Actions for next quarter:
  1.
  2.
"""


def review_template(report: CalibrationReport, max_backup_age_days: int) -> str:
    summary = ", ".join(f"{x.lens} {x.decision}" for x in report.recommendations)
    return REVIEW_TEMPLATE.format(
        quarter=report.quarter,
        date=report.generated_on,
        version=report.framework_version,
        summary=summary,
        age=max_backup_age_days,
    )
