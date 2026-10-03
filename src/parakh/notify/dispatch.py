"""The dispatcher: routing decision → log → audit → delivery (plan 03 §4; ADR-008; AG-05).

    d = Dispatcher(bundle, ctx, sink, state, log, notifier=telegram, mailer=email)
    result = d.submit(alerts)            # route, send the immediate ones as one message
    d.flush_digest()                     # the evening digest, once a day
    d.send_message(render_failure(...))  # system messages bypass routing and shadow mode

Every decision, sent or not, writes one `alerts_log` row and one audit event (`AUD.ALERT.SENT`,
`AUD.ALERT.SUPPRESSED`, `AUD.ALERT.DELIVERY_FAILED`). In shadow mode (`alerts.dry_run`, and
`agents.dry_run` for agent output) nothing leaves the machine: the message is written to the
shadow log with a `[ ] noise` box instead. If Telegram fails, the message goes by email and the
failure is logged (plan 14 L6 resilience: Telegram down → retry + email).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

import structlog

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD
from parakh.audit.ids import new_ulid
from parakh.calendar import Calendar
from parakh.configs import ConfigBundle
from parakh.notify.log import AlertsLog, ShadowLog, plain
from parakh.notify.model import Alert, Decision, alert_from_dict, alert_to_dict
from parakh.notify.routing import AlertState, Router
from parakh.notify.telegram import Delivery, Notifier
from parakh.notify.templates import Message, render_alerts, render_digest
from parakh.notify.tokens import mint

log = structlog.get_logger(__name__)
IMMEDIATE_BATCH = 5  # why: ≤ 10 lines with a header, and one button row per item


class Mailer(Protocol):
    def send_html(
        self,
        subject: str,
        html: str,
        text: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> Delivery: ...


class Ntfy(Protocol):
    def send(self, title: str, text: str, *, priority: str = "high") -> Delivery: ...


@dataclass
class DispatchResult:
    sent: list[Alert] = field(default_factory=list)
    digested: list[Alert] = field(default_factory=list)
    shadowed: list[Alert] = field(default_factory=list)
    suppressed: list[tuple[Alert, str]] = field(default_factory=list)
    failed: list[Alert] = field(default_factory=list)
    messages: int = 0


class Dispatcher:
    def __init__(
        self,
        bundle: ConfigBundle,
        ctx: RunContext,
        sink: AuditSink,
        state: AlertState,
        alerts_log: AlertsLog,
        *,
        notifier: Notifier | None,
        mailer: Mailer | None = None,
        ntfy: Ntfy | None = None,
        button_key: bytes | None = None,
        today: dt.date | None = None,
        alerts_shadow: ShadowLog | None = None,
        agents_shadow: ShadowLog | None = None,
    ) -> None:
        self.bundle, self.ctx, self.sink = bundle, ctx, sink
        self.state, self.log = state, alerts_log
        self.notifier, self.mailer, self.ntfy = notifier, mailer, ntfy
        self.button_key = button_key
        self.today = today or ctx.asof
        self.calendar = Calendar.from_config(bundle.holidays)
        self.router = Router(bundle.notify, self.calendar, state)
        self.alerts_shadow = alerts_shadow or ShadowLog("alerts_shadow.md")
        self.agents_shadow = agents_shadow or ShadowLog("agents_shadow.md")

    # -- helpers -----------------------------------------------------------------------------
    @property
    def include_amounts(self) -> bool:
        return self.bundle.notify.include_amounts

    def _is_agent(self, alert: Alert) -> bool:
        return alert.source.startswith("agent:")

    def _shadow_for(self, alert: Alert) -> ShadowLog | None:
        if self._is_agent(alert) and self.bundle.agents.dry_run:
            return self.agents_shadow
        if alert.kind in ("signal", "event") and self.bundle.flags.alerts.dry_run:
            return self.alerts_shadow
        return None

    def _row(
        self, alert: Alert, alert_id: str, decision: str, reason: str = "", **extra: object
    ) -> None:
        self.log.record(
            {
                "alert_id": alert_id,
                "run_id": self.ctx.run_id,
                "asof": alert.asof.isoformat(),
                "isin": alert.isin,
                "symbol": alert.symbol,
                "code": alert.code,
                "kind": alert.kind,
                "severity": alert.severity.value,
                "source": alert.source,
                "decision": decision,
                "reason": reason,
                "payload_hash": alert.payload_hash(),
                **extra,
            }
        )

    def _audit(
        self, event: AUD, alert: Alert, alert_id: str, reason: str, **details: object
    ) -> None:
        self.sink.emit(
            self.ctx,
            event,
            channel="telegram",
            entity_type="alert",
            entity_id=alert_id,
            isin=alert.isin,
            reason=reason or None,
            details={
                "code": alert.code,
                "severity": alert.severity.value,
                "kind": alert.kind,
                "source": alert.source,
                "dedupe_key": alert.dedupe_key,
                "payload_hash": alert.payload_hash(),
                **details,
            },
        )

    def _buttons(self, msg: Message) -> list[list[tuple[str, str]]] | None:
        if not msg.buttons or self.button_key is None:
            return None
        expires = self.today + dt.timedelta(days=self.bundle.notify.bot.button_token_ttl_days)
        return [
            [(b.text, mint(self.button_key, b.action, b.alert_id, expires)) for b in row]
            for row in msg.buttons
        ]

    def _deliver(self, msg: Message, *, loud_for: list[Alert] | None = None) -> Delivery:
        """Telegram first; on failure the same text goes by email."""
        result = Delivery(False, error="no Telegram notifier configured")
        if self.notifier is not None and self.bundle.notify.channels.telegram_enabled:
            result = self.notifier.send(msg.text, silent=msg.silent, buttons=self._buttons(msg))
        if not result.ok and self.mailer is not None and self.bundle.notify.channels.email.enabled:
            mail = self.mailer.send_html(
                f"Parakh: {plain(msg.lines[0])[:80]}",
                "<br>".join(msg.lines),
                text=plain(msg.text),
            )
            if mail.ok:
                log.warning("notify.telegram_failed_sent_by_email", error=result.error)
                result = Delivery(True, provider_msg_id=mail.provider_msg_id, error=result.error)
        if result.ok and loud_for and self.ntfy and self.bundle.notify.channels.ntfy.enabled:
            top = loud_for[0]
            self.ntfy.send(f"{top.symbol} {top.code}", plain(msg.text))
        return result

    # -- alerts ------------------------------------------------------------------------------
    def submit(self, alerts: list[Alert], *, title: str = "Momentum change") -> DispatchResult:
        out = DispatchResult()
        now_batch: list[tuple[Alert, str, Decision]] = []
        for alert in sorted(alerts, key=lambda a: (-a.severity.rank, a.symbol or "", a.code)):
            alert_id = new_ulid()
            decision = self.router.decide(alert, self.today)
            if decision.action == "suppress":
                out.suppressed.append((alert, decision.reason))
                self._row(alert, alert_id, "suppressed", decision.reason)
                self._audit(AUD.ALERT_SUPPRESSED, alert, alert_id, decision.reason)
                continue
            self.router.commit(alert, decision, self.today)
            if decision.action == "digest":
                out.digested.append(alert)
                self._row(alert, alert_id, "digest", decision.reason)
                self.state.queue_digest(self.today, {**alert_to_dict(alert), "alert_id": alert_id})
                continue
            now_batch.append((alert, alert_id, decision))

        shadow_batch = [(a, i, d) for a, i, d in now_batch if self._shadow_for(a)]
        live_batch = [(a, i, d) for a, i, d in now_batch if not self._shadow_for(a)]
        for alert, alert_id, decision in shadow_batch:
            shadow = self._shadow_for(alert)
            assert shadow is not None
            msg = render_alerts(
                [alert],
                [alert_id],
                day=self.today,
                title=title,
                include_amounts=self.include_amounts,
            )
            shadow.append(
                when=dt.datetime.now(dt.UTC),
                heading=f"{alert.symbol} {alert.code} ({alert.severity.value}), would be sent now: {decision.reason}",
                lines=msg.lines[1:],
                alert_ids=[alert_id],
            )
            out.shadowed.append(alert)
            self._row(alert, alert_id, "shadow", decision.reason, channel="shadow")
            self._audit(AUD.ALERT_SENT, alert, alert_id, decision.reason, dry_run=True)

        for i in range(0, len(live_batch), IMMEDIATE_BATCH):
            chunk = live_batch[i : i + IMMEDIATE_BATCH]
            msg = render_alerts(
                [a for a, _, _ in chunk],
                [aid for _, aid, _ in chunk],
                day=self.today,
                title=title,
                include_amounts=self.include_amounts,
            )
            loud = [a for a, _, d in chunk if d.ntfy]
            delivery = self._deliver(msg, loud_for=loud or None)
            out.messages += 1
            for alert, alert_id, decision in chunk:
                if delivery.ok:
                    out.sent.append(alert)
                    self._row(
                        alert,
                        alert_id,
                        "sent",
                        decision.reason,
                        channel="telegram",
                        provider_msg_id=delivery.provider_msg_id,
                        delivery_status="ok",
                    )
                    self._audit(AUD.ALERT_SENT, alert, alert_id, decision.reason, dry_run=False)
                else:
                    out.failed.append(alert)
                    self._row(
                        alert,
                        alert_id,
                        "failed",
                        decision.reason,
                        channel="telegram",
                        delivery_status=delivery.error or "failed",
                    )
                    self._audit(
                        AUD.ALERT_DELIVERY_FAILED, alert, alert_id, delivery.error or "failed"
                    )
        self.state.save()
        return out

    # -- digest ------------------------------------------------------------------------------
    def flush_digest(self) -> DispatchResult:
        """One evening digest for everything queued up to today (older days included)."""
        out = DispatchResult()
        pending = self.state.pending_digest(self.today)
        rows = [r for day_rows in pending.values() for r in day_rows]
        if not rows:
            return out
        alerts = [alert_from_dict(r) for r in rows]
        ids = [r["alert_id"] for r in rows]
        limit = self.bundle.notify.routing.digest_max_items
        order = sorted(
            range(len(alerts)), key=lambda k: (-alerts[k].severity.rank, alerts[k].symbol or "")
        )
        alerts = [alerts[k] for k in order]
        ids = [ids[k] for k in order]
        shown, shown_ids = alerts[:limit], ids[:limit]
        extra = len(alerts) - len(shown)
        msg = render_digest(shown, shown_ids, day=self.today, include_amounts=self.include_amounts)
        if extra > 0:
            msg = Message(
                msg.template_id,
                [*msg.lines, f"… +{extra} more in the shadow log or reports"][-10:],
                msg.silent,
                msg.buttons,
                msg.alert_ids,
            )
        shadow_all = all(self._shadow_for(a) for a in shown)
        if shadow_all:
            self.alerts_shadow.append(
                when=dt.datetime.now(dt.UTC),
                heading=f"evening digest ({len(alerts)} items), would be sent",
                lines=msg.lines[1:],
                alert_ids=shown_ids,
            )
            out.shadowed.extend(alerts)
            delivered = True
        else:
            delivery = self._deliver(msg)
            out.messages += 1
            delivered = delivery.ok
            (out.sent if delivered else out.failed).extend(shown)
        for a, aid in zip(shown, shown_ids, strict=True):
            self._row(
                a,
                aid,
                "digest_sent" if delivered else "digest_failed",
                channel="shadow" if shadow_all else "telegram",
            )
            if delivered:
                self._audit(AUD.ALERT_SENT, a, aid, "evening digest", dry_run=shadow_all)
        if delivered:
            self.state.clear_digest(list(pending))
        self.state.save()
        return out

    # -- system messages ---------------------------------------------------------------------
    def send_message(self, msg: Message, *, code: str, severity: str = "High") -> Delivery:
        """Failure alerts, the heartbeat, the monthly summary and reviews: never shadowed."""
        alert_id = new_ulid()
        delivery = self._deliver(msg)
        self.log.record(
            {
                "alert_id": alert_id,
                "run_id": self.ctx.run_id,
                "asof": self.ctx.asof.isoformat(),
                "isin": None,
                "symbol": None,
                "code": code,
                "kind": "system",
                "severity": severity,
                "source": "system",
                "decision": "sent" if delivery.ok else "failed",
                "reason": "system message",
                "payload_hash": "sha256:" + new_ulid(),
                "channel": "telegram",
                "delivery_status": "ok" if delivery.ok else (delivery.error or "failed"),
                "provider_msg_id": delivery.provider_msg_id,
            }
        )
        self.sink.emit(
            self.ctx,
            AUD.ALERT_SENT if delivery.ok else AUD.ALERT_DELIVERY_FAILED,
            channel="telegram",
            entity_type="alert",
            entity_id=alert_id,
            reason=None if delivery.ok else delivery.error,
            details={"code": code, "template_id": msg.template_id, "silent": msg.silent},
        )
        return delivery

    # -- agent messages ----------------------------------------------------------------------
    def send_agent_message(self, msg: Message, *, agent: str, code: str) -> Delivery:
        """An agent-written message (the monthly review). Shadow mode keeps it in the log only."""
        if self.bundle.agents.dry_run:
            alert_id = new_ulid()
            self.agents_shadow.append(
                when=dt.datetime.now(dt.UTC),
                heading=f"{agent} {code}, would be sent",
                lines=msg.lines[1:],
                alert_ids=[alert_id],
            )
            self.log.record(
                {
                    "alert_id": alert_id,
                    "run_id": self.ctx.run_id,
                    "asof": self.ctx.asof.isoformat(),
                    "isin": None,
                    "symbol": None,
                    "code": code,
                    "kind": "review",
                    "severity": "Low",
                    "source": f"agent:{agent}",
                    "decision": "shadow",
                    "reason": "agents.dry_run",
                    "payload_hash": "sha256:" + new_ulid(),
                    "channel": "shadow",
                }
            )
            self.sink.emit(
                self.ctx,
                AUD.ALERT_SENT,
                channel="telegram",
                entity_type="alert",
                entity_id=alert_id,
                details={"code": code, "source": f"agent:{agent}", "dry_run": True},
            )
            return Delivery(True, provider_msg_id="shadow")
        return self.send_message(msg, code=code, severity="Low")
