"""The Telegram bot: one owner, signed buttons, a few commands (plan 03 §4.3; AC-F11.9–F11.12).

    bot = Bot(bundle, ctx, sink, state, alerts_log, notifier, owner_chat_id="123", key=key,
              providers=providers, today=day)
    bot.poll()          # reads new updates once, answers each, returns what it did

Only the owner's chat is answered. Anyone else is dropped silently and audited
(`AUD.ACCESS.BOT_REJECTED`), so the bot never reveals it exists. A button tap is verified
(`tokens.verify`): an old, edited or foreign payload is rejected and never applied. Every
command and every tap writes one audit event. Command content comes from `BotProviders`,
which the job wires to the report layer; this module imports no analytics.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD
from parakh.configs import ConfigBundle
from parakh.notify.log import AlertsLog
from parakh.notify.routing import AlertState
from parakh.notify.telegram import Notifier, escape
from parakh.notify.tokens import TokenError, verify

log = structlog.get_logger(__name__)


class BotProviders(Protocol):
    def today(self) -> str: ...
    def stock(self, query: str) -> str: ...
    def pending(self) -> str: ...
    def status(self) -> str: ...
    def resolve(self, symbol: str) -> str | None: ...  # symbol → ISIN
    def decide(self, action: str, alert_id: str) -> str: ...  # approve / reject / snooze


@dataclass
class BotResult:
    handled: int = 0
    rejected: int = 0
    next_offset: int | None = None
    replies: list[str] = field(default_factory=list)


PRIVACY_TEXT = (
    "🔒 <b>Privacy</b>\n"
    "Amounts are masked in messages unless you turn them on. Weight % and P&amp;L % always show.\n"
    "Your CAS name, PAN and DP-ID are never stored, logged or sent to an AI model."
)


class Bot:
    def __init__(
        self,
        bundle: ConfigBundle,
        ctx: RunContext,
        sink: AuditSink,
        state: AlertState,
        alerts_log: AlertsLog,
        notifier: Notifier,
        *,
        owner_chat_id: str,
        key: bytes,
        providers: BotProviders,
        today: dt.date,
    ) -> None:
        self.bundle, self.ctx, self.sink = bundle, ctx, sink
        self.state, self.alerts_log, self.notifier = state, alerts_log, notifier
        self.owner = str(owner_chat_id)
        self.key, self.providers, self.today = key, providers, today

    # -- entry -------------------------------------------------------------------------------
    def poll(self, offset: int | None = None) -> BotResult:
        out = BotResult()
        limit = self.bundle.notify.bot.max_updates_per_poll
        for upd in self.notifier.get_updates(offset, limit):  # type: ignore[attr-defined]
            uid = int(upd.get("update_id", 0))  # type: ignore[call-overload]
            out.next_offset = max(out.next_offset or 0, uid + 1)
            if "callback_query" in upd:
                self._callback(upd["callback_query"], out)  # type: ignore[arg-type]
            elif "message" in upd:
                self._message(upd["message"], out)  # type: ignore[arg-type]
        self.state.save()
        return out

    # -- gate --------------------------------------------------------------------------------
    def _is_owner(self, chat_id: object) -> bool:
        return str(chat_id) == self.owner

    def _reject(self, kind: str, chat_id: object, out: BotResult) -> None:
        out.rejected += 1
        self.sink.emit(
            self.ctx,
            AUD.ACCESS_BOT_REJECTED,
            channel="telegram",
            entity_type="bot",
            entity_id=kind,
            reason="not the owner chat",
            details={"kind": kind},  # the foreign chat id is not stored
        )

    def _reply(self, text: str, out: BotResult) -> None:
        out.replies.append(text)
        self.notifier.send(text, silent=True)

    # -- commands ----------------------------------------------------------------------------
    def _message(self, msg: dict[str, Any], out: BotResult) -> None:
        chat_id = (msg.get("chat") or {}).get("id")
        if not self._is_owner(chat_id):
            self._reject("message", chat_id, out)
            return
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return
        head, _, arg = text[1:].partition(" ")
        cmd = head.split("@")[0].lower()
        arg = arg.strip()
        allowed = self.bundle.notify.bot.owner_commands
        out.handled += 1
        if cmd not in allowed:
            reply = "Commands: " + " ".join(f"/{c}" for c in allowed)
        elif cmd == "today":
            reply = self.providers.today()
        elif cmd == "stock":
            reply = self.providers.stock(arg) if arg else "Usage: /stock SYMBOL"
        elif cmd == "pending":
            reply = self.providers.pending()
        elif cmd == "status":
            reply = self.providers.status()
        elif cmd == "privacy":
            reply = PRIVACY_TEXT
        elif cmd == "mute":
            reply = self._mute_command(arg)
        else:  # pragma: no cover, guarded by `allowed`
            reply = "Unknown command."
        self.sink.emit(
            self.ctx,
            AUD.BOT_COMMAND,
            channel="telegram",
            entity_type="bot",
            entity_id=cmd,
            details={"command": cmd, "has_arg": bool(arg)},
        )
        self._reply(reply, out)

    def _mute_command(self, arg: str) -> str:
        if not arg:
            return "Usage: /mute SYMBOL [days]"
        parts = arg.split()
        symbol = parts[0].upper()
        days = self.bundle.notify.bot.mute_days
        if len(parts) > 1 and parts[1].isdigit():
            days = min(int(parts[1]), 90)  # why: a mute is a pause, not a deletion; 90 days max
        isin = self.providers.resolve(symbol)
        if isin is None:
            return f"I do not know {escape(symbol)}."
        until = self.today + dt.timedelta(days=days)
        self.state.mute(isin, None, until)
        self.sink.emit(
            self.ctx,
            AUD.ALERT_MUTED,
            channel="telegram",
            entity_type="mute",
            entity_id=symbol,
            isin=isin,
            details={"until": until.isoformat(), "days": days, "via": "command"},
        )
        return f"🔕 {escape(symbol)} muted until {until.strftime('%d %b %Y')}"

    # -- buttons -----------------------------------------------------------------------------
    def _callback(self, cb: dict[str, Any], out: BotResult) -> None:
        chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
        cb_id = str(cb.get("id", ""))
        if not self._is_owner(chat_id):
            self._reject("callback", chat_id, out)
            return
        try:
            action, alert_id = verify(self.key, str(cb.get("data", "")), self.today)
        except TokenError as exc:
            out.rejected += 1
            self.sink.emit(
                self.ctx,
                AUD.ACCESS_BOT_REJECTED,
                channel="telegram",
                entity_type="button",
                entity_id=exc.reason,
                reason=f"button {exc.reason}",
                details={"reason": exc.reason},
            )
            self.notifier.answer_callback(cb_id, "That button is no longer valid.")  # type: ignore[attr-defined]
            return
        out.handled += 1
        row = self.alerts_log.find(alert_id) or {}
        reply = self._apply(action, alert_id, row)
        self.notifier.answer_callback(cb_id, reply)  # type: ignore[attr-defined]
        out.replies.append(reply)

    def _apply(self, action: str, alert_id: str, row: dict[str, Any]) -> str:
        isin, code = row.get("isin"), row.get("code")
        if action in ("u", "n"):
            useful = action == "u"
            self.alerts_log.record(
                {
                    **{
                        k: row.get(k)
                        for k in ("asof", "isin", "symbol", "code", "kind", "severity", "source")
                    },
                    "alert_id": alert_id,
                    "run_id": self.ctx.run_id,
                    "decision": "feedback",
                    "reason": "useful" if useful else "noise",
                    "payload_hash": row.get("payload_hash", ""),
                }
            )
            self.sink.emit(
                self.ctx,
                AUD.ALERT_FEEDBACK,
                channel="telegram",
                entity_type="alert",
                entity_id=alert_id,
                isin=isin,
                details={"verdict": "useful" if useful else "noise", "code": code},
            )
            return "Thanks, noted as " + ("useful" if useful else "noise")
        if action == "m":
            until = self.today + dt.timedelta(days=self.bundle.notify.bot.mute_days)
            self.state.mute(isin, code, until)
            self.sink.emit(
                self.ctx,
                AUD.ALERT_MUTED,
                channel="telegram",
                entity_type="alert",
                entity_id=alert_id,
                isin=isin,
                details={"until": until.isoformat(), "code": code, "via": "button"},
            )
            return f"Muted until {until.strftime('%d %b')}"
        # a / r / s: a suggestion decision, applied by the proposals layer, never here
        self.sink.emit(
            self.ctx,
            AUD.BOT_COMMAND,
            channel="telegram",
            entity_type="proposal",
            entity_id=alert_id,
            details={"action": action},
        )
        return self.providers.decide(action, alert_id)
