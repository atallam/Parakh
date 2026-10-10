"""TOOL.calibration.*: the latest calibration report and alert precision, read-only (F17; plan 15 §4.2)."""

from __future__ import annotations

from pydantic import BaseModel

from parakh.mcp.registry import ToolCall, Toolset
from parakh.services import calibration_service
from parakh.services.calibration_service import AlertPrecisionOut, ReportSummaryOut

CALIBRATION = Toolset("calibration", version="0.1.0")


class NoInput(BaseModel):
    pass


@CALIBRATION.tool("report_summary", tier="R", title="Latest calibration report")
def report_summary(params: NoInput, call: ToolCall) -> ReportSummaryOut:
    """Return the verdict of the latest quarterly calibration report: for each lens, whether its
    score weights are CONFIRMED by the evidence, due for REVIEW, or INSUFFICIENT (too little data).

    Use it to answer "do the weights still stand?" or "when was the framework last calibrated?".
    It never changes a weight; changes go through a pull request and a framework version bump.
    INSUFFICIENT is an honest answer while the history is short, not an error.
    """
    return calibration_service.report_summary()


@CALIBRATION.tool("alert_precision", tier="R", title="Alert precision per signal")
def alert_precision(params: NoInput, call: ToolCall) -> AlertPrecisionOut:
    """Return, for each signal ID, how many alerts were sent, how many the owner rated, and the
    share rated useful against the target.

    Use it to answer "which alerts are noisy?". Precision is shown as null until the signal has
    enough ratings to mean something; do not infer a rate from fewer ratings than that.
    """
    return calibration_service.alert_precision()
