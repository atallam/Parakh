"""Telegram adapter against a mocked Bot API (spike ⑥; plan 14 L4 notifier mock). T-NTF-01…"""

from __future__ import annotations

import json

import httpx

from parakh.notify.telegram import MAX_LEN, TelegramNotifier, escape

TOKEN = "123456789:" + "A" * 35


def _client(responses: list[httpx.Response], seen: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        return responses.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sends_html_and_returns_the_message_id() -> None:
    """T-NTF-01"""
    seen: list[dict] = []
    ok = httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})
    d = TelegramNotifier(TOKEN, "999", _client([ok], seen)).send(
        f"<b>{escape('M&M')}</b>", silent=True
    )
    assert d.ok and d.provider_msg_id == "42"
    body = seen[0]["body"]
    assert body["parse_mode"] == "HTML" and body["disable_notification"] is True
    assert body["text"] == "<b>M&amp;M</b>"


def test_429_is_retried_once_after_retry_after() -> None:
    """T-NTF-02"""
    seen: list[dict] = []
    limited = httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 0}})
    ok = httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
    assert TelegramNotifier(TOKEN, "1", _client([limited, ok], seen)).send("hi").ok
    assert len(seen) == 2


def test_errors_never_contain_the_token() -> None:
    """T-NTF-03 (AC-F21.11)"""
    seen: list[dict] = []
    bad = httpx.Response(401, json={"ok": False, "description": f"Unauthorized for bot{TOKEN}"})
    d = TelegramNotifier(TOKEN, "1", _client([bad], seen)).send("hi")
    assert not d.ok and d.error is not None and TOKEN not in d.error


def test_over_long_messages_are_refused_before_sending() -> None:
    """T-NTF-04"""
    seen: list[dict] = []
    d = TelegramNotifier(TOKEN, "1", _client([], seen)).send("x" * (MAX_LEN + 1))
    assert not d.ok and seen == []
