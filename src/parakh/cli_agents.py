"""`parakh concalls fetch` and `parakh agents eval`: the manual path to the priced eval (plan 14 §4.6).

Both are for you at a keyboard: fetch caches the latest filed concall transcript per stock; eval runs
the Qualitative (and, if a snapshot exists, Devil's-advocate) agent on real documents with the real
model, prints what came back and what it cost, and writes the result to logs/agents_shadow.md.
Nothing here writes a snapshot or a watchlist proposal.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
from pathlib import Path

from parakh.configs import ConfigBundle


def _pick(bundle: ConfigBundle, symbols: list[str] | None):  # type: ignore[no-untyped-def]
    secs = [s for s in bundle.universe.active if not symbols or s.symbol in symbols]
    if not secs:
        print(f"no stock in the active universe matches {symbols}", file=sys.stderr)
    return secs


def concalls_fetch(symbols: list[str] | None) -> int:
    """Fetch and cache the latest valid concall transcript for each stock (needs the network)."""
    from parakh.adapters.concalls import ScreenerConcallsProvider
    from parakh.configs import load_all
    from parakh.orchestration.refresh import fetch_transcript
    from parakh.services.documents import TranscriptStore

    bundle = load_all()
    secs = _pick(bundle, symbols)
    if not secs:
        return 2
    provider, store, today = ScreenerConcallsProvider(), TranscriptStore(), dt.date.today()
    failed = 0
    for s in secs:
        doc = fetch_transcript(provider, store, isin=s.isin, symbol=s.symbol, today=today)
        if doc is None:
            failed += 1
            print(f"{s.symbol:12} no valid transcript")
        else:
            print(f"{s.symbol:12} {doc.period} · {doc.pages} pages · {len(doc.text):,} characters")
    return 0 if not failed else 1


def _unverified(overlay, text, check) -> int:  # type: ignore[no-untyped-def]
    """Count quotes in the stored overlay that are not in the document."""
    from parakh.agents.qualitative import QualOutput

    try:
        out = QualOutput.model_validate(
            {k: v for k, v in overlay.items() if k in QualOutput.model_fields}
        )
    except Exception:  # noqa: BLE001  (an overlay we cannot read counts as nothing to verify)
        return 0
    return len(check(out, text))


def _tokens(sink, run_id: str) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    from parakh.audit.events import AUD

    tin = tout = runs = 0
    for e in sink.events_for_run(run_id):
        if e.event_type == AUD.AGENT_END:
            runs += 1
            tin += int(e.details.get("tokens_in", 0))
            tout += int(e.details.get("tokens_out", 0))
    return runs, tin, tout


def agents_eval(symbols: list[str] | None, devils_advocate: bool) -> int:
    """Run the agents once per stock on real documents; print status, quotes and token cost."""
    from parakh.agents.devils_advocate import run_devils_advocate
    from parakh.agents.qualitative import run_qualitative, unverified_quotes
    from parakh.agents.runtime.factory import build_runner
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.configs import load_all
    from parakh.notify.log import ShadowLog
    from parakh.services.documents import TranscriptStore
    from parakh.snapshots.store import load_previous, periods_for, read_snapshot_dict, snapshot_path
    from parakh.watch.state import StateStore

    bundle = load_all()
    runner = build_runner(bundle)
    if runner is None:
        print(
            "no agent runner: set ANTHROPIC_API_KEY in your .env and run `uv sync --extra agents`",
            file=sys.stderr,
        )
        return 2
    secs = _pick(bundle, symbols)
    if not secs:
        return 2
    sink, store, docs = get_sink(), StateStore(), TranscriptStore()
    ctx = RunContext.create(mode="agent-eval", actor_type="user", actor_id="agents-eval")
    shadow = ShadowLog("agents_shadow.md")
    for s in secs:
        lines: list[str] = []
        doc = docs.get(s.isin)
        # a fresh cache key per eval: the eval must spend tokens, never replay an old answer
        q = run_qualitative(
            runner, bundle, ctx, sink, isin=s.isin, symbol=s.symbol, doc=doc,
            previous=docs.get(s.isin, previous=True), store=StateStore(store.root / "eval"),
    sink, docs = get_sink(), TranscriptStore()
    ctx = RunContext.create(mode="agent-eval", actor_type="user", actor_id="agents-eval")
    shadow = ShadowLog("agents_shadow.md")
    # a throw-away cache: the eval must spend tokens every time, never replay an earlier answer
    scratch = tempfile.mkdtemp(prefix="parakh-eval-")
    for s in secs:
        lines: list[str] = []
        doc = docs.get(s.isin)
        # throw-away cache (scratch): never replay an old answer
        q = run_qualitative(
            runner, bundle, ctx, sink, isin=s.isin, symbol=s.symbol, doc=doc,
            previous=docs.get(s.isin, previous=True), store=StateStore(Path(scratch)),
        )  # fmt: skip
        line = f"{s.symbol:12} qualitative {q.status}"
        if q.reason:
            line += f" ({q.reason})"
        if doc is not None and q.status in ("ok", "cached"):
            bad = _unverified(q.overlay, doc.text, unverified_quotes)
            line += f" · {len(q.flags)} thesis flag(s) · unverified quotes {bad}"
        print(line)
        lines.append(line.strip())
        if q.overlay.get("summary"):
            lines.append(f"summary: {q.overlay['summary']}")
        if devils_advocate:
            periods = periods_for(s.cap, s.symbol)
            snap = (
                read_snapshot_dict(snapshot_path(s.cap, s.symbol, periods[-1])) if periods else None
            )
            if snap is None:
                print(f"{'':12} devil's advocate: no snapshot yet")
            else:
                prev = load_previous(s.cap, s.symbol, snap["period"])
                da = run_devils_advocate(runner, bundle, ctx, sink, snap=snap, previous=prev)
                print(
                    f"{'':12} devil's advocate {da.status}"
                    + (f" ({da.reason})" if da.reason else "")
                )
                lines.append(f"devil's advocate {da.status} {da.reason}".strip())
        shadow.append(
            when=dt.datetime.now(dt.UTC), heading=f"agents eval {s.symbol}", lines=lines,
            alert_ids=[ctx.run_id],
        )  # fmt: skip
    runs, tin, tout = _tokens(sink, ctx.run_id)
    print(f"\n{runs} agent run(s) · {tin:,} tokens in · {tout:,} tokens out · run {ctx.run_id}")
    print(f"results are in {shadow.path}")
    return 0
