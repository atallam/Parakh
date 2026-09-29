# Spike ⑥: Telegram adapter

- **Date:** 29 Sep 2026 · **Code kept:** `src/parakh/notify/telegram.py` (`Notifier` interface + `TelegramNotifier`)

## Result

- Adapter built and tested against a mocked Bot API (`tests/unit/test_telegram.py`): HTML with escaping (M&M), silent sends, one retry on 429, the token never appears in errors, over-long messages refused.
- **Live send from your PC: pending.** The token loads, but `.env` no longer has `TELEGRAM_CHAT_ID` (the file was edited at 00:02 IST on 29 Sep and shrank from 165 to 140 bytes). `getUpdates` had no recent messages to recover it from.

## To close

Add `TELEGRAM_CHAT_ID=…` back to `.env`, or send any message to @Parakh_avinash_bot and ask Claude to re-run the spike. Not a blocker for Phase 1 (notifications arrive in Phase 3).
