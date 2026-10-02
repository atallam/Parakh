"""Phase 2 commands: monthly run, show, explain, share, thesis, override, indices, models."""

from __future__ import annotations

import datetime as dt
import json
import sys

from parakh.config import state_dir


def _data(store_kind: str, bundle):  # type: ignore[no-untyped-def]
    from parakh.cli import _supabase_repo
    from parakh.orchestration.analysis_data import SupabaseData
    from parakh.storage.prices import LocalBlobs, ParquetPriceStore, SupabaseBlobs

    repo = _supabase_repo()
    if repo is None:
        return None
    blobs = (
        SupabaseBlobs(repo.client)
        if store_kind == "supabase"
        else LocalBlobs(state_dir() / "prices")
    )
    return SupabaseData(repo, ParquetPriceStore(blobs, state_dir() / "cache" / "prices"))


def month_end(today: dt.date | None = None) -> dt.date:
    """The latest completed month-end: today if it is the last day of its month, else the previous one."""
    t = today or dt.date.today()
    tomorrow = t + dt.timedelta(days=1)
    return t if tomorrow.day == 1 else t.replace(day=1) - dt.timedelta(days=1)


def monthly(asof: str | None, symbols: list[str] | None, store_kind: str = "supabase") -> int:
    from parakh.configs import load_all
    from parakh.orchestration.analysis import run_monthly
    from parakh.orchestration.render_outputs import render_month

    bundle = load_all()
    when = dt.date.fromisoformat(asof) if asof else month_end()
    secs = [s for s in bundle.universe.pilot if not symbols or s.symbol in symbols]
    if not secs:
        print(f"no pilot stock matches {symbols}", file=sys.stderr)
        return 2
    data = _data(store_kind, bundle)
    if data is None:
        return 2
    res = run_monthly(bundle, data, when, securities=secs)
    snaps = [s.snapshot.model_dump(mode="json") for s in res.stocks if s.snapshot]
    files = render_month(bundle, snaps)
    print(f"run {res.ctx.run_id} · {res.outcome.status} · as of {when}")
    print(f"{'SYMBOL':11} {'VERDICT':28} {'CONF':5} {'VALUE':>5} {'MOM':>5}  NOTE")
    from parakh.services.reports import chip

    for s in res.stocks:
        if s.snapshot is None:
            print(f"{s.symbol:11} FAILED: {s.error}")
            continue
        if s.error:
            print(f"{s.symbol:11} WARNING (snapshot written, a later step failed): {s.error}")
        sn = s.snapshot
        v = sn.verdict
        note = v.get("label") or ("; ".join(v.get("vetoes", [])) or "")
        val = "N/A" if sn.value["score"] is None else f"{sn.value['score']:.0f}"
        mom = "N/A" if sn.momentum["score"] is None else f"{sn.momentum['score']:.0f}"
        print(f"{s.symbol:11} {chip(v)[:28]:28} {v['confidence']:5} {val:>5} {mom:>5}  {note}")
    print(f"{len(files)} files written under {res.output_root or 'the output folder'}")
    return 0 if not any(s.error for s in res.stocks) else 1


def _find(symbol: str, period: str | None):  # type: ignore[no-untyped-def]
    from parakh.configs import load_all
    from parakh.snapshots.store import periods_for, read_snapshot_dict, snapshot_path

    bundle = load_all()
    sec = next((s for s in bundle.universe.pilot if s.symbol.upper() == symbol.upper()), None)
    if sec is None:
        print(f"{symbol} is not in the pilot universe", file=sys.stderr)
        return None
    periods = periods_for(sec.cap, sec.symbol)
    if not periods:
        print(
            f"no snapshots for {sec.symbol}; run `parakh run --mode monthly` first", file=sys.stderr
        )
        return None
    p = period or periods[-1]
    snap = read_snapshot_dict(snapshot_path(sec.cap, sec.symbol, p))
    if snap is None:
        print(f"no snapshot for {sec.symbol} {p}; have {', '.join(periods)}", file=sys.stderr)
        return None
    prev_p = max((x for x in periods if x < p), default=None)
    prev = read_snapshot_dict(snapshot_path(sec.cap, sec.symbol, prev_p)) if prev_p else None
    return bundle, snap, prev


def show(symbol: str, period: str | None) -> int:
    found = _find(symbol, period)
    if not found:
        return 2
    _, snap, prev = found
    from parakh.services.reports import stock_view

    v = stock_view(snap, prev)
    print(v["tldr"])
    print(v["chip"])
    print(v["position_line"])
    print("What changed:")
    for b in v["what_changed"]:
        print(f"  - {b}")
    return 0


def explain(symbol: str, period: str | None, as_json: bool) -> int:
    found = _find(symbol, period)
    if not found:
        return 2
    _, snap, prev = found
    from parakh.services.explain import explain_verdict, render_tree

    tree = explain_verdict(snap, prev)
    print(json.dumps(tree, indent=2, ensure_ascii=False) if as_json else render_tree(tree))
    return 0


def share(symbol: str, period: str | None) -> int:
    found = _find(symbol, period)
    if not found:
        return 2
    _, snap, _ = found
    from parakh.render.share import share_card, share_markdown
    from parakh.snapshots.store import stock_dir

    folder = stock_dir(snap["cap"], snap["symbol"]) / "share"
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / f"{snap['period']}.md"
    md.write_text(share_markdown(snap), encoding="utf-8")
    png = share_card(snap, folder / f"{snap['period']}.png")
    print(f"share export (no position data, with disclaimer):\n  {md}\n  {png}")
    return 0


def thesis(action: str, symbol: str | None) -> int:
    from parakh.configs import load_all
    from parakh.registry import REGISTRY, discover
    from parakh.snapshots.store import stock_dir
    from parakh.thesis.model import read_thesis
    from parakh.thesis.status import validate_rules, variable_names

    discover()
    names = variable_names(REGISTRY.metrics.keys())
    if action == "variables":
        for n, mid in sorted(names.items()):
            print(f"{n:32} {mid}")
        return 0
    bundle = load_all()
    secs = [s for s in bundle.universe.pilot if not symbol or s.symbol.upper() == symbol.upper()]
    bad = 0
    for s in secs:
        parsed = read_thesis(stock_dir(s.cap, s.symbol) / "THESIS.md")
        if not parsed.exists:
            print(f"{s.symbol:11} NOT SET (no THESIS.md)")
            continue
        errs = list(parsed.errors) + (validate_rules(parsed, names) if parsed.front else [])
        if errs:
            bad += 1
            print(f"{s.symbol:11} INVALID")
            for e in errs:
                print(f"    - {e}")
        else:
            print(
                f"{s.symbol:11} valid · {len(parsed.front.breakers)} breakers · review by {parsed.front.review_by or 'not set'}"
            )
    return 1 if bad else 0


def override_add(isin: str, fld: str, value: str, reason: str, days: int) -> int:
    """Appends an override to config/overrides.yaml after validating it (reason ≥ 10 chars, ≤ 366 days)."""
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.config import config_dir
    from parakh.configs import load_all
    from parakh.configs.lens_models import Override

    path = config_dir() / "overrides.yaml"
    before = path.read_text(encoding="utf-8")
    today = dt.date.today()
    n = sum(1 for line in before.splitlines() if line.startswith("  - id:")) + 1
    entry = {
        "id": f"OV-{today:%Y}-{n:03d}",
        "isin": isin,
        "field": fld,
        "value": value,
        "reason": reason,
        "set_on": today,
        "expires_on": today + dt.timedelta(days=days),
    }
    try:
        Override.model_validate(entry)
    except Exception as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 2
    block = (
        f"  - id: {entry['id']}\n    isin: {isin}\n    field: {fld}\n    value: {json.dumps(value)}\n"
        f"    reason: {json.dumps(reason, ensure_ascii=False)}\n    set_on: {entry['set_on']}\n    expires_on: {entry['expires_on']}\n"
    )
    text = (
        before.replace("overrides: []\n", "overrides:\n" + block, 1)
        if "overrides: []\n" in before
        else before.rstrip("\n") + "\n" + block
    )
    path.write_text(text, encoding="utf-8")
    try:
        load_all()
    except Exception as exc:
        path.write_text(before, encoding="utf-8")
        print(f"rejected: {exc}", file=sys.stderr)
        return 2
    ctx = RunContext.create(mode="override")
    get_sink().emit(
        ctx, AUD.OVERRIDE_SET, isin=isin, reason=reason, after={k: str(v) for k, v in entry.items()}
    )
    print(f"{entry['id']}: {fld}={value} for {isin} until {entry['expires_on']}")
    return 0


def indices_load(store_kind: str) -> int:
    from parakh.configs import load_all
    from parakh.orchestration.indices import load_indices
    from parakh.storage.prices import LocalBlobs, ParquetPriceStore, SupabaseBlobs

    bundle = load_all()
    if store_kind == "supabase":
        from parakh.cli import _supabase_repo

        repo = _supabase_repo()
        if repo is None:
            return 2
        blobs = SupabaseBlobs(repo.client)
        blobs.ensure_bucket()
    else:
        blobs = LocalBlobs(state_dir() / "prices")
    store = ParquetPriceStore(blobs, state_dir() / "cache" / "prices")
    ctx, outcome, rows = load_indices(bundle, store)
    print(f"run {ctx.run_id} · {outcome.status}")
    for name, n in rows.items():
        print(f"  {name:20} {n} rows")
    return 0


def models(check: bool) -> int:
    from parakh.governance.models import write_model_docs

    changed = write_model_docs(check=check)
    if check and changed:
        print("model inventory/cards are stale: " + ", ".join(changed), file=sys.stderr)
        return 1
    print("model inventory and cards " + ("are current" if check else "written"))
    return 0
