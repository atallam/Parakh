"""LENS.momentum: scores trend strength against the right benchmark (plan 02, F05).

Inputs arrive as a `StockContext` (metrics plus extras built by `analytics.momentum_build`);
the lens does no I/O. It returns a 0–100 score, the momentum view (STRONG / NEUTRAL / WEAK),
active signals, exit levels, and honest N/A reasons. Limited-history rules (plan 02 §3.9):

- fewer than 126 sessions after the listing exclusion → informational (shown, not scored
  into the verdict);
- 126–251 sessions → scored on what exists, confidence capped at Med;
- the Trend Template is reported as x of y, y being the criteria that could be computed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from parakh.analytics.metrics.momentum import MOMENTUM_METRICS
from parakh.analytics.scoring import (
    Confidence,
    SubScore,
    cap_at,
    combine,
    confidence_from_missing,
    score_subscore,
)
from parakh.configs import load_file
from parakh.configs.lens_models import MomentumConfig
from parakh.lenses.base import Lens, LensConfig, LensResult, StockContext
from parakh.registry import register_lens

M = "MET.momentum."


@lru_cache(maxsize=1)
def default_settings() -> MomentumConfig:
    return load_file("momentum.yaml", MomentumConfig)


def settings_for(cfg: LensConfig) -> MomentumConfig:
    given = cfg.params.get("settings")
    return given if isinstance(given, MomentumConfig) else default_settings()


def cap_weights(s: MomentumConfig, cap: str) -> dict[str, float]:
    w = dict(s.weights)
    for k, delta in s.cap_settings[cap].weight_shift.items():  # type: ignore[index]
        w[k] = w.get(k, 0) + delta
    return w


@register_lens("momentum")
class MomentumLens(Lens):
    lens_version = "1.0.0"
    required_metrics = list(MOMENTUM_METRICS)
    applicable_profiles: list[str] = []

    def evaluate(self, ctx: StockContext, cfg: LensConfig) -> LensResult:
        s = settings_for(cfg)
        cap = ctx.cap if ctx.cap in s.cap_settings else "large"
        weights = cap_weights(s, cap)
        subs: dict[str, SubScore] = {
            name: score_subscore(comps, ctx.metrics, ctx.na_reasons)
            for name, comps in s.subscores.items()
        }
        score, missing_share, parts = combine(weights, subs)
        sessions = ctx.metrics.get(M + "sessions")
        flags = list(ctx.extras.get("flags", []))
        explain: list[str] = []
        na = {m: r for sub in subs.values() for m, r in sub.missing.items()}

        conf: Confidence = confidence_from_missing(missing_share, s.confidence.step_missing_weight)
        informational = False
        if score is None:
            conf = "Low"
        if sessions is not None:
            if sessions < s.history.informational_below:
                informational = True
                conf = "Low"
                flags.append(
                    f"limited history: {int(sessions)} sessions; informational below "
                    f"{s.history.informational_below}"
                )
            elif sessions < s.history.confidence_cap_below:
                conf = cap_at(conf, "Med")
                flags.append(f"history {int(sessions)} sessions; confidence capped at Med")
        floor = s.cap_settings[cap].min_traded_value_cr  # type: ignore[index]
        traded = ctx.metrics.get(M + "avg_traded_value_cr")
        if floor and traded is not None and traded < floor:
            flags.append(f"illiquid: ₹{traded:.1f} Cr a day, below the ₹{floor:g} Cr floor")
            conf = cap_at(conf, "Med")

        items: list[dict[str, Any]] = ctx.extras.get("template_items", [])
        known = [i for i in items if i["passed"] is not None]
        t_pass = sum(1 for i in known if i["passed"])
        t_known = len(known)
        stage_v = ctx.metrics.get(M + "stage")
        stage = int(stage_v) if stage_v is not None else None
        rs_pct = ctx.metrics.get(M + "rs_percentile")
        regime = str(ctx.extras.get("regime", "Neutral"))
        signals = ctx.extras.get("signals", [])
        fired = [x["id"] for x in signals if x["status"] == "fired"]
        confirmed = [x["id"] for x in signals if x["status"] == "fired" and x["confirmed"]]

        gate = self._strong_gate(
            s, items_known=(t_pass, t_known), stage=stage, rs_pct=rs_pct, ctx=ctx
        )
        if rs_pct is None and s.trend_template.rs_percentile_unavailable == "skip":
            flags.append("RS percentile unavailable (pilot universe); criterion skipped")
            conf = cap_at(conf, "Med")
        view = "NEUTRAL"
        if score is None:
            view = "UNKNOWN"
        else:
            weak_triggers = [x for x in ("M21", "M25") if x in confirmed]
            if score < s.views.weak_score or stage in (3, 4) or weak_triggers:
                view = "WEAK"
                if weak_triggers:
                    explain.append(f"exit signal {', '.join(weak_triggers)} active")
                elif stage in (3, 4):
                    explain.append(f"Weinstein stage {stage}")
            elif score >= s.views.strong_score and gate["passed"]:
                if regime == "Risk-Off":
                    explain.append("would be STRONG, held at NEUTRAL by the Risk-Off regime")
                else:
                    view = "STRONG"
        top = sorted(parts.items(), key=lambda kv: -kv[1])[:2]
        if top and score is not None:
            explain.append("strongest: " + ", ".join(f"{k} {v:.0f}" for k, v in top))

        details = self._details(ctx, s, cap, subs, t_pass, t_known, stage, signals, regime)
        details["strong_gate"] = gate
        details["metric_values"] = {
            m: ctx.metrics.get(m) for m in sorted({m for sub in subs.values() for m in sub.used})
        }
        return LensResult(
            lens_id=self.lens_id,
            lens_version=s.lens_version,
            score=score,
            subscores={k: round(v.value, 4) for k, v in subs.items() if v.value is not None},
            view=view,
            confidence=conf,
            informational=informational,
            metrics_used=sorted({m for sub in subs.values() for m in sub.used}),
            signals=fired,
            vetoes=[],
            explanations=explain,
            flags=sorted(set(flags)),
            na=na,
            details=details,
        )

    @staticmethod
    def _strong_gate(
        s: MomentumConfig,
        items_known: tuple[int, int],
        stage: int | None,
        rs_pct: float | None,
        ctx: StockContext,
    ) -> dict[str, Any]:
        """The structural tests a STRONG view needs besides the score (plan 02 §3.7)."""
        t_pass, t_known = items_known
        need = s.views.strong_template_min
        if t_known and t_known < 8:
            need = max(1, round(need * t_known / 8))  # scale the bar to the criteria computable
        abs12 = ctx.metrics.get(M + "absolute_return_12m")
        checks = {
            "Trend Template": t_known >= 3 and t_pass >= need,
            "Weinstein stage 2": stage == 2,
            "relative strength percentile": rs_pct is None
            or rs_pct >= s.views.strong_rs_percentile_min,
            "positive 12-month return": abs12 is None or abs12 > s.absolute_momentum_min,
        }
        failed = [name for name, ok in checks.items() if not ok]
        return {"passed": not failed, "failed": failed, "checks": checks}

    @staticmethod
    def _details(
        ctx: StockContext,
        s: MomentumConfig,
        cap: str,
        subs: dict[str, SubScore],
        t_pass: int,
        t_known: int,
        stage: int | None,
        signals: list[dict[str, Any]],
        regime: str,
    ) -> dict[str, Any]:
        m = ctx.metrics
        caps = s.cap_settings[cap]  # type: ignore[index]
        peak, atr, dma200 = m.get(M + "peak_close_52w"), m.get(M + "atr_14"), m.get(M + "dma200")
        stop = None
        if peak is not None:
            by_pct = peak * (1 - caps.trailing_stop_pct)
            stop = max(by_pct, peak - caps.trailing_stop_atr_x * atr) if atr is not None else by_pct
        return {
            "benchmark": caps.benchmark,
            "excess_return": {k: m.get(f"{M}excess_return_{k}") for k in ("1m", "3m", "6m", "12m")}
            | {"12_1": m.get(M + "mom_12_1")},
            "rs_percentile": m.get(M + "rs_percentile"),
            "mansfield_rs": m.get(M + "mansfield_rs"),
            "dma": {
                "price": ctx.extras.get("last_close"),
                "dma50": m.get(M + "dma50"),
                "dma150": m.get(M + "dma150"),
                "dma200": dma200,
                "dma200_slope_20d": m.get(M + "dma200_slope"),
                "pct_above_200": m.get(M + "pct_above_200"),
            },
            "trend_template": {"passed": t_pass, "computable": t_known, "of": 8},
            "template_items": ctx.extras.get("template_items", []),
            "stage": stage,
            "pct_from_52w_high": m.get(M + "pct_from_52w_high"),
            "sessions": m.get(M + "sessions"),
            "regime": regime,
            "active_signals": signals,
            "exit_levels": {"trailing_stop": stop, "trend_exit_200dma": dma200},
            "weights": cap_weights(s, cap),
            "subscore_missing": {k: v.missing for k, v in subs.items() if v.missing},
            "lens_flags_from_data": ctx.extras.get("flags", []),
        }
