// Telegram webhook (Phase 4, plan 03 §4.3). It verifies Telegram's secret header, then queues the tap
// in `ui_actions`; Parakh's own job applies it through the watchlist service (one audit trail).
// It never reads or writes the watchlist, never answers with data, and ignores everything but taps.
//
// Secrets (supabase secrets set): TELEGRAM_WEBHOOK_SECRET, OWNER_CHAT_ID. SUPABASE_URL and
// SUPABASE_SERVICE_ROLE_KEY are provided by the platform.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";

const ok = () => new Response("ok", { status: 200 });

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("not found", { status: 404 });
  if (req.headers.get("x-telegram-bot-api-secret-token") !== Deno.env.get("TELEGRAM_WEBHOOK_SECRET")) {
    return new Response("forbidden", { status: 403 });
  }
  const update = await req.json().catch(() => null);
  const cb = update?.callback_query;
  if (!cb) return ok(); // messages and commands are handled by the polling bot
  if (String(cb.message?.chat?.id) !== Deno.env.get("OWNER_CHAT_ID")) return ok(); // silent drop
  const data = String(cb.data ?? "");
  if (data.length === 0 || data.length > 64) return ok();

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { error } = await db.from("ui_actions").upsert(
    { action_id: `tg-${update.update_id}`, channel: "telegram", kind: "button", payload: data, update_id: update.update_id },
    { onConflict: "update_id", ignoreDuplicates: true },
  );
  if (error) return new Response("retry", { status: 500 }); // Telegram retries; the unique index makes it safe
  return ok();
});
