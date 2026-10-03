"""Phase 3 commands: watch, events, digest, heartbeat, bot, notify-test, replay, integrity."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def today_ist() -> dt.date:
    return dt.datetime.now(IST).date()


def build_deps(store_kind: str = "supabase", *, need_data: bool = True, need_feeds: bool = False):  # type: ignore[no-untyped-def]
    """Wire the real adapters from the environment. Secrets are read, never printed."""
    from parakh.adapters.nse_events import NseFeeds
    from parakh.cli_analysis import _data
    from parakh.config import get_settings
    from parakh.configs import load_all
    from parakh.notify.email import SmtpMailer
    from parakh.notify.ntfy import NtfyClient
    from parakh.notify.telegram import TelegramNotifier
    from parakh.notify.tokens import derive_key
    from parakh.orchestration.watch_jobs import WatchDeps
    from parakh.watch.state import StateStore, logs_dir

    bundle = load_all()
    s = get_settings()
    token = s.telegram_bot_token.get_secret_value() if s.telegram_bot_token else None
    chat = s.telegram_chat_id.get_secret_value() if s.telegram_chat_id else None
    notifier = TelegramNotifier(token, chat) if token and chat else None
    ntfy = None
    if bundle.notify.channels.ntfy.enabled:
        from parakh.secrets import get_secret

        topic = get_secret("NTFY_TOPIC")
        ntfy = NtfyClient(bundle.notify.channels.ntfy.server, topic) if topic else None
    data = _data(store_kind, bundle) if need_data else None
    if need_data and data is None:
        return None
    return WatchDeps(
        bundle=bundle,
        data=data,  # type: ignore[arg-type]
        store=StateStore(),
        notifier=notifier,
        mailer=SmtpMailer.from_env(bundle.notify.channels.email),
        feeds=NseFeeds() if need_feeds else None,
        button_key=derive_key(token) if token else None,
        logs_root=logs_dir(),
        ntfy=ntfy,
        trigger="cron",
    )


def _asof(text: str | None) -> dt.date:
    return dt.date.fromisoformat(text) if text else today_ist()


def _report(res) -> int:  # type: ignore[no-untyped-def]
    if res.status == "skipped":
        print(f"{res.job}: skipped, {res.reason}")
        return 0
    print(
        f"{res.job}: {res.status} · run {res.run_id} · alerts {res.alerts} · sent {res.sent} · shadow {res.shadowed} · held {res.suppressed}"
    )
    for k, v in res.errors.items():
        print(f"  ! {k}: {v}", file=sys.stderr)
    return 0 if not res.errors else 1


def watch(asof: str | None, store: str, symbols: list[str] | None) -> int:
    from parakh.orchestration.watch_jobs import daily_watch

    deps = build_deps(store)
    return 2 if deps is None else _report(daily_watch(deps, _asof(asof), symbols=symbols))


def events(asof: str | None, store: str) -> int:
    from parakh.orchestration.watch_jobs import daily_events

    deps = build_deps(store, need_feeds=True)
    return 2 if deps is None else _report(daily_events(deps, _asof(asof)))


def digest(asof: str | None, store: str) -> int:
    from parakh.orchestration.watch_jobs import evening_digest

    deps = build_deps(store, need_data=False)
    return 2 if deps is None else _report(evening_digest(deps, _asof(asof)))


def heartbeat(asof: str | None) -> int:
    from parakh.orchestration.watch_jobs import heartbeat as job

    deps = build_deps(need_data=False)
    return 2 if deps is None else _report(job(deps, _asof(asof)))


def bot(action: str) -> int:
    from parakh.config import get_settings
    from parakh.orchestration.bot_providers import ReportProviders
    from parakh.orchestration.watch_jobs import bot_poll

    deps = build_deps(need_data=False)
    chat = get_settings().telegram_chat_id
    if deps is None or chat is None:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing", file=sys.stderr)
        return 2
    return _report(bot_poll(deps, chat.get_secret_value(), ReportProviders()))


def notify_test() -> int:
    """One real message to check Telegram (and email) are wired; nothing about holdings."""
    from parakh.notify.templates import Message

    deps = build_deps(need_data=False)
    if deps is None or deps.notifier is None:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing", file=sys.stderr)
        return 2
    d = deps.notifier.send(
        "🧪 <b>Parakh</b> test message. If you can read this, Telegram is wired.", silent=True
    )
    print(f"telegram: {'ok' if d.ok else 'FAILED ' + str(d.error)}")
    if deps.mailer is not None:
        m = deps.mailer.send_html("Parakh test email", "<p>Parakh test email.</p>")
        print(f"email: {'ok' if m.ok else 'FAILED ' + str(m.error)}")
    else:
        print("email: not configured (SMTP_USER / SMTP_PASSWORD)")
    _ = Message
    return 0 if d.ok else 1


def replay(days: int, asof: str | None, store: str) -> int:
    import tempfile

    from parakh.calendar import Calendar
    from parakh.orchestration.watch_jobs import build_held
    from parakh.watch.momentum import MomentumWatcher
    from parakh.watch.replay import render_replay, replay_alerts
    from parakh.watch.state import StateStore, logs_dir

    deps = build_deps(store)
    if deps is None:
        return 2
    end = _asof(asof)
    cal = Calendar.from_config(deps.bundle.holidays)
    if not cal.is_trading_day(end):
        end = cal.previous_trading_day(end)
    start = cal.add_trading_days(end, -days)
    with tempfile.TemporaryDirectory() as tmp:
        watcher = MomentumWatcher(
            deps.bundle, deps.data, StateStore(Path(tmp)), build_held(deps, end)
        )
        rows = replay_alerts(watcher, cal, deps.bundle, start, end)
    out = logs_dir() / f"replay_{end:%Y%m%d}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_replay(rows, start, end), encoding="utf-8")
    print(f"replay {start} → {end}: {len(rows)} alert decision(s) written to {out}")
    return 0


def integrity() -> int:
    """The daily audit-chain check (AC-F21.4): one `AUD.INTEGRITY.CHECK`, and a ❌ if it fails."""
    from parakh.audit.context import RunContext
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.audit.steps import audited_step, run_lifecycle
    from parakh.notify.templates import render_failure
    from parakh.orchestration.watch_jobs import _dispatcher

    deps = build_deps(need_data=False)
    sink = get_sink()
    ctx = RunContext.create(
        mode="integrity",
        asof=today_ist(),
        actor_type="scheduler",
        actor_id="integrity",
        trigger="cron",
    )
    with run_lifecycle(ctx, sink):
        with audited_step(ctx, "verify_chain") as step:
            check = sink.verify_chain()
            step.record_output(ok=check.ok, events=check.events)
        sink.emit(
            ctx,
            AUD.INTEGRITY_CHECK,
            entity_type="audit_chain",
            entity_id=check.head,
            details={
                "ok": check.ok,
                "events": check.events,
                "first_bad_event": check.first_bad_event,
            },
        )
    if not check.ok:
        if deps is not None:
            _dispatcher(deps, ctx).send_message(
                render_failure(
                    "Audit integrity check",
                    "verify_chain",
                    f"chain broken at event {check.first_bad_event}",
                    ctx.run_id,
                ),
                code="SYS.INTEGRITY",
            )
        print(f"audit chain BROKEN at {check.first_bad_event}", file=sys.stderr)
        return 1
    print(f"audit chain OK · {check.events} events")
    return 0
