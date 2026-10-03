"""Doubles for the notification layer: a recording Telegram notifier and mailer."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from parakh.audit.context import RunContext
from parakh.audit.emit import get_sink
from parakh.configs import ConfigBundle, load_all
from parakh.notify.dispatch import Dispatcher
from parakh.notify.log import AlertsLog, ShadowLog
from parakh.notify.model import Alert, Severity
from parakh.notify.routing import AlertState
from parakh.notify.telegram import Delivery
from parakh.watch.state import StateStore

INDIGO = "INE646L01027"
MM = "INE101A01026"


@dataclass
class FakeNotifier:
    fail: bool = False
    sent: list[dict] = field(default_factory=list)
    updates: list[dict] = field(default_factory=list)
    answered: list[str] = field(default_factory=list)

    def send(self, text, *, silent=False, buttons=None):  # type: ignore[no-untyped-def]
        self.sent.append({"text": text, "silent": silent, "buttons": buttons})
        if self.fail:
            return Delivery(False, error="HTTP 500")
        return Delivery(True, provider_msg_id=str(len(self.sent)))

    def get_updates(self, offset=None, limit=100):  # type: ignore[no-untyped-def]
        return [u for u in self.updates if offset is None or u["update_id"] >= offset]

    def answer_callback(self, callback_id, text=""):  # type: ignore[no-untyped-def]
        self.answered.append(callback_id)
        return True


@dataclass
class FakeMailer:
    sent: list[dict] = field(default_factory=list)

    def send_html(self, subject, html, text=None, attachments=None):  # type: ignore[no-untyped-def]
        self.sent.append({"subject": subject, "html": html, "text": text, "att": attachments})
        return Delivery(True, provider_msg_id="mail-1")


def alert(
    code: str = "M21",
    *,
    kind: str = "signal",
    severity: Severity = Severity.HIGH,
    direction: str = "exit",
    owned: bool = True,
    isin: str = INDIGO,
    symbol: str = "INDIGO",
    asof: dt.date = dt.date(2026, 10, 5),
    top_decile: bool = False,
    source: str = "watcher",
    group: str = "",
    headline: str = "200-DMA breakdown (2nd close)",
    note: str | None = None,
) -> Alert:
    return Alert(
        kind=kind,  # type: ignore[arg-type]
        code=code,
        severity=severity,
        headline=headline,
        asof=asof,
        isin=isin,
        symbol=symbol,
        direction=direction,  # type: ignore[arg-type]
        owned=owned,
        weight_pct=12.0 if owned else None,
        pnl_pct=18.4 if owned else None,
        top_decile=top_decile,
        source=source,
        group=group,
        note=note,
    )


def bundle(dry_run_alerts: bool = False, dry_run_agents: bool = False) -> ConfigBundle:
    """The repo config with the shadow switches set as a test needs them."""
    from dataclasses import replace

    b = load_all()
    flags = b.flags.model_copy(update={"alerts": b.flags.alerts.model_copy(update={"dry_run": dry_run_alerts})})
    agents = b.agents.model_copy(update={"dry_run": dry_run_agents})
    return replace(b, flags=flags, agents=agents)


def dispatcher(
    tmp_path: Path,
    *,
    today: dt.date = dt.date(2026, 10, 5),
    notifier: FakeNotifier | None = None,
    mailer: FakeMailer | None = None,
    dry_run_alerts: bool = False,
    dry_run_agents: bool = False,
    key: bytes | None = b"k" * 32,
) -> tuple[Dispatcher, FakeNotifier, AlertState, AlertsLog, RunContext]:
    b = bundle(dry_run_alerts, dry_run_agents)
    ctx = RunContext.create(mode="watch", asof=today, actor_type="scheduler", actor_id="test")
    state = AlertState(StateStore(tmp_path / "watch"))
    log = AlertsLog(tmp_path / "alerts")
    n = notifier or FakeNotifier()
    d = Dispatcher(
        b,
        ctx,
        get_sink(),
        state,
        log,
        notifier=n,
        mailer=mailer,
        button_key=key,
        today=today,
        alerts_shadow=ShadowLog("alerts_shadow.md", tmp_path / "logs"),
        agents_shadow=ShadowLog("agents_shadow.md", tmp_path / "logs"),
    )
    return d, n, state, log, ctx
