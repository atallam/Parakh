"""Telegram cards for pending watchlist suggestions (plan 06 §5.2; AC-F15.1).

    msg = render_suggestion_cards(pending, max_cards=5)   # one message, ✅ ❌ 💤 per card

Each button carries the suggestion id in a signed, expiring token (`tokens.mint`); a tap is applied by
the service, never here. Amounts never appear: a suggestion is a symbol, a cap and a reason.
"""

from __future__ import annotations

from collections.abc import Sequence

from parakh.notify.telegram import escape
from parakh.notify.templates import Button, Message, fit_lines
from parakh.watchlist.models import Suggestion

VERB = {
    "add_my": "Add to My Watchlist",
    "remove_my": "Remove from My Watchlist",
    "promote": "Promote to My Watchlist",
}


def card_lines(s: Suggestion) -> list[str]:
    who = "🤖 " if s.is_agent else ""
    head = f"{who}<b>{escape(s.symbol)}</b> ({escape(s.cap.title())}) · {escape(VERB.get(s.action, s.action))}"
    return [head, f"  {escape(s.reason[:160])}", f"  expires {s.expires_on:%d %b}"]


def render_suggestion_cards(pending: Sequence[Suggestion], *, max_cards: int) -> Message | None:
    if not pending:
        return None
    shown = list(pending)[:max_cards]
    lines = [f"🗂 <b>Watchlist suggestions</b> — {len(pending)} waiting"]
    buttons: list[list[Button]] = []
    for s in shown:
        lines.extend(card_lines(s))
        buttons.append(
            [
                Button(f"✅ {s.symbol}", "a", s.sugg_id),
                Button("❌", "r", s.sugg_id),
                Button("💤 30d", "s", s.sugg_id),
            ]
        )
    if len(pending) > len(shown):
        lines.append(f"… +{len(pending) - len(shown)} more in the app")
    return Message(
        "watchlist_suggestions", fit_lines(lines, keep_tail=0), False, buttons,
        [s.sugg_id for s in shown],
    )  # fmt: skip
