"""Code versus the UAT-0 analyst oracle (plan 14 §4.1): value metrics on the three golden stocks.

`tests/oracles/golden_expected.json` holds the oracle's derived values (built by
`tools/compare_oracle.py` from Excel formulas on the raw Screener exports). The code is changed to
match the oracle, never the other way round. Disagreements still awaiting the owner's decision are
listed in OPEN and must still disagree (strict), so fixing one turns the test red until it is removed.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from parakh.analytics.metrics.value import compute_all
from parakh.analytics.value_build import build_inputs
from parakh.analytics.value_calc import VCalc
from parakh.lenses.value import default_settings

ROOT = Path(__file__).resolve().parents[1]
ORACLE = json.loads((ROOT / "oracles" / "golden_expected.json").read_text(encoding="utf-8"))
TOL = ORACLE["tolerance"]
SCORE_METRICS = ("pe_percentile_10y", "roce_trend_pp", "op_margin_trend_pp")

# (symbol, metric) -> why it disagrees; the decision is recorded in docs/uat/UAT-0_*.md
OPEN: dict[tuple[str, str], str] = {}

# Accepted definition difference (UAT-0 finding F3, owner decision 2026-10-03): the code prices at today's
# price x FY26 adjusted shares, the oracle uses the export's market cap. "Discount to median" magnifies the 0.2% gap.
ACCEPTED_SHARE_BASIS = {
    ("HDFCBANK", "pe_discount_own_3y"),
    ("HDFCBANK", "ev_ebitda_discount_own"),
    ("INDIGO", "pb_discount_own_5y"),
}
SHARE_BASIS_REL = 0.04

CASES = [
    (isin, sym, key.removeprefix("MET.value."), val)
    for isin, body in ORACLE["stocks"].items()
    for sym in [body["symbol"]]
    for key, val in body.items()
    if key.startswith("MET.value.") and not isinstance(val, str)
]


def _code(isin: str, symbol: str, price: float) -> dict[str, float | None]:
    rows = json.loads(
        (ROOT / "fixtures" / "golden" / isin / "facts.json").read_text(encoding="utf-8")
    )["rows"]
    cfg = default_settings()
    inp = build_inputs(isin, symbol, "large", "standard", dt.date(2026, 10, 3), price, rows, cfg)
    return compute_all(VCalc(inp, cfg))[0]


@pytest.fixture(scope="module")
def code() -> dict[str, dict[str, float | None]]:
    return {
        body["symbol"]: _code(isin, body["symbol"], body["price"])
        for isin, body in ORACLE["stocks"].items()
    }


def _agrees(
    metric: str, got: float | None, expected: float | None, rel: float | None = None
) -> bool:
    if expected is None:
        return got is None
    if got is None:
        return False
    if metric in SCORE_METRICS:
        return got == pytest.approx(expected, abs=TOL["abs_score"])
    return got == pytest.approx(expected, rel=rel or TOL["rel"], abs=1e-9)


@pytest.mark.parametrize(("isin", "symbol", "metric", "expected"), CASES, ids=lambda x: str(x)[:30])
def test_code_matches_oracle(code, isin, symbol, metric, expected) -> None:
    got = code[symbol]["MET.value." + metric]
    rel = SHARE_BASIS_REL if (symbol, metric) in ACCEPTED_SHARE_BASIS else None
    agrees = _agrees(metric, got, expected, rel)
    if (symbol, metric) in OPEN:  # strict: fixing the code must also remove the entry
        assert not agrees, f"{symbol} {metric} now agrees with the oracle: remove it from OPEN"
        return
    assert agrees, f"{symbol} {metric}: oracle {expected}, code {got}"
