"""Bot: owner-only, signed buttons, commands, mute, feedback (AC-F11.6, F11.9, F11.12)."""

from __future__ import annotations

import datetime as dt

from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.notify.bot import Bot
from parakh.notify.tokens import mint
from tests.helpers.notify import INDIGO, alert, dispatcher

KEY = b"k" * 32
DAY = dt.date(2026, 10, 5)


class P:
    def today(self) -> str:
        return "TODAY"

    def stock(self, q: str) -> str:
        return f"STOCK {q}"

    def pending(self) -> str:
        return "PENDING"

    def status(self) -> str:
        return "STATUS"

    def resolve(self, s: str) -> str | None:
        return INDIGO if s == "INDIGO" else None

    def decide(self, action: str, alert_id: str) -> str:
        return f"DECIDED {action}"


def _bot(tmp_path):  # type: ignore[no-untyped-def]
    d, n, state, log, ctx = dispatcher(tmp_path)
    bot = Bot(
        d.bundle,
        ctx,
        get_sink(),
        state,
        log,
        n,
        owner_chat_id="1",
        key=KEY,
        providers=P(),
        today=DAY,
    )
    return bot, d, n, state, log, ctx


def _msg(uid, chat, text):  # type: ignore[no-untyped-def]
    return {"update_id": uid, "message": {"chat": {"id": chat}, "text": text}}


def _cb(uid, chat, data):  # type: ignore[no-untyped-def]
    return {
        "update_id": uid,
        "callback_query": {"id": f"c{uid}", "data": data, "message": {"chat": {"id": chat}}},
    }


def _types(ctx):  # type: ignore[no-untyped-def]
    return [e.event_type for e in get_sink().events_for_run(ctx.run_id)]


def test_stranger_is_dropped_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, _, n, _, _, ctx = _bot(tmp_path)
    n.updates = [_msg(1, 999, "/today")]
    r = bot.poll()
    assert r.rejected == 1 and n.sent == []
    assert AUD.ACCESS_BOT_REJECTED in _types(ctx)


def test_owner_commands_are_answered_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, _, n, _, _, ctx = _bot(tmp_path)
    n.updates = [_msg(1, 1, "/today"), _msg(2, 1, "/stock indigo"), _msg(3, 1, "/privacy")]
    r = bot.poll()
    assert (
        r.replies[0] == "TODAY"
        and r.replies[1] == "STOCK indigo"
        and "never stored" in r.replies[2]
    )
    assert _types(ctx).count(AUD.BOT_COMMAND) == 3
    assert r.next_offset == 4


def test_mute_command_sets_mute(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, d, n, state, _, _ = _bot(tmp_path)
    n.updates = [_msg(1, 1, "/mute INDIGO 5")]
    bot.poll()
    res = d.submit([alert()])
    assert len(res.suppressed) == 1


def test_button_feedback_and_mute(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, d, n, _, log, ctx = _bot(tmp_path)
    d.submit([alert()])
    aid = log.rows()[0]["alert_id"]
    exp = DAY + dt.timedelta(days=30)
    n.updates = [_cb(1, 1, mint(KEY, "n", aid, exp)), _cb(2, 1, mint(KEY, "m", aid, exp))]
    r = bot.poll()
    assert r.handled == 2
    types = _types(ctx)
    assert AUD.ALERT_FEEDBACK in types and AUD.ALERT_MUTED in types


def test_expired_and_tampered_buttons_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    bot, _, n, _, _, ctx = _bot(tmp_path)
    old = mint(KEY, "u", "01ABC", DAY - dt.timedelta(days=1))
    bad = mint(KEY, "u", "01ABC", DAY + dt.timedelta(days=1))[:-1] + "0"
    n.updates = [_cb(1, 1, old), _cb(2, 1, bad), _cb(3, 1, "junk")]
    r = bot.poll()
    assert r.rejected == 3 and r.handled == 0
