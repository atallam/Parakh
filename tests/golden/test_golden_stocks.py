"""Golden stocks: HDFCBANK, INDIGO, M&M on real Screener fundamentals (plan 14 L3).

Regression baselines on deterministic synthetic prices; see tests/fixtures/golden/README.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from parakh.configs import load_all
from parakh.orchestration.analysis import run_monthly
from tests.helpers.pilot import END, pilot_data

GOLD = Path(__file__).resolve().parents[1] / "fixtures" / "golden"

# symbol -> (isin, verdict, value score, momentum score, rule id)
EXPECTED = {
    "HDFCBANK": ("INE040A01034", "WATCH", 89.7, 25.1, "VP.matrix.high_value×weak_momentum"),
    "INDIGO": ("INE646L01027", "BUY", 71.7, 48.7, "VP.matrix.high_value×neutral_momentum"),
    "M&M": ("INE101A01026", "BUY", 82.2, 70.5, "VP.matrix.fair_value×strong_momentum"),
}


def _facts(isin: str) -> dict:
    return json.loads((GOLD / isin / "facts.json").read_text(encoding="utf-8"))


def test_golden_facts_name_the_export_they_came_from() -> None:
    """The Screener exports are not committed (source terms); the manifest records each export's hash."""
    for line in (GOLD / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        assert _facts(name.split("/")[0])["export_hash"] == "sha256:" + digest, name


@pytest.fixture(scope="module")
def snaps(tmp_path_factory):
    bundle = load_all()
    data = pilot_data(bundle)
    for isin, *_ in EXPECTED.values():
        data.fundamental_rows[isin] = _facts(isin)["rows"]
    res = run_monthly(bundle, data, END, out_root=tmp_path_factory.mktemp("golden"))
    assert not [s for s in res.stocks if getattr(s, "error", None)]
    return {s.symbol: s for s in res.snapshots}


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_golden_stock(snaps, symbol: str) -> None:
    isin, verdict, value, momentum, rule = EXPECTED[symbol]
    s = snaps[symbol]
    assert s.isin == isin
    assert s.verdict["verdict"] == verdict and s.verdict["rule_id"] == rule
    assert s.value["score"] == pytest.approx(value, abs=3)
    assert s.momentum["score"] == pytest.approx(momentum, abs=3)
    assert s.verdict["vetoes"] == []
