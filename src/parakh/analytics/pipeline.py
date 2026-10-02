# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""One stock, one as-of date → one snapshot (F09). Pure: callers pass frames and rows, not stores.

    result = analyse_stock(request, bundle, meta)
    result.snapshot      # the canonical record (JSON-ready)
    result.events        # audit events the caller should emit (score, veto, verdict, thesis)

The order matters and is the plan's: momentum first (the value lens's trap detector reads its
12-month relative strength), then value, then the thesis check (a BROKEN thesis changes the
owned wording), then the verdict policy, then the attribution of any change.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from parakh import __version__
from parakh.analytics.fundamentals_view import Fundamentals
from parakh.analytics.indicators import sma_series
from parakh.analytics.momentum_build import momentum_context_parts, momentum_inputs
from parakh.analytics.profile_rows import profile_inputs_from, stakes_from
from parakh.analytics.regime import RegimeResult
from parakh.analytics.value_build import (
    build_inputs,
    earnings_accel_measure,
    price_on_or_before,
    value_context_parts,
)
from parakh.audit.events import AUD
from parakh.config import config_dir
from parakh.configs import ConfigBundle
from parakh.configs.models import Security
from parakh.holdings.position import PositionInfo
from parakh.lenses.base import LensConfig, StockContext
from parakh.lenses.momentum import MomentumLens
from parakh.lenses.value import ValueLens, components_for
from parakh.policy import attribution
from parakh.policy.overrides import active_for
from parakh.policy.verdict import PolicyInput, PrevState, decide
from parakh.registry import REGISTRY, discover
from parakh.snapshots.models import Framework, Snapshot, period_of
from parakh.storage.point_in_time import SHAREHOLDING_KEY, visible_asof
from parakh.thesis.model import ParsedThesis
from parakh.thesis.status import ThesisContext, evaluate_thesis, variable_names

CHART_SESSIONS = 260
QUALITATIVE_PENDING = {
    "status": "not_run",
    "reason": "the qualitative agent arrives in Phase 4 (F06); no LLM has touched this report",
}
EVENTS_UNAVAILABLE = {
    "status": "unavailable",
    "reason": "the event calendar (results dates, board meetings, ex-dates) arrives with the Phase 3 event watcher",
}


@dataclass
class StockRequest:
    sec: Security
    prices: pd.DataFrame
    fundamentals: list[dict[str, Any]]
    shareholding: list[dict[str, Any]]
    bench: pd.Series | None
    regime: RegimeResult
    thesis: ParsedThesis
    position: PositionInfo | None = None
    prev: dict[str, Any] | None = None
    lineage: dict[str, Any] = field(default_factory=dict)
    dq: list[dict[str, Any]] = field(default_factory=list)  # {check_id, status} for this ISIN
    index_pe_percentile: float | None = None


@dataclass(frozen=True)
class RunMeta:
    asof: dt.date
    run_id: str
    code_version: str
    config_hash: str
    now: dt.datetime


@dataclass
class StockResult:
    snapshot: Snapshot
    events: list[tuple[AUD, dict[str, Any]]]


def weights_hash(root: Path | None = None) -> str:
    """Short hash of the files that move a score: value, momentum and policy config."""
    d = hashlib.sha256()
    for name in ("value.yaml", "momentum.yaml", "verdict_policy.yaml"):
        # line endings differ between Windows and Linux checkouts; the hash must not
        d.update((root or config_dir()).joinpath(name).read_bytes().replace(b"\r\n", b"\n"))
    return d.hexdigest()[:8]


def _weekdays_between(a: dt.date, b: dt.date) -> int:
    """Whole weekdays after `a` up to `b` (an approximation of trading days; holidays make it generous)."""
    if b <= a:
        return 0
    return int(np.busday_count(a + dt.timedelta(days=1), b + dt.timedelta(days=1)))


def _chart_block(prices: pd.DataFrame, asof: dt.date, intrinsic: dict[str, Any]) -> dict[str, Any]:
    f = prices.copy()
    f["trade_date"] = pd.to_datetime(f["trade_date"]).dt.date
    f = f[f["trade_date"] <= asof].sort_values("trade_date")
    if f.empty:
        return {}
    close = f["close"].to_numpy(float)
    d50, d200 = sma_series(close, 50), sma_series(close, 200)
    tail = slice(-CHART_SESSIONS, None)

    def clean(a: np.ndarray) -> list[float | None]:
        return [None if not np.isfinite(x) else round(float(x), 2) for x in a[tail]]

    return {
        "dates": [d.isoformat() for d in f["trade_date"].iloc[tail]],
        "close": clean(close),
        "dma50": clean(d50),
        "dma200": clean(d200),
        "fair_value_low": intrinsic.get("low"),
        "fair_value_high": intrinsic.get("high"),
        "fair_value_mid": intrinsic.get("mid"),
        "next_event": None,
    }


def _metric_sub(bundle: ConfigBundle, profile: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub, comps in components_for(bundle.value, profile).items():
        for c in comps:
            out[c.metric] = sub
    for sub, comps in bundle.momentum.subscores.items():
        for c in comps:
            out.setdefault(c.metric, sub)
    return out


def _data_confidence(
    last_session: dt.date | None,
    asof: dt.date,
    fund: Fundamentals,
    req: StockRequest,
    bundle: ConfigBundle,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    conf = "High"
    pdq, fdq = bundle.data_quality.prices, bundle.data_quality.fundamentals
    if last_session is None:
        return "Low", ["no price history loaded"]
    stale = _weekdays_between(last_session, asof)
    if stale > pdq.max_stale_trading_days:
        conf = "Low"
        notes.append(
            f"last price session {last_session} is {stale} trading days before the as-of date"
        )
    if not fund.has_data():
        conf = "Low"
        notes.append("no fundamentals visible at the as-of date")
    elif (
        fund.last_quarter is not None
        and (asof - fund.last_quarter).days > fdq.max_latest_quarter_age_days
    ):
        conf = "Med" if conf == "High" else conf
        notes.append(
            f"latest quarter ({fund.last_quarter}) is older than {fdq.max_latest_quarter_age_days} days"
        )
    failed = [d["check_id"] for d in req.dq if d.get("status") == "fail"]
    if failed:
        conf = "Low"
        notes.append("data-quality checks failed: " + ", ".join(sorted(failed)))
    return conf, notes


def analyse_stock(req: StockRequest, bundle: ConfigBundle, meta: RunMeta) -> StockResult:
    discover()
    sec, asof = req.sec, meta.asof
    cfg_v, cfg_m = bundle.value, bundle.momentum
    period = period_of(asof)
    events: list[tuple[AUD, dict[str, Any]]] = []

    profile_ov = active_for(bundle.overrides, sec.isin, asof, "profile")
    profile = profile_ov.value if profile_ov else sec.profile
    archetype_ov = active_for(bundle.overrides, sec.isin, asof, "archetype")
    verdict_ov = active_for(bundle.overrides, sec.isin, asof, "verdict")
    thesis_ov = active_for(bundle.overrides, sec.isin, asof, "thesis_status")
    active_overrides = [
        o for o in (profile_ov, archetype_ov, verdict_ov, thesis_ov) if o is not None
    ]

    lag = bundle.data_quality.fundamentals.assumed_report_lag_days
    fund_rows = visible_asof(req.fundamentals, asof, lag)
    sh_rows = visible_asof(req.shareholding, asof, lag, SHAREHOLDING_KEY)
    fund = Fundamentals(fund_rows)

    price = price_on_or_before(req.prices, asof) if len(req.prices) else None
    stamps = (
        pd.to_datetime(req.prices["trade_date"]).dt.date
        if len(req.prices)
        else pd.Series([], dtype=object)
    )
    last_session = max((d for d in stamps if d <= asof), default=None)
    data_conf, dq_notes = _data_confidence(last_session, asof, fund, req, bundle)

    # -- momentum ------------------------------------------------------------------------------
    m_inp = momentum_inputs(
        sec.isin,
        sec.symbol,
        sec.cap,
        asof,
        req.prices,
        cfg_m,
        sec.listed_on,
        bench=req.bench,
        results_dates=[d for d in fund.result_dates() if d <= asof],
        earnings_accel=earnings_accel_measure(fund),
    )
    m_vals, m_reasons, m_extras = momentum_context_parts(m_inp, cfg_m)
    m_extras["regime"] = req.regime.regime
    m_extras["last_close"] = price
    owned = req.position is not None and req.position.quantity > 0
    m_ctx = StockContext(
        isin=sec.isin, symbol=sec.symbol, asof=asof, profile=profile, cap=sec.cap,
        metrics=m_vals, na_reasons=m_reasons, extras=m_extras, owned=owned,
    )  # fmt: skip
    m_res = MomentumLens().evaluate(
        m_ctx, LensConfig(lens_version=cfg_m.lens_version, params={"settings": cfg_m})
    )

    # -- value ---------------------------------------------------------------------------------
    inputs, reasons_in = profile_inputs_from(fund_rows)
    register = bundle.profile_inputs.listed_stakes.get(sec.isin)
    stakes = stakes_from(fund_rows, register.investees) if register else []
    v_inp = build_inputs(
        sec.isin, sec.symbol, sec.cap, profile, asof, price, fund_rows, cfg_v, sh_rows,
        sec.listed_on, inputs, reasons_in, stakes, m_vals.get("MET.momentum.excess_return_12m"),
        req.index_pe_percentile,
    )  # fmt: skip
    v_vals, v_reasons, v_extras = value_context_parts(v_inp, cfg_v)
    if archetype_ov:
        v_extras["archetype"] = archetype_ov.value
    v_extras["avg_traded_value_cr"] = m_vals.get("MET.momentum.avg_traded_value_cr")
    v_ctx = StockContext(
        isin=sec.isin, symbol=sec.symbol, asof=asof, profile=profile, cap=sec.cap,
        history_class=v_extras.get("history_class", "H3"),
        metrics=v_vals, na_reasons=v_reasons, extras=v_extras, owned=owned,
    )  # fmt: skip
    v_res = ValueLens().evaluate(
        v_ctx, LensConfig(lens_version=cfg_v.lens_version, params={"settings": cfg_v})
    )

    # -- thesis --------------------------------------------------------------------------------
    names = variable_names(REGISTRY.metrics)
    t_ctx = ThesisContext(
        metrics=v_vals | m_vals, fund=fund, price=price,
        value_score=v_res.score, momentum_score=m_res.score, names=names,
    )  # fmt: skip
    thesis = evaluate_thesis(
        req.thesis, t_ctx, asof, (req.prev or {}).get("thesis"), period, thesis_ov
    )

    # -- verdict -------------------------------------------------------------------------------
    prev = req.prev
    pv = (prev or {}).get("verdict") or {}
    prev_state = (
        PrevState(
            verdict=pv.get("verdict"), action=pv.get("action"), value_level=pv.get("value_level"),
            momentum_level=pv.get("momentum_level"), asof=(prev or {}).get("asof"),
        )
        if prev
        else None
    )  # fmt: skip
    target = None
    if req.thesis.front and req.thesis.front.sizing_rationale:
        target = (
            None  # the sizing note is prose; a numeric target weight is a Phase 4 thesis-form field
        )
    verdict = decide(
        PolicyInput(
            value=v_res, momentum=m_res, regime=req.regime.regime, owned=owned,
            weight_pct=req.position.weight_pct if req.position else None,
            target_weight_pct=target, thesis_status=thesis["status"],
            data_confidence=data_conf,  # type: ignore[arg-type]
            prev=prev_state, override=verdict_ov,
        ),
        bundle.verdict_policy,
    )  # fmt: skip

    # -- assemble ------------------------------------------------------------------------------
    value_d, mom_d = v_res.model_dump(mode="json"), m_res.model_dump(mode="json")
    regime_d = {
        "segment": sec.cap,
        "regime": req.regime.regime,
        "reasons": req.regime.reasons,
        "breadth": req.regime.breadth,
        "benchmark": cfg_m.cap_settings[sec.cap].benchmark,  # type: ignore[index]
        "benchmark_pct_vs_200dma": req.regime.benchmark_pct_vs_200,
        "flags": req.regime.flags,
        "known": req.regime.known,
    }
    msub = _metric_sub(bundle, profile)
    for d in (value_d, mom_d):
        d["details"]["metric_sub"] = {
            m: sub for m, sub in msub.items() if m in (d["metrics_used"] or [])
        }
    current = {
        "value": value_d,
        "momentum": mom_d,
        "verdict": verdict.model_dump(mode="json"),
        "regime": regime_d,
        "thesis": thesis,
    }
    verdict.drivers = attribution.drivers(prev, current, bundle.verdict_policy.top_drivers, msub)
    current["verdict"] = verdict.model_dump(mode="json")

    checks = [
        {**c, "last_attempt": asof.isoformat()} for c in value_d["details"].get("checks", [])
    ] + [
        {"id": u["check"], "name": u["check"], "state": "UNKNOWN", "detail": u["reason"], "last_attempt": asof.isoformat()}
        for u in value_d["details"].get("unknown_checks", [])
        if not str(u["check"]).startswith("RULE.")
    ]  # fmt: skip

    intrinsic = value_d["details"].get("intrinsic_value", {})
    framework = Framework(
        version=__version__,
        policy_version=bundle.verdict_policy.policy_version,
        lens_versions={"value": v_res.lens_version, "momentum": m_res.lens_version},
        config_hash=meta.config_hash,
        weights_hash=weights_hash(),
        code_version=meta.code_version,
    )
    snap = Snapshot(
        symbol=sec.symbol, isin=sec.isin, name=sec.name, cap=sec.cap, sector=sec.sector,
        profile=profile, history_class=str(v_extras.get("history_class", "H3")),
        period=period, asof=asof, run_id=meta.run_id, generated_at=meta.now, framework=framework,
        price={"close": price, "last_session": last_session.isoformat() if last_session else None, "source": "yfinance (adjusted)"},
        fundamentals_asof={
            "annual": v_extras["asof"].get("fundamentals_annual"),
            "quarter": v_extras["asof"].get("fundamentals_quarter"),
            "shareholding": v_extras["asof"].get("shareholding"),
            "visible_rows": len(fund_rows),
            "assumed_report_lag_days": lag,
        },
        value=value_d, momentum=mom_d, regime=regime_d, verdict=current["verdict"],
        position=req.position.model_dump(mode="json") if req.position else None,
        thesis=thesis, checks=checks, qualitative=dict(QUALITATIVE_PENDING),
        events=dict(EVENTS_UNAVAILABLE) | {"results_dates": [d.isoformat() for d in fund.result_dates()[-4:]]},
        data_quality={"confidence": data_conf, "notes": dq_notes, "checks": req.dq},
        lineage=req.lineage | {"config_hash": meta.config_hash, "code_version": meta.code_version},
        chart=_chart_block(req.prices, asof, intrinsic) if len(req.prices) else {},
        overrides=[o.model_dump(mode="json") for o in active_overrides],
        notes=[],
    )  # fmt: skip

    for lens_id, res in (("value", v_res), ("momentum", m_res)):
        events.append((AUD.SCORE_COMPUTED, {
            "isin": sec.isin, "lens": lens_id, "lens_version": res.lens_version, "score": res.score,
            "view": res.view, "confidence": res.confidence, "informational": res.informational,
        }))  # fmt: skip
    for veto in verdict.vetoes:
        events.append((AUD.VETO_TRIGGERED, {"isin": sec.isin, "rule": veto}))
    if verdict.changed:
        events.append((AUD.VERDICT_CHANGED, {
            "isin": sec.isin, "before": {"verdict": verdict.prev_verdict, "action": verdict.prev_action},
            "after": {"verdict": verdict.verdict, "action": verdict.action}, "drivers": verdict.drivers,
        }))  # fmt: skip
    if thesis["changed_from"] is not None:
        events.append((AUD.THESIS_CHANGED, {
            "isin": sec.isin, "before": {"status": thesis["changed_from"]}, "after": {"status": thesis["status"]}, "source": thesis["status_source"],
        }))  # fmt: skip
    return StockResult(snap, events)
