"""`parakh watchlist …`: the same actions as the Streamlit page, from a terminal (plan 06 §5.2).

parakh watchlist pending
parakh watchlist approve 01JB… 01JC…
parakh watchlist reject 01JB… --reason "too cyclical"
parakh watchlist add TCS --reason "waiting for a dip" --target 3400
parakh watchlist list
parakh watchlist review                 # run the monthly review on the latest snapshots
"""

from __future__ import annotations

import datetime as dt
import sys

from parakh.audit.context import RunContext
from parakh.configs import load_all
from parakh.services.watchlist import WatchlistError, WatchlistService
from parakh.watchlist.repository import open_repository


def _service() -> WatchlistService:
    return WatchlistService(open_repository(), load_all(), RunContext.create(mode="watchlist-cli"))


def _today() -> dt.date:
    from parakh.cli_watch import today_ist

    return today_ist()


def _print_pending(svc: WatchlistService) -> None:
    rows = svc.pending()
    if not rows:
        print("Nothing pending.")
        return
    for s in rows:
        who = "🤖 " if s.is_agent else ""
        print(f"{s.sugg_id[:10]}  {s.symbol:11} {s.cap:5} {s.action:10} {who}{s.reason[:70]}")
        print(
            f"            expires {s.expires_on:%d %b %Y} · sources: {', '.join(s.sources) or '-'}"
        )


def _list(svc: WatchlistService) -> None:
    state = svc.repo.load()
    for kind in ("my", "system"):
        rows = sorted(state.open_entries(kind=kind), key=lambda e: (e.cap, e.symbol))
        print(f"\n{'My' if kind == 'my' else 'System'} Watchlist ({len(rows)})")
        for e in rows:
            flags = f"  {' '.join(e.flags)}" if e.flags else ""
            tgt = f" target ₹{e.target_entry_inr:,.0f}" if e.target_entry_inr else ""
            print(
                f"  {e.symbol:11} {e.cap:5} since {e.added_on:%d %b %Y}{tgt}{flags}  {e.reason[:50]}"
            )
    print(f"\nArchive: {sum(1 for e in state.entries.values() if e.status == 'archived')} entries")


def run(
    action: str, args: list[str], reason: str | None, target: float | None, note: str | None
) -> int:
    svc = _service()
    try:
        if action == "pending":
            svc.ingest_proposals(today=_today())
            _print_pending(svc)
        elif action == "list":
            _list(svc)
        elif action in ("approve", "reject", "snooze"):
            if not args:
                print(
                    f"parakh watchlist {action} needs at least one suggestion id", file=sys.stderr
                )
                return 2
            code = 0
            for sid in args:
                try:
                    if action == "approve":
                        res = svc.approve(
                            sid,
                            channel="cli",
                            note=note or reason,
                            target_entry_inr=target,
                            today=_today(),
                        )
                    elif action == "reject":
                        res = svc.reject(sid, channel="cli", note=reason, today=_today())
                    else:
                        res = svc.snooze(sid, channel="cli", today=_today())
                except WatchlistError as exc:
                    print(f"  ✗ {sid}: {exc}", file=sys.stderr)
                    code = 1
                    continue
                print(f"  {'✓' if res.ok else '–'} {res.message}")
                if res.needs_thesis:
                    print("    next: write the thesis (THESIS.md) or use the Holdings page form")
            return code
        elif action in ("add", "remove"):
            if not args or not reason:
                print(f'usage: parakh watchlist {action} SYMBOL --reason "…"', file=sys.stderr)
                return 2
            res = (
                svc.add_my(
                    args[0], reason=reason, channel="cli", target_entry_inr=target, today=_today()
                )
                if action == "add"
                else svc.remove_my(args[0], reason=reason, channel="cli", today=_today())
            )
            print(("✓ " if res.ok else "– ") + res.message)
        elif action == "review":
            from parakh.watch.history import SignalLog
            from parakh.watch.state import StateStore
            from parakh.watchlist.models import period_of
            from parakh.watchlist.review import load_snapshots, monthly_review

            snaps = load_snapshots()
            if not snaps:
                print("no snapshots found; run `parakh run --mode monthly` first", file=sys.stderr)
                return 2
            period = max(s["period"] for s in snaps)
            snaps = [s for s in snaps if s["period"] == period]
            res_r = monthly_review(
                svc, snaps, period=period or period_of(_today()), today=_today(),
                event_rows=SignalLog(StateStore()).rows(),
            )  # fmt: skip
            print(res_r.line)
            for a in res_r.acts:
                print(f"  {a.kind:10} {a.symbol:11} {a.rule_id or ''}")
        elif action == "ingest":
            acts = svc.ingest_proposals(today=_today())
            print(f"{len(acts)} agent proposal(s) turned into suggestions")
        else:  # pragma: no cover, argparse limits the choices
            return 2
    except WatchlistError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    return 0


def universe(
    action: str, cap: str | None, csv_path: str | None, amfi: str | None = None, small: int = 250
) -> int:
    """`parakh universe stage | import --cap mid --csv file.csv` (F01 full)."""
    from pathlib import Path

    from parakh.config import config_dir
    from parakh.configs import load_all
    from parakh.configs.directory import import_rows

    bundle = load_all()
    if action == "stage":
        by_cap: dict[str, int] = {}
        for s in bundle.universe.active:
            by_cap[s.cap] = by_cap.get(s.cap, 0) + 1
        print(
            f"rollout: {bundle.universe.rollout} · "
            + " · ".join(f"{k} {v}" for k, v in sorted(by_cap.items()))
        )
        return 0
    if action == "import" and amfi:
        from parakh.configs.directory import import_amfi

        try:
            counts = import_amfi(
                Path(amfi), config_dir() / bundle.universe.directory, small_count=small
            )
        except (ValueError, OSError) as exc:
            print(f"rejected: {exc}", file=sys.stderr)
            return 1
        print(
            " · ".join(f"{k} {v}" for k, v in counts.items()),
            f"written to {bundle.universe.directory}/",
        )
        return 0
    if action == "import":
        if cap not in ("large", "mid", "small") or not csv_path:
            print("usage: parakh universe import --cap large|mid|small --csv FILE", file=sys.stderr)
            return 2
        try:
            n = import_rows(Path(csv_path), cap, config_dir() / bundle.universe.directory)  # type: ignore[arg-type]
        except ValueError as exc:
            print(f"rejected: {exc}", file=sys.stderr)
            return 1
        print(f"{n} {cap}-cap stocks written to {bundle.universe.directory}/{cap}.csv")
        return 0
    print("unknown action", file=sys.stderr)
    return 2


def jobs_drain(store_kind: str) -> int:
    """`parakh jobs drain`: serve queued refresh requests (the daily events job calls this)."""
    import datetime as dt

    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.cli_watch import build_deps
    from parakh.orchestration.refresh import drain

    deps = build_deps(store_kind, need_data=False)
    if deps is None:
        return 2
    from parakh.adapters.concalls import ScreenerConcallsProvider

    ctx = RunContext.create(mode="refresh", actor_type="scheduler", actor_id="jobs-drain")
    res = drain(
        ScreenerConcallsProvider(), deps.runner, deps.bundle, ctx, get_sink(), today=dt.date.today()
    )
    print(f"refresh requests: {res.served} served · {res.failed} failed · {res.skipped} skipped")
    for line in res.details:
        print(line)
    return 0


def prompts_pin(action: str, name: str, to: str | None, reason: str) -> int:
    """`parakh prompts rollback NAME --reason ...` / `promote NAME --to vN --reason ...` (P3)."""
    from parakh.prompts.rollback import PinError, promote, rollback

    try:
        if action == "rollback":
            version = rollback(name, reason=reason, to=to)
        else:
            if not to:
                print("promote needs --to vN", file=sys.stderr)
                return 2
            version = promote(name, to, reason=reason)
    except PinError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(f"{name} is now pinned to {version}. Commit registry.yaml to make it permanent.")
    return 0
