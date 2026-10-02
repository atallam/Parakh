"""A synthetic pilot: every pilot stock with prices, fundamentals, shareholding and benchmarks."""

from __future__ import annotations

import datetime as dt

from parakh.configs import ConfigBundle
from parakh.orchestration.analysis_data import InMemoryData
from tests.helpers import fundamentals as F
from tests.helpers.prices import make_index, make_prices

END = dt.date(2026, 9, 30)


def pilot_data(
    bundle: ConfigBundle, end: dt.date = END, sessions: int = 900, drift: float = 0.0006
) -> InMemoryData:
    d = InMemoryData()
    for i, s in enumerate(bundle.universe.pilot):
        px = make_prices(sessions, end=end, isin=s.isin, seed=i + 1, drift=drift)
        d.price_frames[s.isin] = px
        d.fundamental_rows[s.isin] = F.rows(isin=s.isin)
        d.shareholding_rows[s.isin] = F.shareholding(s.isin)
        for c in bundle.momentum.cap_settings.values():
            d.indices[c.benchmark] = make_index(px)
    return d
