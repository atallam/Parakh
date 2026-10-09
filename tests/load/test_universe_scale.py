"""P5: a full-universe dry run with a mocked LLM, before the Phase 4 scale-up (plan 13 P5; NFR-07).

500 stocks (150 mid, 100 large, 250 small) go through the post-monthly step: devil's advocate and qualitative
agents on the FakeRunner, the watchlist review and the curator. The assertions are about the pipeline, not the
model: it finishes inside the run-time budget, every stock gets an overlay or an explicit "pending", the audit
chain stays valid, and a rate-limited model leaves "qualitative pending" instead of a guess.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import time

import pytest

from parakh.agents.qualitative import run_qualitative
from parakh.audit.context import RunContext
from parakh.audit.emit import get_sink
from parakh.configs import load_all
from parakh.mcp.middleware import Gateway
from parakh.orchestration import post_monthly as pm
from parakh.registry import discover
from parakh.services.documents import CachedDoc, TranscriptStore, sha256_text
from parakh.watch.state import StateStore
from tests.fakes.agent_runner import FakeRunner, Trajectory, Turn

TODAY = dt.date(2026, 12, 30)
SPLIT = {"mid": 150, "large": 100, "small": 250}
BUDGET_S = (
    120  # far below NFR-07's 20 minutes: the LLM is mocked, so what is left is our own overhead
)

PTS = [{"claim": f"c{i}", "evidence_metric": "pe", "evidence_value": "40"} for i in range(3)]


def isin_of(n: int) -> str:
    return f"INE{n:06d}01011"


@pytest.fixture
def universe(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("PARAKH_OUTPUT_DIR", str(out))
    monkeypatch.setenv("PARAKH_WATCH_STATE_DIR", str(tmp_path / "watch"))
    from parakh import config

    config.get_settings.cache_clear()
    snaps, n = [], 0
    for cap, count in SPLIT.items():
        for i in range(count):
            n += 1
            sym = f"{cap[:2].upper()}{i:03d}"
            snap = {
                "symbol": sym, "isin": isin_of(n), "cap": cap, "period": "2026-12", "name": sym,
                "verdict": {"verdict": "BUY" if i % 7 == 0 else "HOLD", "prev_verdict": "HOLD", "changed": i % 7 == 0, "confidence": "High"},
                "qualitative": {"status": "not_run"}, "history_class": "H0",
                "value": {"score": 40 + i % 50}, "momentum": {"score": 30 + i % 60},
            }  # fmt: skip
            folder = out / f"{cap}_cap" / sym / "snapshots"
            folder.mkdir(parents=True)
            (folder / "2026-12.json").write_text(json.dumps(snap), encoding="utf-8")
            snaps.append(snap)
    yield snaps
    config.get_settings.cache_clear()


def trajectories(snaps, ctx_run_id):
    out = {}
    for s in snaps:
        out[f"{ctx_run_id}.da.{s['isin']}"] = Trajectory(
            [Turn("mcp__parakh__reports_get_stock")],
            {"counter_points": PTS, "confidence_adjustment": 0},
        )
        out[f"{ctx_run_id}.qual.{s['isin']}"] = Trajectory(
            [Turn("mcp__parakh__data_get_document")],
            {"readable": True, "summary": "Steady quarter.", "guidance": [], "thesis_assessments": [], "tone_change": "SAME", "tone_reason": ""},
        )  # fmt: skip
    return out


@pytest.mark.load
def test_five_hundred_stocks_finish_inside_the_budget_with_a_valid_audit_chain(
    universe, tmp_path
) -> None:
    discover()
    bundle = load_all()
    flags = bundle.flags.model_copy(
        update={"qualitative": bundle.flags.qualitative.model_copy(update={"enabled": True})}
    )
    bundle = dataclasses.replace(
        bundle, flags=flags
    )  # the flag ships off until the first priced eval run
    ctx = RunContext.create(
        mode="post-monthly", asof=TODAY, actor_type="scheduler", actor_id="load"
    )
    docs = TranscriptStore(tmp_path / "docs")
    for s in universe[::2]:  # half of the universe has a transcript
        text = f"{s['symbol']} management sounded steady this quarter."
        docs.put(
            CachedDoc(
                isin=s["isin"],
                symbol=s["symbol"],
                period="2026-09",
                source_url="https://x",
                sha256=sha256_text(text),
                fetched_on="2026-12-01",
                pages=2,
                text=text,
            )
        )
    runner = FakeRunner(Gateway.for_client("agent:qualitative"), trajectories(universe, ctx.run_id))
    t0 = time.perf_counter()
    out = pm.post_monthly(
        bundle,
        runner,
        ctx,
        get_sink(),
        period="2026-12",
        today=TODAY,
        snaps=universe,
        store=StateStore(tmp_path / "watch"),
        transcripts=docs,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < BUDGET_S, f"{elapsed:.0f}s for 500 stocks"
    assert not out.errors
    assert sum(out.qualitative.values()) == 500 and sum(out.advocate.values()) == 500
    assert (
        out.qualitative.get("ok", 0) == 250 and out.qualitative.get("pending", 0) == 250
    )  # no transcript: explicit pending
    assert out.advocate.get("ok", 0) == sum(1 for s in universe if s["verdict"]["changed"])
    assert get_sink().verify_chain().ok
    assert out.llm_alert is None  # nothing misbehaved


class RateLimited:
    """An Anthropic 429 on every call: the SDK runner backs off, gives up, and raises."""

    calls = 0

    async def run(self, spec, task, ctx):  # type: ignore[no-untyped-def]
        type(self).calls += 1
        raise RuntimeError("429 rate_limit_error")


def test_a_rate_limited_model_leaves_qualitative_pending_not_a_guess(tmp_path) -> None:
    bundle = load_all()
    ctx = RunContext.create(mode="qualitative", actor_type="scheduler", actor_id="t")
    text = "Management sounded steady."
    doc = CachedDoc(
        isin=isin_of(1),
        symbol="X",
        period="2026-09",
        source_url="u",
        sha256=sha256_text(text),
        fetched_on="2026-12-01",
        pages=1,
        text=text,
    )
    res = run_qualitative(
        RateLimited(),
        bundle,
        ctx,
        get_sink(),
        isin=doc.isin,
        symbol="X",
        doc=doc,
        store=StateStore(tmp_path),
    )
    assert res.status == "pending" and "qualitative pending" in res.overlay["reason"]
    assert not StateStore(tmp_path).load("qualitative_cache")  # a failure is never cached
