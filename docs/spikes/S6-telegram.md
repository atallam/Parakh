# Spike ⑥: Telegram adapter

- **Date:** 29 Sep 2026 · **Code kept:** `src/parakh/notify/telegram.py` (`Notifier` interface + `TelegramNotifier`)

## Result

- Adapter built and tested against a mocked Bot API (`tests/unit/test_telegram.py`): HTML with escaping (M&M), silent sends, one retry on 429, the token never appears in errors, over-long messages refused.
- **Live send from your PC: done (29 Sep 2026, 11:26 IST).** `TELEGRAM_CHAT_ID` had been removed from `.env` in an edit; after you messaged the bot, Claude read the ID from `getUpdates` and wrote it back to `.env` without printing it. The adapter then delivered a silent HTML test message (message id 10), with `M&M <test>` escaped correctly.

## Status

Closed. Backlog BL-02 done.
