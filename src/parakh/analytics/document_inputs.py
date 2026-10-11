"""Value-lens inputs that come from documents (investor presentations, results releases).

`config/document_inputs.yaml` holds each number with its source, tier and as-of date. A number is
used only when the owner has checked it against the source and set `verified: true`, and only
from its as-of date onward (point in time). Filed-XBRL inputs (profile_rows) take precedence.
Nothing is estimated: a number that is open, unverified or not yet visible leaves the input
unset, with the reason shown in the report.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from parakh.configs.models import DocumentInputsConfig

__all__ = ["document_inputs_for"]


def document_inputs_for(
    cfg: DocumentInputsConfig, isin: str, asof: dt.date
) -> tuple[dict[str, float | None], dict[str, str], dict[str, dict[str, Any]]]:
    """Return (values, reasons, lineage) for one stock at an as-of date."""
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    lineage: dict[str, dict[str, Any]] = {}
    for key, item in (cfg.inputs.get(isin) or {}).items():
        if item is None:
            reasons[key] = f"{key}: open, not yet sourced (document_inputs.yaml)"
        elif item.as_of > asof:
            reasons[key] = f"{key}: source dated {item.as_of}, after the as-of date {asof}"
        elif not item.verified:
            reasons[key] = (
                f"{key}: {item.tier} source awaiting your check against the document "
                "(document_inputs.yaml: verified)"
            )
        else:
            values[key] = item.value
            lineage[key] = {
                "value": item.value,
                "as_of": item.as_of.isoformat(),
                "tier": item.tier,
                "source": item.source,
            }
    return values, reasons, lineage
