"""Read-only views of calibration results for the MCP toolset (F17). No computation happens here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from parakh.config import REPO_ROOT
from parakh.configs import load_all
from parakh.notify.log import AlertsLog
from parakh.watch.state import StateStore


class RecommendationOut(BaseModel):
    lens: str
    decision: str = Field(description="CONFIRM, REVIEW or INSUFFICIENT.")
    reason: str


class ReportSummaryOut(BaseModel):
    available: bool
    quarter: str | None = None
    overall: str | None = None
    framework_version: str | None = None
    recommendations: list[RecommendationOut] = Field(default_factory=list)
    note: str = ""


class SignalPrecisionOut(BaseModel):
    code: str
    alerts: int
    rated: int
    precision_pct: float | None = None
    status: str


class AlertPrecisionOut(BaseModel):
    alerts: int
    rated: int
    precision_pct: float | None = None
    target_pct: float
    signals: list[SignalPrecisionOut] = Field(default_factory=list)


def report_summary(root: Path | None = None) -> ReportSummaryOut:
    folder = (root or REPO_ROOT) / "docs" / "calibration"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if not files:
        return ReportSummaryOut(
            available=False,
            note="No calibration report has been produced yet (`parakh calibrate report`).",
        )
    data: dict[str, Any] = json.loads(files[-1].read_text(encoding="utf-8"))
    recs = [RecommendationOut(**r) for r in data["recommendations"]]
    decisions = {r.decision for r in recs}
    overall = (
        "REVIEW"
        if "REVIEW" in decisions
        else "CONFIRM"
        if "CONFIRM" in decisions
        else "INSUFFICIENT"
    )
    return ReportSummaryOut(
        available=True, quarter=data["quarter"], overall=overall,
        framework_version=data["framework_version"], recommendations=recs,
    )  # fmt: skip


def alert_precision() -> AlertPrecisionOut:
    from parakh.calibration.feedback import alert_precision as compute

    rows = AlertsLog(StateStore().root / "alerts").rows()
    s = compute(rows, load_all().calibration.alerts)
    return AlertPrecisionOut(
        alerts=s.alerts, rated=s.rated, precision_pct=s.precision_pct, target_pct=s.target_pct,
        signals=[
            SignalPrecisionOut(
                code=x.code, alerts=x.alerts, rated=x.rated,
                precision_pct=x.precision_pct if x.status != "not enough ratings" else None,
                status=x.status,
            )
            for x in s.signals
        ],
    )  # fmt: skip
