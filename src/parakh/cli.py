"""Command line: `parakh --help` (also `python run.py --help`, plan 13 D1)."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from parakh import __version__
from parakh.config import env_file, get_settings
from parakh.observability.logging import configure_logging
from parakh.observability.tracing import flush_tracing

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


def _run(
    mode: str,
    asof: str | None,
    symbols: list[str] | None = None,
    store: str = "supabase",
    notify: bool = False,
) -> int:
    from parakh.orchestration.jobs import run_dummy

    if mode == "monthly":
        from parakh.cli_analysis import monthly

        return monthly(asof, symbols, store, notify)
    if mode == "watch":
        from parakh.cli_watch import watch

        return watch(asof, store, symbols)
    if mode == "events":
        from parakh.cli_watch import events

        return events(asof, store)
    if mode != "dummy":
        print(
            f"mode '{mode}' arrives in a later phase (plan 09); 'dummy' and 'monthly' exist so far"
        )
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


def _supabase_repo():  # type: ignore[no-untyped-def]
    """Connect the audit sink and run mirroring to Supabase; None (with a message) if unset."""
    from parakh.storage.supabase_repo import connect_supabase

    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_key):
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY missing from .env", file=sys.stderr)
        return None
    return connect_supabase(settings.supabase_url, settings.supabase_service_key.get_secret_value())


def _fundamentals_load(files: list[str] | None, use_xbrl: bool, store: str) -> int:
    """Load Screener exports (default: every export in FILES FOR ANALYSIS) with the XBRL check."""
    from parakh.adapters.exchange_http import NseApi, NseFilings
    from parakh.config import state_dir
    from parakh.configs import load_all
    from parakh.orchestration.fundamentals import load_fundamentals

    paths = (
        [Path(f) for f in files]
        if files
        else sorted(
            p for p in _inbox().glob("*.xlsx") if not p.name.startswith(("Stocks_PnL", "~$"))
        )
    )
    if not paths:
        print(f"no Screener exports found in {_inbox()}", file=sys.stderr)
        return 2
    repo = _supabase_repo() if store == "supabase" else None
    if store == "supabase" and repo is None:
        return 2
    filings = NseFilings(NseApi(), state_dir() / "raw") if use_xbrl else None
    ctx, outcome, loads = load_fundamentals(
        load_all(), [p.read_bytes() for p in paths], filings, repo
    )
    if repo is not None:
        repo.record_dq(ctx.run_id, [r for x in loads for r in x.dq])
    print(
        f"run {ctx.run_id} · {outcome.status} · {len(paths)} files, {outcome.summary.get('unmatched', 0)} unmatched"
    )
    print(f"{'SYMBOL':11} {'FACTS':>5} {'DATED':>5} {'NEW':>5} {'RESTATED':>8}  DQ")
    for x in loads:
        bad = [f"{r.check_id.split('.')[-1]}:{r.status}" for r in x.dq if r.status != "pass"]
        print(
            f"{x.symbol:11} {x.facts:>5} {x.with_reported_on:>5} {x.inserted:>5} {x.restated:>8}  "
            f"{x.status}{' (' + ', '.join(bad) + ')' if bad else ''}"
        )
    return 0 if all(x.status != "fail" for x in loads) else 1


def _reference_load(store: str, amfi_file: str | None) -> int:
    """AMFI cap categories + Nifty index membership for the universe. Needs the network."""
    import hashlib
    import re

    import httpx

    from parakh.adapters.exchange_http import BROWSER_HEADERS
    from parakh.adapters.reference import INDEX_FILES, index_url
    from parakh.config import state_dir
    from parakh.configs import load_all
    from parakh.orchestration.reference import load_reference

    raw = state_dir() / "raw" / "reference"
    raw.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(headers=BROWSER_HEADERS, timeout=40, follow_redirects=True)

    def keep(name: str, data: bytes) -> bytes:
        (raw / f"{hashlib.sha256(data).hexdigest()[:12]}_{name}").write_bytes(data)
        return data

    if amfi_file:
        amfi = Path(amfi_file).read_bytes()
    else:
        page = client.get("https://www.amfiindia.com/otherdata/categorisation-of-stocks")
        page.raise_for_status()
        links = re.findall(r'href="([^"]+\.xlsx?)"', page.text, flags=re.I)
        if not links:
            print("no AMFI list link found; download it and pass --amfi FILE", file=sys.stderr)
            return 2
        url = links[0] if links[0].startswith("http") else "https://www.amfiindia.com" + links[0]
        resp = client.get(url)
        resp.raise_for_status()
        amfi = keep("amfi.xlsx", resp.content)
    files = {}
    for index_id in INDEX_FILES:
        resp = client.get(index_url(index_id), headers={"Referer": "https://www.niftyindices.com/"})
        resp.raise_for_status()
        files[index_id] = keep(f"{INDEX_FILES[index_id]}.csv", resp.content)
    repo = _supabase_repo() if store == "supabase" else None
    if store == "supabase" and repo is None:
        return 2
    bundle = load_all()
    ctx, outcome, report = load_reference(bundle, amfi, files, writer=repo)
    if repo is not None:
        repo.record_dq(ctx.run_id, report.dq)
    print(f"run {ctx.run_id} · {outcome.status} · AMFI list to {report.amfi_period_end}")
    caps = {c["isin"]: c for c in report.caps}
    print(f"{'SYMBOL':11} {'RANK':>5}  {'AMFI':6} {'CONFIG':6}  INDICES")
    for sec in bundle.universe.active:
        c = caps.get(sec.isin)
        print(
            f"{sec.symbol:11} {c['amfi_rank'] if c else '-':>5}  {c['bucket'] if c else '-':6} {sec.cap:6}  "
            f"{', '.join(report.membership.get(sec.isin, [])) or 'none of the three'}"
        )
    print(f"membership changes: {len(report.joins)} joined, {len(report.leaves)} left")
    for r in report.dq:
        if r.status != "pass":
            print(f"  {r.status}: {r.check_id} {r.isin} {r.detail}")
    return 0 if report.status != "fail" else 1


def _shareholding_load(store: str, symbols: list[str] | None) -> int:
    """Quarterly shareholding pattern and promoter pledge from NSE filings. Needs the network."""
    from parakh.adapters.exchange_http import NseApi
    from parakh.configs import load_all
    from parakh.orchestration.shareholding import load_shareholding
    from parakh.render.format import pct

    repo = _supabase_repo() if store == "supabase" else None
    if store == "supabase" and repo is None:
        return 2
    ctx, outcome, report = load_shareholding(load_all(), NseApi(), symbols, writer=repo)
    if repo is not None:
        repo.record_dq(ctx.run_id, report.dq)
    print(f"run {ctx.run_id} · {outcome.status}")
    print(
        f"{'SYMBOL':11} {'QTRS':>4} {'NEW':>4}  {'LATEST':10} {'PROMOTER':>9} {'FII':>7} "
        f"{'DII':>7} {'MF':>7} {'PLEDGE':>7}  DQ"
    )
    for x in report.loads:
        r = x.latest or {}
        cells = [
            pct(r.get(k), decimals=2, signed=False)
            for k in ("promoter_pct", "fii_pct", "dii_pct", "mf_pct", "pledge_pct")
        ]
        print(
            f"{x.symbol:11} {x.quarters:>4} {x.added:>4}  {r.get('period_end', '-'):10} "
            f"{cells[0]:>9} {cells[1]:>7} {cells[2]:>7} {cells[3]:>7} {cells[4]:>7}  {x.status}"
        )
    for r in report.dq:
        if r.status != "pass":
            print(f"  {r.status}: {r.check_id} {r.isin} {r.detail}")
    return 0 if report.status != "fail" else 1


def _profile_load(store: str) -> int:
    """D24 profile inputs from exchange filings (lease debt, rentals, advances, listed stakes)."""
    from parakh.adapters.exchange_http import NseApi, NseFilings
    from parakh.config import state_dir
    from parakh.configs import load_all
    from parakh.orchestration.profile_inputs import load_profile_inputs

    repo = _supabase_repo() if store == "supabase" else None
    if store == "supabase" and repo is None:
        return 2
    api = NseApi()
    ctx, outcome, loads = load_profile_inputs(
        load_all(), NseFilings(api, state_dir() / "raw"), api, writer=repo
    )
    if repo is not None:
        repo.record_dq(ctx.run_id, [r for x in loads for r in x.dq])
    print(f"run {ctx.run_id} · {outcome.status}")
    for x in loads:
        print(
            f"{x.symbol}: {len(x.rows)} values, {x.inserted} new, {x.restated} restated · {x.status}"
        )
        for metric, (period, value) in sorted(x.latest().items()):
            print(f"  {metric.removeprefix('profile.'):40} {period}  {value:>16,.2f}")
        for r in x.dq:
            if r.status != "pass":
                print(f"  {r.status}: {r.check_id} {r.detail}")
    return 0 if all(x.status != "fail" for x in loads) else 1


def _dq_scorecard() -> int:
    """Latest data-quality result of every check, per stock (plan 10 §13)."""
    from parakh.configs import load_all
    from parakh.quality.scorecard import scorecard
    from parakh.render.format import pct

    repo = _supabase_repo()
    if repo is None:
        return 2
    symbols = {s.isin: s.symbol for s in load_all().universe.active}
    card = scorecard(repo.dq_rows(), symbols)
    if not card.rows:
        print("no data-quality results stored yet")
        return 0
    mark = {"pass": "ok", "warn": "WARN", "fail": "FAIL"}
    print(f"{'SYMBOL':12} " + " ".join(f"{a:13}" for a in card.areas) + " CONFIDENCE")
    for row in card.rows:
        cells = " ".join(f"{mark.get(row.areas.get(a, ''), '-'):13}" for a in card.areas)
        why = f"  ({', '.join(row.confidence.reasons)})" if row.confidence.reasons else ""
        print(f"{row.symbol:12} {cells} {row.confidence.level}{why}")
    print(f"DQ {pct(card.score_pct, decimals=1, signed=False)} over {card.checks} checks")
    return 0 if all(r.failed == 0 for r in card.rows) else 1


BACKUP_KEY_FILE = "parakh-backup-key.txt"  # beside the repo, in Stock Analysis (never committed)


def _backup(action: str) -> int:
    """keygen: make an age key pair. run: weekly encrypted backup. verify: check the latest."""
    import re

    from parakh.config import REPO_ROOT

    key_file = REPO_ROOT.parent / BACKUP_KEY_FILE
    if action == "keygen":
        from pyrage import x25519

        if key_file.exists():
            print(f"{key_file} already exists; not overwriting it", file=sys.stderr)
            return 2
        identity = x25519.Identity.generate()
        key_file.write_text(
            f"# Parakh backup key. Keep a copy in your password manager.\n{identity}\n",
            encoding="utf-8",
        )
        print(f"private key written to {key_file} (copy it to your password manager)")
        print(f"public key for config/backup.yaml recipients: {identity.to_public()}")
        return 0

    import psycopg

    from parakh.configs import load_all
    from parakh.storage.prices import SupabaseBlobs

    bundle = load_all()
    settings = get_settings()
    repo = _supabase_repo()
    if repo is None or settings.supabase_db_password is None or not settings.supabase_url:
        print(
            "SUPABASE_URL, SUPABASE_SERVICE_KEY and SUPABASE_DB_PASSWORD are needed",
            file=sys.stderr,
        )
        return 2
    blobs = SupabaseBlobs(repo.client, bundle.backup.bucket)
    if action == "run":
        from parakh.orchestration.backup import run_backup
        from parakh.storage.backup import PostgresTables

        ref = re.search(r"https://([a-z0-9]+)\.supabase\.co", settings.supabase_url)
        if ref is None:
            print("SUPABASE_URL is not a supabase.co project URL", file=sys.stderr)
            return 2
        blobs.ensure_bucket()
        with psycopg.connect(
            host=bundle.backup.pooler_host,
            port=5432,
            dbname="postgres",
            user=f"postgres.{ref.group(1)}",
            password=settings.supabase_db_password.get_secret_value(),
            connect_timeout=20,
        ) as conn:
            ctx, outcome, info = run_backup(bundle, PostgresTables(conn), blobs)
        assert info is not None
        print(
            f"run {ctx.run_id} · {outcome.status} · {info.name} · {info.tables} tables, {info.rows} rows, {info.bytes:,} bytes"
        )
        return 0
    # verify
    from parakh.storage.backup import decrypt, read_archive

    names = sorted(n for n in blobs.list() if n.endswith(".tar.gz.age"))
    if not names:
        print("no backups yet", file=sys.stderr)
        return 1
    if not key_file.exists():
        print(f"private key not found at {key_file}", file=sys.stderr)
        return 2
    identity = next(
        line.strip()
        for line in key_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("AGE-SECRET-KEY-")
    )
    data = blobs.get(names[-1])
    assert data is not None
    manifest, _ = read_archive(decrypt(data, identity))
    rows = sum(t["rows"] for t in manifest["tables"].values())
    print(
        f"{names[-1]} decrypts and matches its manifest: {len(manifest['tables'])} tables, {rows} rows, migrations {manifest['migrations']}"
    )
    return 0


def _prices_load(symbols: list[str] | None, store_kind: str, use_exchange: bool) -> int:
    """Fetch, check and store daily prices for the pilot (Phase 1). Needs the network."""
    from parakh.adapters.corporate_actions import parse_nse_corporate_actions
    from parakh.adapters.exchange_http import ExchangeArchive, NseApi
    from parakh.config import state_dir
    from parakh.configs import load_all
    from parakh.orchestration.prices import YahooPrimary, load_prices
    from parakh.storage.prices import LocalBlobs, ParquetPriceStore, SupabaseBlobs

    bundle = load_all()
    pilot = [s for s in bundle.universe.active if not symbols or s.symbol in symbols]
    if not pilot:
        print(f"no pilot stock matches {symbols}", file=sys.stderr)
        return 2
    repo = _supabase_repo() if store_kind == "supabase" else None
    if store_kind == "supabase":
        if repo is None:
            return 2
        blobs = SupabaseBlobs(repo.client)
        blobs.ensure_bucket()
    else:
        blobs = LocalBlobs(state_dir() / "prices")
    store = ParquetPriceStore(blobs, state_dir() / "cache" / "prices")
    resolve = {p.isin: s.isin for s in bundle.universe.active for p in s.previous_isins}
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
    if repo is not None:
        source = {x.isin: x.source for x in loads}
        repo.record_price_files(
            [
                {
                    "isin": w.isin,
                    "year": w.year,
                    "storage_path": w.path,
                    "sha256": w.sha256,
                    "rows": w.rows,
                    "first_date": w.first.isoformat(),
                    "last_date": w.last.isoformat(),
                    "source_id": "yfinance" if source.get(w.isin) == "yfinance" else "nse_archives",
                    "adjusted": True,
                    "run_id": ctx.run_id,
                }
                for w in store.written
            ]
        )
        repo.record_dq(ctx.run_id, [r for x in loads for r in x.dq])
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


def _holdings_import() -> int:
    """Store the newest CAS + broker report in Supabase (restricted tables). Counts only."""
    import hashlib

    from parakh.adapters.broker_pnl import parse_groww_pnl
    from parakh.adapters.cas import read_cas_pdf
    from parakh.orchestration.holdings import import_holdings
    from parakh.privacy import AccountKeyMissing, account_key

    inbox = _inbox()
    cas_path = max(inbox.glob("*CAS*.[Pp][Dd][Ff]"), default=None, key=lambda p: p.stat().st_mtime)
    pnl_path = max(
        inbox.glob("Stocks_PnL_Report*.xlsx"), default=None, key=lambda p: p.stat().st_mtime
    )
    password = get_settings().cas_password
    if cas_path is None or password is None:
        print(f"need a CAS PDF in {inbox} and CAS_PASSWORD in .env", file=sys.stderr)
        return 2
    try:
        key = account_key(require_stable=True)
    except AccountKeyMissing as exc:
        print(exc, file=sys.stderr)
        return 2
    repo = _supabase_repo()
    if repo is None:
        return 2
    data = cas_path.read_bytes()
    statement = read_cas_pdf(cas_path, password.get_secret_value(), key)
    report = parse_groww_pnl(pnl_path.read_bytes()) if pnl_path else None
    ctx, outcome, r = import_holdings(
        statement, "sha256:" + hashlib.sha256(data).hexdigest(), report, repo
    )
    print(f"run {ctx.run_id} · {outcome.status}")
    print(
        f"statement {statement.period_to}: {'new' if r.statement_new else 'already imported'} · "
        f"{r.positions} positions · {r.lots_added} lots added ({r.cost_pending} cost pending)"
        f"{' · seeded from broker report' if r.seeded else ''}"
    )
    print(
        "reconciliation: "
        + ", ".join(f"{k} {v}" for k, v in sorted(r.recon.items()))
        + f" · in transit {r.in_transit}"
    )
    return 0


def _holdings_keygen() -> int:
    """Append a stable PARAKH_ACCOUNT_KEY to your .env (never printed)."""
    import secrets

    from parakh.config import env_file

    path = env_file()
    if path is None:
        print("no .env found", file=sys.stderr)
        return 2
    if get_settings().parakh_account_key is not None:
        print("PARAKH_ACCOUNT_KEY is already set; not changing it (that would orphan stored lots)")
        return 0
    with path.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n# Parakh: key behind account references (plan 13 P6). Never change it.\nPARAKH_ACCOUNT_KEY={secrets.token_hex(32)}\n"
        )
    print(f"PARAKH_ACCOUNT_KEY added to {path}")
    return 0


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
    p_run.add_argument("--asof", help="as-of date, YYYY-MM-DD (default: the latest month-end)")
    p_run.add_argument(
        "--symbol", action="append", help="monthly mode: pilot symbol(s); default: all"
    )
    p_run.add_argument(
        "--store",
        choices=["local", "supabase"],
        default="supabase",
        help="where prices are read from",
    )
    p_run.add_argument(
        "--notify", action="store_true", help="monthly mode: send the Telegram summary and email"
    )

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

    p_fund = sub.add_parser("fundamentals", help="Screener exports + XBRL cross-check (Phase 1)")
    p_fund.add_argument("action", choices=["load"])
    p_fund.add_argument(
        "--file", action="append", help="export file(s); default: all in FILES FOR ANALYSIS"
    )
    p_fund.add_argument("--no-xbrl", action="store_true", help="skip the exchange XBRL tie-out")
    p_fund.add_argument("--store", choices=["none", "supabase"], default="none")

    p_prof = sub.add_parser("profile", help="D24 profile inputs from filings (Phase 1)")
    p_prof.add_argument("action", choices=["load"])
    p_prof.add_argument("--store", choices=["none", "supabase"], default="none")

    p_dq = sub.add_parser("dq", help="data-quality scorecard (Phase 1)")
    p_dq.add_argument("action", choices=["scorecard"])

    p_shp = sub.add_parser("shareholding", help="shareholding pattern and pledge (Phase 1)")
    p_shp.add_argument("action", choices=["load"])
    p_shp.add_argument("--symbol", action="append", help="pilot symbol(s); default: all")
    p_shp.add_argument("--store", choices=["none", "supabase"], default="none")

    p_ref = sub.add_parser("reference", help="AMFI cap list and index constituents (Phase 1)")
    p_ref.add_argument("action", choices=["load"])
    p_ref.add_argument("--store", choices=["none", "supabase"], default="none")
    p_ref.add_argument("--amfi", help="AMFI .xlsx file (default: latest from amfiindia.com)")

    p_bak = sub.add_parser("backup", help="encrypted database backups (plan 10 §11)")
    p_bak.add_argument("action", choices=["keygen", "run", "verify"])

    p_hold = sub.add_parser("holdings", help="holdings tools (local only)")
    p_hold.add_argument("action", choices=["check", "import", "keygen"])
    p_hold.add_argument("--cas", help="CAS PDF (default: newest in FILES FOR ANALYSIS)")
    p_hold.add_argument("--broker", help="Groww Stocks P&L report (default: newest)")

    p_show = sub.add_parser("show", help="TL;DR, verdict chip and what changed for one stock")
    p_show.add_argument("symbol")
    p_show.add_argument("--period", help="YYYY-MM (default: latest)")

    p_exp = sub.add_parser(
        "explain", help="verdict lineage: rule, lens, metric, source (plan 10 §6)"
    )
    p_exp.add_argument("symbol")
    p_exp.add_argument("--period", help="YYYY-MM (default: latest)")
    p_exp.add_argument("--json", action="store_true")

    p_shr = sub.add_parser("share", help="share export: Markdown + PNG with no position data")
    p_shr.add_argument("symbol")
    p_shr.add_argument("--period", help="YYYY-MM (default: latest)")

    p_th = sub.add_parser(
        "thesis", help="validate THESIS.md files / list the variables rules may use"
    )
    p_th.add_argument("action", choices=["validate", "variables"])
    p_th.add_argument("symbol", nargs="?")

    p_ov = sub.add_parser(
        "override", help="verdict/profile/archetype/thesis-status overrides (reason + expiry)"
    )
    p_ov.add_argument("action", choices=["add"])
    p_ov.add_argument("--isin", required=True)
    p_ov.add_argument(
        "--field", required=True, choices=["verdict", "profile", "archetype", "thesis_status"]
    )
    p_ov.add_argument("--value", required=True)
    p_ov.add_argument("--reason", required=True)
    p_ov.add_argument("--days", type=int, default=90, help="life in days (max 366)")

    p_idx = sub.add_parser("indices", help="benchmark and VIX series")
    p_idx.add_argument("action", choices=["load"])
    p_idx.add_argument("--store", choices=["local", "supabase"], default="local")

    p_mod = sub.add_parser("models", help="regenerate docs/MODELS.md and the lens cards")
    p_mod.add_argument("--check", action="store_true", help="fail if they are stale")

    p_w = sub.add_parser("watch", help="daily momentum watcher (Phase 3)")
    p_w.add_argument("--asof")
    p_w.add_argument("--symbol", action="append")
    p_w.add_argument("--store", choices=["local", "supabase"], default="supabase")

    p_e = sub.add_parser(
        "events", help="daily event watcher: filings, insider trades, surveillance"
    )
    p_e.add_argument("--asof")
    p_e.add_argument("--store", choices=["local", "supabase"], default="supabase")

    p_d = sub.add_parser("digest", help="send the evening digest of queued alerts")
    p_d.add_argument("--asof")
    p_d.add_argument("--store", choices=["local", "supabase"], default="supabase")

    p_hb = sub.add_parser("heartbeat", help="Sunday heartbeat: jobs healthy, service levels")
    p_hb.add_argument("--asof")

    p_bot = sub.add_parser("bot", help="Telegram bot: answer new messages and button taps once")
    p_bot.add_argument("action", choices=["poll"])

    sub.add_parser("notify-test", help="send one test message to Telegram (and email)")

    p_rp = sub.add_parser(
        "replay", help="replay the watcher over the last N trading days (sends nothing)"
    )
    p_rp.add_argument("--days", type=int, default=60)
    p_rp.add_argument("--asof")
    p_rp.add_argument("--store", choices=["local", "supabase"], default="supabase")

    p_nf = sub.add_parser(
        "notify-failure", help="send a failure alert for a workflow that broke outside a job"
    )
    p_nf.add_argument("--job", required=True)
    p_nf.add_argument("--run-url")

    sub.add_parser("integrity", help="verify the audit hash chain; alert if it is broken")
    p_find = sub.add_parser("find", help="every alert for a signal or rule code (e.g. M03)")
    p_find.add_argument("code")

    p_un = sub.add_parser("universe", help="stock universe: stage, import (Phase 4 scale-up)")
    p_un.add_argument("action", choices=["stage", "import"])
    p_un.add_argument("--cap", choices=["large", "mid", "small"])
    p_un.add_argument("--csv")
    p_un.add_argument("--amfi", help="AMFI half-yearly .xlsx: writes large, mid and small at once")
    p_un.add_argument("--small", type=int, default=250, help="small caps to take (AMFI ranks 251+)")

    p_cc = sub.add_parser("concalls", help="concall transcripts: fetch the latest per stock")
    p_cc.add_argument("action", choices=["fetch"])
    p_cc.add_argument("--symbol", action="append", help="repeat for several; default is all")

    p_ag = sub.add_parser("agents", help="agents: run the priced eval on real documents")
    p_ag.add_argument("action", choices=["eval"])
    p_ag.add_argument("--symbol", action="append", help="repeat for several; default is all")
    p_ag.add_argument("--no-devils-advocate", action="store_true")

    p_pr = sub.add_parser("prompts", help="prompt pins: roll back or promote a version (P3)")
    p_pr.add_argument("action", choices=["rollback", "promote"])
    p_pr.add_argument("name")
    p_pr.add_argument("--to", help="version to pin, e.g. v1 (promote needs it)")
    p_pr.add_argument("--reason", required=True)

    p_jb = sub.add_parser("jobs", help="queued jobs: drain refresh requests")
    p_jb.add_argument("action", choices=["drain"])
    p_jb.add_argument("--store", choices=["local", "supabase"], default="supabase")

    p_wl = sub.add_parser(
        "watchlist", help="watchlist: pending, approve, reject, add, remove, review"
    )
    p_wl.add_argument(
        "action",
        choices=[
            "pending",
            "list",
            "approve",
            "reject",
            "snooze",
            "add",
            "remove",
            "review",
            "ingest",
        ],
    )
    p_wl.add_argument("args", nargs="*", help="suggestion ids, or a symbol for add/remove")
    p_wl.add_argument("--reason", help="required for add/remove; optional note for reject/approve")
    p_wl.add_argument("--target", type=float, help="target entry price in rupees (add/approve)")
    p_wl.add_argument("--note", help="decision note (approve)")

    p_cal = sub.add_parser(
        "calibrate", help="calibration (F17): backtest, outcomes, quintiles; governance checks"
    )
    p_cal.add_argument(
        "action",
        choices=["membership-import", "panel", "report", "drift", "replay", "restore-test"],
    )
    p_cal.add_argument("file", nargs="?", help="membership-import: the constituents CSV")
    p_cal.add_argument("--store", choices=["local", "supabase"], default="supabase")
    p_cal.add_argument("--years", type=int, default=10)
    p_cal.add_argument("--quarter", help="report label, e.g. 2026-Q4 (default: this quarter)")
    p_cal.add_argument(
        "--allow-proxy",
        action="store_true",
        help="run the backtest on today's members, labelled biased",
    )
    p_cal.add_argument("--rebuild", action="store_true", help="panel: re-score everything")
    p_cal.add_argument(
        "--write", action="store_true", help="report: write docs/calibration and the review"
    )
    p_cal.add_argument("--asof", help="replay: month-end to replay, or drift: period YYYY-MM")
    p_cal.add_argument("--output", help="folder of stored snapshots (default: the output folder)")

    p_j = sub.add_parser("journal", help="decision journal: add, list, due, review")
    p_j.add_argument("action", choices=["add", "list", "due", "review"])
    p_j.add_argument("args", nargs="*", help="add: SYMBOL · review: ENTRY_ID")
    p_j.add_argument("--action", dest="kind", help="buy, add, trim, sell, hold or skip")
    p_j.add_argument("--reason")
    p_j.add_argument("--expected")
    p_j.add_argument("--review-on", dest="when", help="YYYY-MM-DD (default: 3 months)")
    p_j.add_argument("--verdict", choices=["right", "wrong", "mixed", "too_early"])
    p_j.add_argument("--note")

    p_sum = sub.add_parser("summarize", help="scaffold sample agent: summarise a text file")
    p_sum.add_argument("path")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        return _dispatch(argv)
    finally:
        flush_tracing()  # short-lived jobs must send their Langfuse traces before the process ends


def _dispatch(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()
    match args.command:
        case "doctor":
            return _doctor()
        case "config":
            return _config_validate()
        case "run":
            return _run(args.mode, args.asof, args.symbol, args.store, args.notify)
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
        case "fundamentals":
            return _fundamentals_load(args.file, not args.no_xbrl, args.store)
        case "profile":
            return _profile_load(args.store)
        case "dq":
            return _dq_scorecard()
        case "shareholding":
            return _shareholding_load(args.store, args.symbol)
        case "reference":
            return _reference_load(args.store, args.amfi)
        case "backup":
            return _backup(args.action)
        case "holdings":
            if args.action == "import":
                return _holdings_import()
            if args.action == "keygen":
                return _holdings_keygen()
            return _holdings_check(args.cas, args.broker)
        case "show":
            from parakh.cli_analysis import show

            return show(args.symbol, args.period)
        case "explain":
            from parakh.cli_analysis import explain

            return explain(args.symbol, args.period, args.json)
        case "share":
            from parakh.cli_analysis import share

            return share(args.symbol, args.period)
        case "thesis":
            from parakh.cli_analysis import thesis

            return thesis(args.action, args.symbol)
        case "override":
            from parakh.cli_analysis import override_add

            return override_add(args.isin, args.field, args.value, args.reason, args.days)
        case "indices":
            from parakh.cli_analysis import indices_load

            return indices_load(args.store)
        case "models":
            from parakh.cli_analysis import models

            return models(args.check)
        case "watch":
            from parakh.cli_watch import watch

            return watch(args.asof, args.store, args.symbol)
        case "events":
            from parakh.cli_watch import events

            return events(args.asof, args.store)
        case "digest":
            from parakh.cli_watch import digest

            return digest(args.asof, args.store)
        case "heartbeat":
            from parakh.cli_watch import heartbeat

            return heartbeat(args.asof)
        case "bot":
            from parakh.cli_watch import bot

            return bot(args.action)
        case "notify-test":
            from parakh.cli_watch import notify_test

            return notify_test()
        case "replay":
            from parakh.cli_watch import replay

            return replay(args.days, args.asof, args.store)
        case "notify-failure":
            from parakh.cli_watch import notify_failure

            return notify_failure(args.job, args.run_url)
        case "find":
            from parakh.cli_watch import find_code

            return find_code(args.code)
        case "integrity":
            from parakh.cli_watch import integrity

            return integrity()
        case "universe":
            from parakh.cli_watchlist import universe

            return universe(args.action, args.cap, args.csv, args.amfi, args.small)
        case "concalls":
            from parakh.cli_agents import concalls_fetch

            return concalls_fetch(args.symbol)
        case "agents":
            from parakh.cli_agents import agents_eval

            return agents_eval(args.symbol, not args.no_devils_advocate)
        case "prompts":
            from parakh.cli_watchlist import prompts_pin

            return prompts_pin(args.action, args.name, args.to, args.reason)
        case "jobs":
            from parakh.cli_watchlist import jobs_drain

            return jobs_drain(args.store)
        case "calibrate":
            from parakh import cli_calibration as cc

            match args.action:
                case "membership-import":
                    if not args.file:
                        print("usage: parakh calibrate membership-import FILE.csv", file=sys.stderr)
                        return 2
                    return cc.membership_import(args.file)
                case "panel":
                    return cc.panel(args.store, args.years, args.rebuild)
                case "report":
                    return cc.report(
                        args.store, args.years, args.quarter, args.allow_proxy, args.write
                    )
                case "drift":
                    return cc.drift(args.output, args.asof)
                case "replay":
                    return cc.replay_check(args.store, args.asof, args.output)
                case _:
                    return cc.restore_check()
        case "journal":
            from parakh.cli_calibration import journal

            return journal(
                args.action, args.args, args.reason, args.expected, args.when,
                args.verdict, args.note, args.kind,
            )  # fmt: skip
        case "watchlist":
            from parakh.cli_watchlist import run as watchlist

            return watchlist(args.action, args.args, args.reason, args.target, args.note)
        case "summarize":
            return _summarize(args.path)
    parser.print_help(sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
