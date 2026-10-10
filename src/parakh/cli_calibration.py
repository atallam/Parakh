"""Phase 5 commands: calibration reports, governance checks and the decision journal.

parakh calibrate membership-import FILE      merge historical index constituents (CSV)
parakh calibrate panel [--years 10]          score every month-end into the cached panel
parakh calibrate report [--quarter 2026-Q4]  backtest, outcomes, quintiles, alerts, scorecard, journal
parakh calibrate drift | replay | restore-test
parakh journal add|list|due|review
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

from parakh.config import REPO_ROOT, state_dir

PANEL_FILE = "panel.parquet"
MEMBERSHIP_FILE = "membership_history.csv"


def calibration_dir() -> Path:
    return state_dir() / "calibration"


def _today() -> dt.date:
    from parakh.cli_watch import today_ist

    return today_ist()


def _load_inputs(bundle: Any, store_kind: str, years: int, asof: dt.date) -> Any:
    """Read prices, benchmarks, membership, alerts, watchlist and journal into `CalibrationInputs`."""
    from parakh.calibration.journal import JournalStore
    from parakh.calibration.membership import Membership
    from parakh.cli_analysis import _data
    from parakh.notify.log import AlertsLog
    from parakh.services.calibration import CalibrationInputs
    from parakh.watch.state import StateStore
    from parakh.watchlist.repository import open_repository

    data = _data(store_kind, bundle)
    if data is None:
        return None
    start = dt.date(asof.year - years, 1, 1)
    secs = bundle.universe.active
    prices = {s.isin: data.prices(s.isin, start, asof) for s in secs}
    benches = {
        cap: b
        for cap, cs in bundle.momentum.cap_settings.items()
        if (b := data.index_close(cs.benchmark, asof)) is not None
    }
    path = calibration_dir() / MEMBERSHIP_FILE
    store = StateStore()
    first_buys: dict[str, dt.date] = {}
    for lot in data.open_lots():
        first_buys[lot.isin] = min(lot.trade_date, first_buys.get(lot.isin, lot.trade_date))
    return CalibrationInputs(
        securities=secs,
        prices=prices,
        benches=benches,
        wide_bench=data.index_close(bundle.calibration.backtest.benchmark, asof),
        membership=Membership.from_csv(path) if path.exists() else None,
        alert_rows=AlertsLog(store.root / "alerts").rows(),
        watchlist=open_repository(store).load(),
        journal=JournalStore(store).all(),
        first_buys=first_buys,
        start=start,
        asof=asof,
    )


def membership_import(file: str) -> int:
    from parakh.calibration.membership import import_csv

    target = calibration_dir() / MEMBERSHIP_FILE
    try:
        n = import_csv(Path(file), target)
    except (ValueError, OSError, KeyError) as exc:
        print(f"cannot import {file}: {exc}", file=sys.stderr)
        return 2
    print(f"{n} membership rows now in {target}")
    return 0


def _panel(bundle: Any, inputs: Any, *, rebuild: bool = False) -> Any:
    from parakh.calibration.panel import load_panel, save_panel
    from parakh.services.calibration import compute_panel

    path = calibration_dir() / PANEL_FILE
    existing = None if rebuild else load_panel(path)
    panel = compute_panel(
        bundle, inputs, existing=existing, on_progress=lambda m: print(m, flush=True)
    )
    save_panel(panel, path)
    return panel


def panel(store: str, years: int, rebuild: bool) -> int:
    from parakh.configs import load_all

    bundle = load_all()
    inputs = _load_inputs(bundle, store, years, _today())
    if inputs is None:
        return 2
    p = _panel(bundle, inputs, rebuild=rebuild)
    print(f"{len(p)} scored stock-months in {calibration_dir() / PANEL_FILE}")
    return 0


def report(store: str, years: int, quarter: str | None, allow_proxy: bool, write: bool) -> int:
    from parakh import __version__
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.calibration.report import build_report, quarter_of, review_template
    from parakh.configs import load_all
    from parakh.services.calibration import compute_parts

    bundle = load_all()
    today = _today()
    inputs = _load_inputs(bundle, store, years, today)
    if inputs is None:
        return 2
    p = _panel(bundle, inputs)
    parts = compute_parts(bundle, inputs, p, allow_proxy=allow_proxy)
    q = quarter or quarter_of(today)
    rep = build_report(
        quarter=q, cfg=bundle.calibration, framework_version=__version__, parts=parts, today=today
    )
    print(rep.to_markdown())
    if write:
        out = REPO_ROOT / "docs" / "calibration"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{q}.md").write_text(rep.to_markdown(), encoding="utf-8")
        (out / f"{q}.json").write_text(rep.to_json(), encoding="utf-8")
        gov = REPO_ROOT / "governance" / "reviews"
        gov.mkdir(parents=True, exist_ok=True)
        if not (gov / f"{q}.md").exists():  # never overwrite a review someone has filled in
            (gov / f"{q}.md").write_text(
                review_template(rep, bundle.calibration.restore.max_backup_age_days),
                encoding="utf-8",
            )
        ctx = RunContext.create(mode="calibration", actor_type="user")
        get_sink().emit(
            ctx, AUD.CALIBRATION_REPORT, entity_type="report", entity_id=q,
            details={"overall": rep.overall, "framework": __version__},
        )  # fmt: skip
        print(f"\nwritten to {out / (q + '.md')}", file=sys.stderr)
    return 0


def drift(output: str | None, period: str | None) -> int:
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.config import output_dir
    from parakh.configs import load_all
    from parakh.governance.drift import drift_report
    from parakh.services.calibration import snapshot_rows

    bundle = load_all()
    rows = snapshot_rows(Path(output) if output else output_dir())
    if rows.empty:
        print("no snapshots found; run `parakh monthly` first", file=sys.stderr)
        return 2
    rep = drift_report(rows, bundle.calibration.drift, period=period)
    for c in rep.checks:
        print(f"{c.status:>18}  {c.name}  {c.value if c.value is not None else ''}  {c.detail}")
    print(f"drift {rep.period}: {rep.status}")
    get_sink().emit(
        RunContext.create(mode="drift", actor_type="ci", actor_id="drift-check"),
        AUD.DRIFT_CHECKED, entity_type="drift", entity_id=rep.period, details={"status": rep.status},
    )  # fmt: skip
    return 1 if rep.status == "alert" else 0


def replay_check(store: str, asof: str | None, output: str | None) -> int:
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.cli_analysis import _data, month_end
    from parakh.config import output_dir
    from parakh.configs import load_all
    from parakh.governance.replay import replay_month

    bundle = load_all()
    data = _data(store, bundle)
    if data is None:
        return 2
    when = dt.date.fromisoformat(asof) if asof else month_end(_today())
    rep = replay_month(bundle, data, when, Path(output) if output else output_dir())
    print(f"replay {rep.period}: {rep.status} · {rep.matched} of {rep.stocks} stocks identical")
    for d in rep.diffs:
        print(f"  {d.symbol}: {d.status}: " + "; ".join(d.differences))
    get_sink().emit(
        RunContext.create(mode="replay", actor_type="ci", actor_id="replay-check"),
        AUD.REPLAY_CHECKED, entity_type="replay", entity_id=rep.period,
        details={"status": rep.status, "stocks": rep.stocks, "matched": rep.matched},
    )  # fmt: skip
    return 0 if rep.status == "pass" else 1


def restore_check() -> int:
    from parakh.cli import _supabase_repo
    from parakh.configs import load_all
    from parakh.governance.restore_test import run_restore_test
    from parakh.secrets import get_secret
    from parakh.storage.prices import SupabaseBlobs

    identity = get_secret("BACKUP_AGE_IDENTITY")
    if not identity:
        print(
            "BACKUP_AGE_IDENTITY is not set; the restore test needs the private key",
            file=sys.stderr,
        )
        return 2
    repo = _supabase_repo()
    if repo is None:
        return 2
    _, res = run_restore_test(
        load_all(), SupabaseBlobs(repo.client, "backups"), identity, now=dt.datetime.now(dt.UTC)
    )
    print(
        f"restore test: {res.status} · {res.backup} · {res.tables} tables · {res.manifest_rows} rows"
    )
    print(
        "(archive decrypted and every table matched its manifest hash; no scratch database was loaded)"
    )
    for p in res.problems:
        print(f"  ! {p}", file=sys.stderr)
    return 0 if res.status == "pass" else 1


# -- journal --------------------------------------------------------------------------------------
def journal(action: str, args: list[str], reason: str | None, expected: str | None,
            when: str | None, verdict: str | None, note: str | None, kind: str | None) -> int:  # fmt: skip
    from parakh.audit.context import RunContext
    from parakh.calibration.journal import JournalError, JournalStore
    from parakh.configs import load_all
    from parakh.services.journal import JournalService

    svc = JournalService(JournalStore(), load_all(), RunContext.create(mode="journal"))
    today = _today()
    try:
        if action == "add":
            if not args or not kind or not reason or not expected:
                print(
                    "usage: parakh journal add SYMBOL --action buy --reason … --expected …",
                    file=sys.stderr,
                )
                return 2
            e = svc.add(
                args[0], action=kind, reason=reason, expected=expected, today=today,
                review_on=dt.date.fromisoformat(when) if when else None,
            )  # fmt: skip
            print(f"{e.entry_id} · {e.symbol} {e.action} · review on {e.review_on}")
        elif action == "review":
            if not args or not verdict:
                print(
                    "usage: parakh journal review ENTRY_ID --verdict right|wrong|mixed|too_early [--note …]",
                    file=sys.stderr,
                )
                return 2
            e = svc.review(args[0], verdict=verdict, note=note or "", today=today)
            print(f"{e.entry_id} reviewed: {e.verdict}")
        else:
            rows = svc.due(today) if action == "due" else svc.entries()
            for e in rows:
                print(
                    f"{e.entry_id}  {e.status:<8} {e.symbol:<10} {e.action:<5} review {e.review_on}  {e.reason}"
                )
            if not rows:
                print("nothing due" if action == "due" else "no journal entries yet")
    except JournalError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
