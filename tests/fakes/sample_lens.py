"""A tiny lens used only by the contract-test harness until the real lenses land (Phase 2)."""

from __future__ import annotations

from parakh.lenses.base import Lens, LensConfig, LensResult, StockContext

GOOD_DOC = """Test metric.

Formula:   x
Meaning:   y
Pitfalls:  z
Source:    tests
"""

SAMPLE_METRIC = "MET.sample.earnings_yield"


class SampleLens(Lens):
    lens_version = "0.0.1"
    required_metrics = [SAMPLE_METRIC]
    applicable_profiles = []

    def evaluate(self, ctx: StockContext, cfg: LensConfig) -> LensResult:
        value = ctx.metrics.get(SAMPLE_METRIC)
        if value is None:
            return LensResult(
                lens_id=self.lens_id,
                lens_version=self.lens_version,
                score=None,
                view="UNKNOWN",
                confidence="Low",
                metrics_used=[SAMPLE_METRIC],
                explanations=["earnings yield unavailable"],
            )
        sub = max(0.0, min(1.0, value / 0.1))
        return LensResult(
            lens_id=self.lens_id,
            lens_version=self.lens_version,
            score=round(sub * 100, 1),
            subscores={"yield": sub},
            view="CHEAP" if sub > 0.6 else "FAIR",
            confidence="Med",
            metrics_used=[SAMPLE_METRIC],
        )
