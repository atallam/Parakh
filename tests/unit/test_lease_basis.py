"""T-VAL-45…: airline lease basis. Screener's Borrowings already hold Ind AS 116 leases, so the
lease-adjusted metrics must not add the filed lease liabilities a second time (UAT-0 finding,
11 Oct 2026), and the lease cost is the sum of the last four filed quarters of rentals."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from parakh.analytics.metrics.value import ev_ebitdar, lease_adj_leverage
from parakh.analytics.profile_rows import profile_inputs_from
from parakh.analytics.value_build import build_inputs
from parakh.analytics.value_calc import VCalc
from parakh.configs import load_file
from parakh.configs.lens_models import ValueConfig
from parakh.storage.point_in_time import visible_asof
from tests.helpers import fundamentals as fx

ASOF = dt.date(2026, 10, 30)
INDIGO = "INE646L01027"


def _calc(inputs: dict[str, float | None], include_leases: bool) -> VCalc:
    cfg = load_file("value.yaml", ValueConfig).model_copy(
        update={"borrowings_include_leases": include_leases}
    )
    rows = visible_asof(fx.rows(isin=INDIGO), ASOF, 75)
    inp = build_inputs(
        INDIGO, "INDIGO", "large", "airline_lease_heavy", ASOF, 280.0, rows, cfg,
        fx.shareholding(INDIGO), dt.date(2006, 11, 10), inputs, None, None,
    )  # fmt: skip
    return VCalc(inp, cfg)


def _nd(v: VCalc) -> float:
    x = v.net_debt_cr()
    assert x is not None
    return x


def _ev(v: VCalc) -> float:
    x = v.ev_cr()
    assert x is not None
    return x


def _op(v: VCalc) -> float:
    x = v.f.ttm("Operating Profit")
    assert x is not None
    return x


def _borrowings(v: VCalc) -> float:
    return float(v.f.annual("balance_sheet", "Borrowings").iloc[-1])


def test_config_says_screener_borrowings_include_leases() -> None:
    """The shipped config states the INDIGO basis; flipping it is an oracle change."""
    assert load_file("value.yaml", ValueConfig).borrowings_include_leases is True


@pytest.mark.ac("AC-F04.10")
def test_leases_already_in_borrowings_are_not_added_twice() -> None:
    """T-VAL-45: same numerator whatever the filed lease balance, when borrowings include it."""
    small = _calc({"lease_liabilities_cr": 10.0, "lease_cost_cr": 900.0}, True)
    big = _calc({"lease_liabilities_cr": 40.0, "lease_cost_cr": 900.0}, True)
    lev_small, lev_big = lease_adj_leverage(small).value, lease_adj_leverage(big).value
    assert lev_small is not None and lev_small == pytest.approx(lev_big)
    op = _op(small)
    assert lev_small == pytest.approx(_nd(small) / (op + 900.0))
    ev = ev_ebitdar(small).value
    assert ev == pytest.approx(_ev(small) / (op + 900.0))


def test_leases_are_added_when_borrowings_exclude_them() -> None:
    """T-VAL-46: the other basis still works (a company whose export leaves leases out)."""
    v = _calc({"lease_liabilities_cr": 40.0, "lease_cost_cr": 900.0}, False)
    op = _op(v)
    assert lease_adj_leverage(v).value == pytest.approx((_nd(v) + 40.0) / (op + 900.0))


def test_lease_balance_above_borrowings_refuses_the_basis() -> None:
    """T-VAL-47: a lease balance larger than borrowings means the assumption is wrong: N/A."""
    probe = _calc({"lease_liabilities_cr": 1.0, "lease_cost_cr": 900.0}, True)
    v = _calc({"lease_liabilities_cr": _borrowings(probe) + 1.0, "lease_cost_cr": 900.0}, True)
    m = lease_adj_leverage(v)
    assert m.value is None and "exceed" in (m.reason or "")


def _q(metric: str, end: str, value: float) -> dict[str, Any]:
    return {"metric_id": f"profile.{metric}", "period_end": end, "value": value}


QUARTERS = [
    _q("aircraft_engine_rentals_cr", "2025-09-30", 500.0),
    _q("aircraft_engine_rentals_cr", "2025-12-31", 600.0),
    _q("aircraft_engine_rentals_cr", "2026-03-31", 762.9),
    _q("aircraft_engine_rentals_cr", "2026-06-30", 700.0),
]


def test_lease_cost_is_the_last_four_quarters_summed() -> None:
    """T-VAL-48: TTM rentals, not the latest quarter; older quarters are ignored."""
    old = _q("aircraft_engine_rentals_cr", "2025-06-30", 9999.0)
    values, reasons = profile_inputs_from([old, *QUARTERS])
    assert values["lease_cost_cr"] == pytest.approx(2562.9)
    assert "lease_cost_cr" not in reasons


def test_lease_cost_needs_four_consecutive_quarters() -> None:
    """T-VAL-49: three quarters, or a hole in the middle, leave it unset with a reason."""
    values, reasons = profile_inputs_from(QUARTERS[1:])
    assert "lease_cost_cr" not in values and "only 3 of 4" in reasons["lease_cost_cr"]
    gap = [
        QUARTERS[0],
        QUARTERS[2],
        QUARTERS[3],
        _q("aircraft_engine_rentals_cr", "2026-09-30", 1.0),
    ]
    values, reasons = profile_inputs_from(gap)
    assert "lease_cost_cr" not in values and "not consecutive" in reasons["lease_cost_cr"]
