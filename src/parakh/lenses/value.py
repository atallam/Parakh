"""LENS.value: scores valuation, quality, balance sheet, growth and governance (plan 01, F04).

Inputs arrive as a `StockContext` built by `analytics.value_build`; the lens does no I/O.
Sector profiles replace metric lists (plan 01 §3); history classes decide which own-history
measures exist (§3.1). When the value lens is informational (H0, a pre-profit profile, or under
half of the valuation weight computable) the score is still shown, each missing metric as
❔ N/A with its reason, and the verdict policy uses the Fair-value row (AC-F04.9).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from parakh.analytics.metrics.value import VALUE_METRICS
from parakh.analytics.regime import mos_uplift_pp  # noqa: F401  (re-exported for callers)
from parakh.analytics.scoring import (
    Confidence,
    SubScore,
    cap_at,
    combine,
    confidence_from_missing,
    score_subscore,
)
from parakh.configs import load_file
from parakh.configs.lens_models import Component, RegimeConfig, ValueConfig
from parakh.lenses.base import Lens, LensConfig, LensResult, StockContext
from parakh.lenses.value_rules import negative_cfo, nnpa_cap, pledge_cap
from parakh.registry import REGISTRY, register_lens

V = "MET.value."
VALUE_LENS_ID = "value"
SUBSCORES = ("valuation", "quality", "balance_sheet", "growth", "governance")


@lru_cache(maxsize=1)
def default_settings() -> ValueConfig:
    return load_file("value.yaml", ValueConfig)


@lru_cache(maxsize=1)
def default_regime() -> RegimeConfig:
    return load_file("regime.yaml", RegimeConfig)


def settings_for(cfg: LensConfig) -> ValueConfig:
    given = cfg.params.get("settings")
    return given if isinstance(given, ValueConfig) else default_settings()


def components_for(s: ValueConfig, profile: str) -> dict[str, list[Component]]:
    spec = s.profiles.get(profile) or s.profiles["standard"]  # type: ignore[call-overload]
    comps = {k: list(v) for k, v in s.subscores.items()}
    for k, v in spec.replace.items():
        comps[k] = list(v)
    return comps


@register_lens("value")
class ValueLens(Lens):
    lens_version = "1.0.0"
    required_metrics = list(VALUE_METRICS)
    applicable_profiles: list[str] = []

    def evaluate(self, ctx: StockContext, cfg: LensConfig) -> LensResult:
        s = settings_for(cfg)
        cap = ctx.cap if ctx.cap in s.cap_settings else "large"
        profile = ctx.profile if ctx.profile in s.profiles else "standard"
        spec = s.profiles[profile]  # type: ignore[index]
        comps = components_for(s, profile)
        weights = dict(s.cap_settings[cap].weights)  # type: ignore[index]
        subs: dict[str, SubScore] = {
            k: score_subscore(comps[k], ctx.metrics, ctx.na_reasons) for k in SUBSCORES
        }
        score, missing_share, parts = combine(weights, subs)
        flags: list[str] = []
        explain: list[str] = []
        na = {m: r for sub in subs.values() for m, r in sub.missing.items()}

        history = str(ctx.extras.get("history_class", ctx.history_class))
        conf: Confidence = confidence_from_missing(missing_share, s.confidence.step_missing_weight)
        if score is None:
            conf = "Low"
        val_ok_share = (
            1 - subs["valuation"].missing_share if subs["valuation"].weight_total else 0.0
        )
        informational, why_info = False, ""
        months = ctx.extras.get("months_listed")
        if history == "H0":
            informational, why_info = (
                True,
                (
                    f"listed {months:.0f} months; own-history valuation needs 24+"
                    if months is not None
                    else "under 24 months listed"
                ),
            )
            conf = "Low"
        elif history == "H1":
            conf = cap_at(conf, "Med")
            flags.append(
                "history 24–59 months: own-history bands partial; confidence capped at Med"
            )
        if spec.informational:
            informational, why_info = (
                True,
                f"{profile.replace('_', ' ')} profile: earnings-based valuation does not apply",
            )
            conf = "Low"
        if val_ok_share < s.informational_min_valuation_weight and not informational:
            informational, why_info = (
                True,
                f"only {val_ok_share:.0%} of the valuation weight is computable",
            )
            conf = cap_at(conf, "Low")
        if informational:
            flags.append(f"limited history: value lens informational ({why_info})")
        floor = s.cap_settings[cap].min_traded_value_cr  # type: ignore[index]
        traded = ctx.extras.get("avg_traded_value_cr")
        if floor and traded is not None and traded < floor:
            flags.append(f"illiquid: ₹{traded:.1f} Cr a day below the ₹{floor:g} Cr floor")
            conf = cap_at(conf, "Med")

        vetoes = self._vetoes(ctx, s)
        unknown = [dict(x) for x in ctx.extras.get("unknown_checks", [])]
        checks: list[dict[str, Any]] = []
        for rid, name, res in (
            ("RULE.value.pledge_cap", "promoter pledge within the cap", pledge_cap(ctx, s)),
            ("RULE.value.negative_cfo", "operating cash flow", negative_cfo(ctx, s)),
            ("RULE.value.nnpa_cap", "net NPA within the cap", nnpa_cap(ctx, s)),
        ):
            if res is None:
                unknown.append({"check": rid, "reason": "its input is missing"})
                checks.append(
                    {"id": rid, "name": name, "state": "UNKNOWN", "detail": "its input is missing"}
                )
            else:
                checks.append(
                    {"id": rid, "name": name, "state": "FLAGGED" if res else "CLEAN", "detail": ""}
                )
        self._flags(ctx, s, flags)

        intrinsic = self._intrinsic(ctx, s, cap)
        price = ctx.extras.get("price")
        mos, required = intrinsic.get("margin_of_safety"), intrinsic.get("mos_required")
        high = intrinsic.get("high")

        view = "UNKNOWN"
        if score is not None:
            if vetoes:
                view = "AVOID"
            elif score < s.views.fair_score or (
                price and high and price > high * (1 + s.views.overvalued_above_high)
            ):
                view = "OVERVALUED"
            elif score >= s.views.undervalued_score:
                if mos is not None and required is not None and mos >= required:
                    view = "UNDERVALUED"
                else:
                    view = "QUALITY_FAIRLY_PRICED"
                    if mos is None:
                        explain.append("margin of safety unavailable: held at fairly priced")
            else:
                view = "FAIR"
        if vetoes:
            explain.append("veto: " + ", ".join(vetoes))
        top = sorted(parts.items(), key=lambda kv: -kv[1])[:2]
        if top and score is not None:
            explain.append("strongest: " + ", ".join(f"{k} {v:.0f}" for k, v in top))
        trap = self._value_trap(ctx, s, mos)
        if trap:
            flags.append(trap)

        details = {
            "profile": profile,
            "history_class": history,
            "archetype": ctx.extras.get("archetype"),
            "weights": weights,
            "subscore_missing": {k: v.missing for k, v in subs.items() if v.missing},
            "metrics": self._metric_rows(ctx, subs),
            "intrinsic_value": intrinsic,
            "implied_growth_reverse_dcf": ctx.extras.get("intrinsic", {}).get(
                "implied_growth_reverse_dcf"
            ),
            "delivered_growth": ctx.extras.get("intrinsic", {}).get("delivered_growth"),
            "expected_irr": ctx.extras.get("intrinsic", {}).get("expected_irr"),
            "margin_of_safety": mos,
            "mos_required": required,
            "informational_reason": why_info or None,
            "unknown_checks": unknown,
            "checks": checks,
            "asof": ctx.extras.get("asof", {}),
            "history_break": ctx.extras.get("history_break"),
            "value_view": view,
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
            signals=[],
            vetoes=vetoes,
            explanations=explain,
            flags=sorted(set(flags)),
            na=na,
            details=details,
        )

    @staticmethod
    def _vetoes(ctx: StockContext, s: ValueConfig) -> list[str]:
        out = []
        if pledge_cap(ctx, s):
            out.append("RULE.value.pledge_cap")
        if negative_cfo(ctx, s) and ctx.profile not in ("bank", "nbfc", "insurance"):
            out.append("RULE.value.negative_cfo")
        if nnpa_cap(ctx, s):
            out.append("RULE.value.nnpa_cap")
        return out

    @staticmethod
    def _flags(ctx: StockContext, s: ValueConfig, flags: list[str]) -> None:
        m, f = ctx.metrics, s.flags
        fin = ctx.profile in ("bank", "nbfc", "insurance", "capital_market_intermediary")
        if (
            (x := m.get(V + "other_income_share")) is not None
            and x > f["other_income_share"]
            and not fin
        ):
            flags.append(f"other income is {x:.0%} of PBT (above {f['other_income_share']:.0%})")
        if (x := m.get(V + "debtor_days_change")) is not None and x > f["debtor_days_rise"]:
            flags.append(f"debtor days up {x:.0%} year on year")
        if (x := m.get(V + "dilution_3y")) is not None and x > f["dilution_3y"]:
            flags.append(f"share count growing {x:.1%} a year")
        if (x := m.get(V + "eps_vs_revenue_gap")) is not None and x > f["eps_vs_revenue_gap"]:
            flags.append("EPS growing well ahead of revenue: margin expansion may not last")
        if (x := m.get(V + "lease_adj_leverage")) is not None and x > f["lease_leverage"]:
            flags.append(
                f"lease-adjusted leverage {x:.1f}× EBITDAR (above {f['lease_leverage']:g}×)"
            )
        if (x := m.get(V + "net_cash_to_mcap")) is not None and x > f["net_cash_to_mcap_high"]:
            flags.append(f"net cash is {x:.0%} of market cap: check payout policy")
        if (x := m.get(V + "promoter_trend_pp")) is not None and x <= f["promoter_drop_pp"]:
            flags.append(f"promoter holding down {abs(x):.1f} points in a year")
        if (x := m.get(V + "pe_percentile_10y")) is not None and x >= f[
            "pe_percentile_fully_valued"
        ]:
            flags.append("P/E above the 90th percentile of its own history: fully valued")
        if (x := m.get(V + "pledge_pct")) is not None and x > 0:
            flags.append(f"promoter pledge {x:.1%} of holding")
        n, years = ctx.extras.get("cfo_negative_years"), ctx.extras.get("cfo_years", 0)
        if ctx.profile == "new_age" and n and n >= s.vetoes.negative_cfo_years_of_5 and years >= 5:
            flags.append(
                f"negative operating cash flow in {n} of {years} years (flag while runway ≥ {s.vetoes.runway_months_min:g} months)"
            )
        ig, dg = (
            ctx.extras.get("intrinsic", {}).get("implied_growth_reverse_dcf"),
            ctx.extras.get("intrinsic", {}).get("delivered_growth"),
        )
        if ig is not None and dg is not None and ig > dg + 0.05:
            flags.append(f"price assumes {ig:.0%} growth against {dg:.0%} delivered")

    @staticmethod
    def _intrinsic(ctx: StockContext, s: ValueConfig, cap: str) -> dict[str, Any]:
        block = dict(ctx.extras.get("intrinsic", {}))
        price = ctx.extras.get("price")
        required = s.cap_settings[cap].required_mos  # type: ignore[index]
        uplift = mos_uplift_pp(ctx.extras.get("index_pe_percentile"), default_regime()) / 100
        block["mos_required"] = required + uplift
        if uplift:
            block["mos_uplift"] = uplift
        mid = block.get("mid")
        if price and mid:
            block["margin_of_safety"] = (mid - price) / mid
        return block

    @staticmethod
    def _value_trap(ctx: StockContext, s: ValueConfig, mos: float | None) -> str | None:
        m, f = ctx.metrics, s.flags
        cheap = (m.get(V + "pe_discount_own_5y") or -1) >= f["cheap_pe_discount"] or (
            mos is not None and mos > 0
        )
        if not cheap:
            return None
        signs = []
        if (x := m.get(V + "roce_trend_pp")) is not None and x < 0:
            signs.append("ROCE falling")
        if (x := m.get(V + "op_margin_trend_pp")) is not None and x < 0:
            signs.append("margins falling")
        if (x := m.get(V + "promoter_trend_pp")) is not None and x < 0:
            signs.append("promoter selling")
        if (x := ctx.extras.get("excess_return_12m")) is not None and x < 0:
            signs.append("negative 12-month relative strength")
        if (x := m.get(V + "debtor_days_change")) is not None and x > f["debtor_days_rise"]:
            signs.append("debtor days rising")
        if len(signs) >= f["value_trap_min_signs"]:
            return "value-trap risk: cheap, but " + ", ".join(signs)
        return None

    @staticmethod
    def _metric_rows(ctx: StockContext, subs: dict[str, SubScore]) -> dict[str, dict[str, Any]]:
        """Each scored metric with its source family and as-of date (AC-F04.6)."""
        asof = ctx.extras.get("asof", {})
        rows: dict[str, dict[str, Any]] = {}
        for sub in subs.values():
            for mid in sub.used:
                spec = REGISTRY.metrics.get(mid)
                inputs = spec.inputs if spec else []
                if any(i.startswith("shareholding") for i in inputs):
                    src, when = "nse_shareholding", asof.get("shareholding")
                elif any(i.startswith("profile_inputs") for i in inputs):
                    src, when = "profile_inputs", None
                elif any(i.startswith("fundamentals") for i in inputs):
                    src, when = (
                        "screener_export",
                        asof.get("fundamentals_quarter") or asof.get("fundamentals_annual"),
                    )
                else:
                    src, when = "derived", asof.get("price")
                if any(i.startswith("prices") for i in inputs) and src == "screener_export":
                    src = "screener_export+prices"
                rows[mid] = {"value": ctx.metrics.get(mid), "source": src, "asof": when}
        return rows
