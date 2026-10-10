"""F17 analysis: signal outcomes, score-quintile calibration, alert precision, watchlist scorecard."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from parakh.calibration import backtest as bt
from parakh.calibration import feedback as fb
from parakh.calibration import outcomes as oc
from parakh.calibration import quintiles as qn
from parakh.calibration.scorecard import build_scorecard
from parakh.configs import load_all
from parakh.watchlist.models import Entry, Suggestion, WatchlistState
from tests.helpers.calibration import frame, make_isin, trailing_panel, world

CAL = load_all().calibration
D0 = dt.date(2024, 1, 1)


def ramp_book(slopes: dict[str, float], n: int = 300) -> tuple[bt.PriceBook, pd.DatetimeIndex]:
    days = pd.bdate_range(D0, periods=n)
    frames = {isin: frame(isin, days, 100 * np.exp(np.arange(n) * s)) for isin, s in slopes.items()}
    return bt.PriceBook.from_frames(frames), days


# -- signal outcomes ------------------------------------------------------------------------------
def test_forward_return_matured_pending_and_delisted() -> None:
    up, dn = make_isin(1), make_isin(2)
    book, days = ramp_book({up: 0.01, dn: -0.01})
    d = days[10].date()
    f = oc.forward(book, up, d, 21, None, 15)
    assert f.status == "matured" and f.ret == pytest.approx(np.exp(0.21) - 1, rel=1e-6)
    late = days[-5].date()
    assert oc.forward(book, up, late, 21, None, 15).status == "pending"
    # a series that stops early while the data goes on is a delisting, valued at its last close
    short = frame("X", days[:100], 100 * np.exp(np.arange(100) * -0.02))
    book2 = bt.PriceBook.from_frames({"X": short, up: frame(up, days, np.full(len(days), 100.0))})
    g = oc.forward(book2, "X", days[90].date(), 21, None, 15)
    assert g.status == "delisted" and g.ret is not None and g.ret < 0


def test_outcomes_hit_rate_follows_the_direction_of_the_signal() -> None:
    up, dn = make_isin(1), make_isin(2)
    book, days = ramp_book({up: 0.01, dn: -0.01})
    obs = [
        oc.Observation(up, "UP", "M01", days[i].date(), "entry", "live") for i in range(5, 30)
    ] + [oc.Observation(dn, "DN", "E01", days[i].date(), "exit", "live") for i in range(5, 30)]
    table = {r.code: r for r in oc.track(obs, book, {}, {}, CAL.outcomes)}
    entry, exit_ = table["M01"].horizons["1M"], table["E01"].horizons["1M"]
    assert entry.matured == 25 and entry.hit_rate_pct == 100.0
    assert exit_.hit_rate_pct == 100.0  # fell after an exit signal: the signal was right
    assert entry.evidence == "enough to read"


def test_outcomes_with_few_observations_are_not_concluded() -> None:
    up = make_isin(1)
    book, days = ramp_book({up: 0.01})
    obs = [oc.Observation(up, "UP", "M01", days[5].date(), "entry", "live")]
    row = oc.track(obs, book, {}, {}, CAL.outcomes)[0].horizons["1M"]
    assert row.evidence.startswith("not enough yet")


def test_alert_rows_become_one_observation_per_stock_signal_day() -> None:
    rows = [
        {"kind": "signal", "code": "M01", "isin": "A", "asof": "2025-01-31", "decision": "sent"},
        {"kind": "signal", "code": "M01", "isin": "A", "asof": "2025-01-31", "decision": "shadow"},
        {
            "kind": "signal",
            "code": "M01",
            "isin": "A",
            "asof": "2025-01-31",
            "decision": "feedback",
        },
        {"kind": "signal", "code": "ZZ", "isin": "A", "asof": "2025-01-31", "decision": "sent"},
    ]
    obs = oc.observations_from_alerts(rows, {"M01": "entry"})
    assert len(obs) == 1 and obs[0].direction == "entry"


def test_panel_observations_use_new_signals_only() -> None:
    panel = pd.DataFrame(
        {
            "asof": [dt.date(2025, 1, 31), dt.date(2025, 2, 28), dt.date(2025, 3, 31)],
            "isin": ["A"] * 3,
            "symbol": ["A"] * 3,
            "segment": ["large"] * 3,
            "signals": ["M01", "M01", "M01,M02"],
        }
    )
    obs = oc.observations_from_panel(panel, {"M01": "entry", "M02": "entry"})
    assert [(o.code, o.date.month) for o in obs] == [("M01", 1), ("M02", 3)]


# -- score-quintile calibration (AC-F17.3) --------------------------------------------------------
@pytest.fixture(scope="module")
def scored_world():  # type: ignore[no-untyped-def]
    prices, _bench, _ = world(n_stocks=30, years=8.0, seed=11, spread=0.0015)
    panel = trailing_panel(prices)
    book = bt.PriceBook.from_frames(prices)
    return qn.attach_forward(panel, book, [6], CAL.outcomes.delisted_gap_days), panel


@pytest.mark.ac("AC-F17.3")
def test_predictive_scores_give_a_positive_top_minus_bottom_spread(scored_world) -> None:  # type: ignore[no-untyped-def]
    rows, _ = scored_world
    cal = qn.calibrate(rows, "score", 6, CAL.quintiles, lens="momentum")
    assert cal.periods_used >= CAL.quintiles.min_periods
    assert len(cal.buckets) == CAL.quintiles.buckets
    assert cal.spread_pct is not None and cal.spread_pct > 0
    assert cal.buckets[-1].mean_pct > cal.buckets[0].mean_pct  # type: ignore[operator]
    assert cal.verdict == "confirmed"


@pytest.mark.ac("AC-F17.3")
def test_scores_that_are_noise_are_not_confirmed(scored_world) -> None:  # type: ignore[no-untyped-def]
    rows, _ = scored_world
    noisy = rows.copy()
    noisy["score"] = np.random.default_rng(5).uniform(0, 100, len(noisy))
    cal = qn.calibrate(noisy, "score", 6, CAL.quintiles, lens="momentum")
    assert cal.verdict in ("inconclusive", "reversed")


@pytest.mark.ac("AC-F17.3")
def test_reversed_scores_are_called_reversed(scored_world) -> None:  # type: ignore[no-untyped-def]
    rows, _ = scored_world
    flipped = rows.copy()
    flipped["score"] = 100 - flipped["score"]
    cal = qn.calibrate(flipped, "score", 6, CAL.quintiles, lens="momentum")
    assert cal.verdict == "reversed" and cal.spread_pct < 0  # type: ignore[operator]


@pytest.mark.ac("AC-F17.3")
def test_too_few_stocks_is_insufficient_not_a_finding(scored_world) -> None:  # type: ignore[no-untyped-def]
    rows, _ = scored_world
    few = rows[rows["isin"].isin(sorted(rows["isin"].unique())[:7])]
    cal = qn.calibrate(few, "score", 6, CAL.quintiles, lens="momentum")
    assert cal.verdict == "insufficient" and cal.periods_used == 0 and cal.reason


def test_empty_input_is_insufficient() -> None:
    assert (
        qn.calibrate(pd.DataFrame(), "score", 6, CAL.quintiles, lens="value").verdict
        == "insufficient"
    )


def test_add_months_clamps_to_month_end() -> None:
    assert qn.add_months(dt.date(2025, 1, 31), 1) == dt.date(2025, 2, 28)
    assert qn.add_months(dt.date(2025, 11, 30), 3) == dt.date(2026, 2, 28)


def test_by_verdict_orders_by_mean_return(scored_world) -> None:  # type: ignore[no-untyped-def]
    rows, _ = scored_world
    r = rows.copy()
    r["verdict"] = np.where(r["score"] > 50, "BUY", "AVOID")
    out = qn.by_verdict(r, 6)
    assert [v.verdict for v in out] == ["BUY", "AVOID"]


# -- alert precision (AC-F17.5) -------------------------------------------------------------------
def alert(aid: str, code: str = "M01", decision: str = "sent") -> dict:
    return {"alert_id": aid, "code": code, "decision": decision, "kind": "signal"}


def rating(aid: str, verdict: str, channel: str = "telegram", tag: str | None = None) -> dict:
    return {
        "alert_id": aid,
        "decision": "feedback",
        "reason": verdict,
        "channel": channel,
        "tag": tag,
    }


@pytest.mark.ac("AC-F17.5")
def test_precision_per_signal_from_telegram_and_streamlit() -> None:
    rows = [alert(f"a{i}") for i in range(12)] + [alert(f"b{i}", "E01") for i in range(3)]
    rows += [rating(f"a{i}", "useful") for i in range(8)]
    rows += [rating(f"a{i}", "noise", "streamlit", "late") for i in range(8, 12)]
    rows += [rating("b0", "useful")]
    s = fb.alert_precision(rows, CAL.alerts)
    m01 = next(x for x in s.signals if x.code == "M01")
    assert (m01.rated, m01.useful, m01.noise) == (12, 8, 4)
    assert m01.precision_pct == pytest.approx(66.67, abs=0.01)
    assert m01.status == "below target" and m01.tags == {"late": 4}
    assert next(x for x in s.signals if x.code == "E01").status == "not enough ratings"
    assert s.by_channel == {"telegram": 9, "streamlit": 4}


@pytest.mark.ac("AC-F17.5")
def test_latest_rating_wins_and_system_alerts_are_excluded() -> None:
    rows = [alert("a1"), alert("s1", "SYS.health"), rating("a1", "noise"), rating("a1", "useful")]
    s = fb.alert_precision(rows, CAL.alerts)
    assert s.alerts == 1 and s.useful == 1 and s.noise == 0


def test_wilson_lower_bound_tempers_small_samples() -> None:
    assert fb.wilson_lower(0, 0) is None
    assert fb.wilson_lower(3, 3) < 0.7  # type: ignore[operator]
    assert fb.wilson_lower(90, 100) > fb.wilson_lower(9, 10)  # type: ignore[operator]


# -- watchlist scorecard --------------------------------------------------------------------------
def entry(isin: str, kind: str, source: str, added: dt.date, **kw) -> Entry:  # type: ignore[no-untyped-def]
    return Entry(
        entry_id=f"E-{isin}-{kind}", isin=isin, symbol=isin[-4:], cap="large", list_kind=kind,  # type: ignore[arg-type]
        added_on=added, added_period=f"{added:%Y-%m}", added_by="rule", sources=[source], **kw,
    )  # fmt: skip


def test_scorecard_groups_by_source_and_keeps_archived_names() -> None:
    good, bad, faded = make_isin(1), make_isin(2), make_isin(3)
    book, days = ramp_book({good: 0.004, bad: -0.004, faded: -0.003}, n=600)
    start = days[5].date()
    st = WatchlistState()
    for e in (
        entry(good, "system", "SRC.top_combined", start),
        entry(bad, "my", "SRC.value_zone", start),
        entry(
            faded,
            "system",
            "SRC.top_combined",
            start,
            status="archived",
            removed_on=days[50].date(),
            removal_rule="RM.fade",
        ),  # fmt: skip
    ):
        st.entries[e.entry_id] = e
    st.suggestions["s1"] = Suggestion(
        sugg_id="s1", isin=good, symbol="G", cap="large", action="add_my", sources=["SRC.top_combined"],
        origin="agent:scout", reason="r", status="approved", created_on=start, expires_on=start,
    )  # fmt: skip
    st.suggestions["s2"] = st.suggestions["s1"].model_copy(
        update={"sugg_id": "s2", "origin": "rule", "status": "rejected"}
    )
    bench = {"large": pd.Series(np.full(600, 100.0), index=[d.date() for d in days])}
    card = build_scorecard(st, book, bench, CAL.scorecard, {good: days[20].date()}, 15)
    src = {g.name: g for g in card.by_source}
    assert src["SRC.top_combined"].entries == 2  # the archived name still counts
    assert src["SRC.top_combined"].cells["3M"].matured == 2
    assert src["SRC.value_zone"].cells["3M"].mean_pct < 0  # type: ignore[operator]
    assert "not enough yet" in src["SRC.value_zone"].note
    assert {g.name for g in card.by_list} == {"my watchlist", "system watchlist"}
    assert [g.name for g in card.archive_after_removal] == ["removed by a rule"]
    rows = {(d["source"], d["origin"]): d for d in card.decisions}
    assert rows[("SRC.top_combined", "agent")]["approved"] == 1
    assert rows[("SRC.top_combined", "rule")]["rejected"] == 1
    assert card.purchase["bought"] == 1 and card.purchase["median_days_to_buy"] == 21
