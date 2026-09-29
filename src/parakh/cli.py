"""Command line: `parakh --help` (also `python run.py --help`, plan 13 D1)."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from parakh import __version__
from parakh.config import env_file, get_settings
from parakh.observability.logging import configure_logging

SECRET_SUFFIXES = ("_key", "_token", "_password", "_secret", "_id")


def _doctor() -> int:
    """Report configuration without calling any external service or printing secrets."""
    settings = get_settings()
    path = env_file()
    print(f"parakh {__version__} · env={settings.app_env} · model={settings.llm_model}")
    print(f".env file: {path if path else 'none found (using environment variables only)'}")
    for field_name, info in type(settings).model_fields.items():
        if "SecretStr" in str(info.annotation) or field_name.endswith(SECRET_SUFFIXES):
            value = getattr(settings, field_name)
            print(f"  {field_name.upper():32} {'set' if value else 'missing'}")
    return 0


def _config_validate() -> int:
    from parakh.configs import ConfigError, load_all

    try:
        bundle = load_all()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    u = bundle.universe
    print(f"config OK · {len(bundle.sources)} files · universe mode={u.mode}")
    for s in u.pilot:
        flag = " (golden)" if s.golden else ""
        print(f"  {s.symbol:11} {s.isin}  {s.cap:5}  {s.profile}{flag}")
    return 0


def _run(mode: str, asof: str | None) -> int:
    from parakh.orchestration.jobs import run_dummy

    if mode != "dummy":
        print(f"mode '{mode}' arrives in a later phase (plan 09); only 'dummy' exists in Phase 0")
        return 2
    ctx, outcome = run_dummy(dt.date.fromisoformat(asof) if asof else None)
    print(f"run {ctx.run_id} · {outcome.status} · {len(ctx.steps)} steps")
    if outcome.audit_pending:
        print(
            f"  {outcome.audit_pending} audit events wait in the local outbox (Supabase sync: Phase 1)"
        )
    return 0


def _audit_verify() -> int:
    from parakh.audit.emit import get_sink

    check = get_sink().verify_chain()
    if check.ok:
        print(f"audit chain OK · {check.events} events · head {check.head[:19]}…")
        return 0
    print(
        f"audit chain BROKEN at event {check.first_bad_event} ({check.events} events)",
        file=sys.stderr,
    )
    return 1


def _catalogue(check: bool) -> int:
    from parakh.registry.catalogue import generate

    stale = generate(check=check)
    if check and stale:
        print(f"stale catalogues: {', '.join(stale)} · run `parakh catalogue`", file=sys.stderr)
        return 1
    print("catalogues up to date" if not stale else f"wrote {', '.join(stale)}")
    return 0


def _summarize(path: str) -> int:
    from parakh.orchestration.graph import run_pipeline

    result = run_pipeline(Path(path).read_text(encoding="utf-8"))
    summary = result.summary
    if summary is None:
        print("Summary unavailable: the LLM could not be reached. Try again later.")
        return 2
    print(summary.model_dump_json(indent=2))
    if result.needs_review:
        print(f"Flagged for human review: {result.review_reason}")
    return 0


def _inbox() -> Path:
    """Your private files folder (plan 13 D19): `Stock Analysis\\FILES FOR ANALYSIS`."""
    from parakh.config import REPO_ROOT

    return get_settings().parakh_inbox_dir or REPO_ROOT.parent / "FILES FOR ANALYSIS"


def _prices_load(symbols: list[str] | None, store_kind: str, use_exchange: bool) -> int:
    """Fetch, check and store daily prices for the pilot (Phase 1). Needs the network."""
    from parakh.adapters.corporate_actions import parse_nse_corporate_actions
    from parakh.adapters.exchange_http import ExchangeArchive, NseApi
    from parakh.config import state_dir
    from parakh.configs import load_all
    from parakh.orchestration.prices import YahooPrimary, load_prices
    from parakh.storage.prices import LocalBlobs, ParquetPriceStore, SupabaseBlobs

    bundle = load_all()
    pilot = [s for s in bundle.universe.pilot if not symbols or s.symbol in symbols]
    if not pilot:
        print(f"no pilot stock matches {symbols}", file=sys.stderr)
        return 2
    if store_kind == "supabase":
        from supabase import create_client

        settings = get_settings()
        if not (settings.supabase_url and settings.supabase_service_key):
            print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing", file=sys.stderr)
            return 2
        client = create_client(
            settings.supabase_url, settings.supabase_service_key.get_secret_value()
        )
        blobs = SupabaseBlobs(client)
        blobs.ensure_bucket()
    else:
        blobs = LocalBlobs(state_dir() / "prices")
    store = ParquetPriceStore(blobs, state_dir() / "cache" / "prices")
    resolve = {p.isin: s.isin for s in bundle.universe.pilot for p in s.previous_isins}
    api = NseApi()

    def actions_for(isin: str):  # type: ignore[no-untyped-def]
        sec = bundle.universe.by_isin(isin)
        try:
            rows = api.corporate_actions(sec.symbol) if sec else []
        except Exception as exc:  # the loader still runs; gaps will show as DQ failures
            print(
                f"  {isin}: corporate actions unavailable ({type(exc).__name__})", file=sys.stderr
            )
            rows = []
        return parse_nse_corporate_actions(rows, lambda i: resolve.get(i, i))

    exchange = ExchangeArchive(state_dir() / "raw") if use_exchange else None
    ctx, outcome, loads = load_prices(
        bundle, store, YahooPrimary(), exchange, actions_for, securities=pilot
    )
    print(f"run {ctx.run_id} · {outcome.status}")
    print(f"{'SYMBOL':11} {'ROWS':>6}  {'FROM':10}  {'TO':10}  {'SOURCE':18} DQ")
    for x in loads:
        bad = [r.check_id.split(".")[-1] for r in x.dq if r.status != "pass"]
        print(
            f"{x.symbol:11} {x.rows:>6}  {x.first or '-'!s:10}  {x.last or '-'!s:10}  "
            f"{x.source:18} {x.status}{' (' + ', '.join(bad) + ')' if bad else ''}"
        )
    return 0 if all(x.status != "fail" for x in loads) else 1


def _holdings_check(cas: str | None, broker: str | None) -> int:
    """Parse a CAS and the broker P&L report and reconcile them (local only; nothing is stored).

    Prints ISINs and match statuses only: no quantities, costs, names or account identifiers.
    """
    from collections import Counter

    from parakh.adapters.broker_pnl import parse_groww_pnl
    from parakh.adapters.cas import read_cas_pdf
    from parakh.holdings.lots import lots_from_broker, match_broker_account, reconcile
    from parakh.privacy import account_key

    inbox = _inbox()
    cas_path = (
        Path(cas)
        if cas
        else max(inbox.glob("*CAS*.[Pp][Dd][Ff]"), default=None, key=lambda p: p.stat().st_mtime)
    )
    pnl_path = (
        Path(broker)
        if broker
        else max(
            inbox.glob("Stocks_PnL_Report*.xlsx"), default=None, key=lambda p: p.stat().st_mtime
        )
    )
    if cas_path is None or pnl_path is None:
        print(f"need a CAS PDF and a Groww Stocks P&L report in {inbox}", file=sys.stderr)
        return 2
    password = get_settings().cas_password
    if password is None:
        print("CAS_PASSWORD missing from .env", file=sys.stderr)
        return 2
    statement = read_cas_pdf(cas_path, password.get_secret_value(), account_key())
    report = parse_groww_pnl(pnl_path.read_bytes())
    print(
        f"CAS {statement.period_from} .. {statement.period_to} · {len(statement.account_refs)} accounts · {len(statement.holdings)} holdings"
    )
    print(
        f"broker report (holdings as on {report.holdings_as_of}) · {len(report.open_lots)} lots · {len(report.holdings)} stocks · issues: {len(report.issues)}"
    )
    for issue in report.issues:
        print(f"  ! {issue}")
    ref = match_broker_account(statement, report)
    if ref is None:
        print("could not tell which demat account the broker report covers", file=sys.stderr)
        return 1
    rows = reconcile(statement, lots_from_broker(report, ref), [ref])
    print(
        "reconciliation: "
        + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r.status for r in rows).items()))
    )
    for r in rows:
        if r.status != "match" or r.in_transit_qty:
            note = " (lots in transit at the statement date)" if r.in_transit_qty else ""
            print(f"  {r.isin}  {r.status}{note}")
    return 0 if all(r.status in ("match", "no_lots") for r in rows) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parakh",
        description="Parakh: personal NSE stock analysis with value and momentum lenses",
    )
    parser.add_argument("--version", action="version", version=f"parakh {__version__}")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("doctor", help="check configuration and secrets (no external calls)")

    p_cfg = sub.add_parser("config", help="config tools")
    p_cfg.add_argument("action", choices=["validate"])

    p_run = sub.add_parser("run", help="run a job (Phase 0: --mode dummy)")
    p_run.add_argument("--mode", default="dummy", choices=["dummy", "monthly", "watch", "events"])
    p_run.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: today)")

    p_audit = sub.add_parser("audit", help="audit trail tools")
    p_audit.add_argument("action", choices=["verify"])

    p_cat = sub.add_parser("catalogue", help="regenerate docs/*.md catalogues from the registries")
    p_cat.add_argument("--check", action="store_true", help="fail if any catalogue is stale")

    p_mcp = sub.add_parser("mcp", help="parakh-mcp server (local stdio only)")
    p_mcp.add_argument("action", choices=["serve"])

    p_prices = sub.add_parser("prices", help="daily prices (Phase 1)")
    p_prices.add_argument("action", choices=["load"])
    p_prices.add_argument("--symbol", action="append", help="pilot symbol(s); default: all")
    p_prices.add_argument("--store", choices=["local", "supabase"], default="local")
    p_prices.add_argument(
        "--no-exchange", action="store_true", help="skip the bhavcopy cross-check"
    )

    p_hold = sub.add_parser("holdings", help="holdings tools (local only)")
    p_hold.add_argument("action", choices=["check"])
    p_hold.add_argument("--cas", help="CAS PDF (default: newest in FILES FOR ANALYSIS)")
    p_hold.add_argument("--broker", help="Groww Stocks P&L report (default: newest)")

    p_sum = sub.add_parser("summarize", help="scaffold sample agent: summarise a text file")
    p_sum.add_argument("path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()
    match args.command:
        case "doctor":
            return _doctor()
        case "config":
            return _config_validate()
        case "run":
            return _run(args.mode, args.asof)
        case "audit":
            return _audit_verify()
        case "catalogue":
            return _catalogue(args.check)
        case "mcp":
            from parakh.mcp.server import serve

            serve()
            return 0
        case "prices":
            return _prices_load(args.symbol, args.store, not args.no_exchange)
        case "holdings":
            return _holdings_check(args.cas, args.broker)
        case "summarize":
            return _summarize(args.path)
    parser.print_help(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
