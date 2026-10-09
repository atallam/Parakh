"""What the Telegram bot says: snapshot views, never recomputation (plan 03 §4.3; AG-04).

The same service functions back `parakh show` and the MCP tools, so a bot reply and a report cannot
disagree. Every reply is masked: weight and P&L percentages, no amounts, and escaped for Telegram HTML.
"""

from __future__ import annotations

from pathlib import Path

from parakh.notify.telegram import escape
from parakh.services import report_service as rs
from parakh.services.watchlist import WatchlistError, WatchlistService


class ReportProviders:
    def __init__(
        self,
        root: Path | None = None,
        runs_root: Path | None = None,
        watchlist: WatchlistService | None = None,
    ) -> None:
        self.root, self.runs_root, self.watchlist = root, runs_root, watchlist

    def today(self) -> str:
        wc = rs.what_changed(root=self.root)
        if not wc.found:
            return escape(wc.message)
        if not wc.items:
            return f"📊 <b>{escape(wc.period or '')}</b>\nNothing changed since last month."
        lines = [f"📊 <b>What changed, {escape(wc.period or '')}</b>"]
        for it in wc.items[:7]:
            own = "🟢 " if it.owned else ""
            lines.append(
                f"{own}<b>{escape(it.symbol)}</b> · {escape(it.kind)}: {escape(it.text[:90])}"
            )
        if len(wc.items) > 7:
            lines.append(f"… +{len(wc.items) - 7} more in the report")
        return "\n".join(lines)

    def stock(self, query: str) -> str:
        res = rs.get_stock(query.strip(), root=self.root)
        if not res.found or res.view is None:
            return escape(res.message or f"No snapshot for {query}.")
        v = res.view
        lines = [
            f"<b>{escape(res.symbol or query)}</b> · {escape(str(v.get('chip', '')))}",
            escape(str(v.get("tldr", "")))[:300],
        ]
        if v.get("position_line"):
            lines.append(escape(str(v["position_line"])))
        return "\n".join(lines)

    def pending(self) -> str:
        if self.watchlist is None:
            return "🗂 The watchlist is not connected to the bot."
        rows = self.watchlist.pending()
        if not rows:
            return "🗂 Nothing pending."
        lines = [f"🗂 <b>{len(rows)} waiting for your decision</b>"]
        for r in rows[:7]:
            who = "🤖 " if r.is_agent else ""
            lines.append(
                f"{who}<b>{escape(r.symbol)}</b> · {escape(r.action)} · {escape(r.reason[:80])}"
            )
        if len(rows) > 7:
            lines.append(f"… +{len(rows) - 7} more in the app")
        return "\n".join(lines)

    def status(self) -> str:
        import datetime as dt

        from parakh.orchestration.watch_jobs import week_runs

        runs = week_runs(dt.date.today(), self.runs_root)
        if not runs:
            return "No job runs recorded in the last 7 days."
        ok = sum(1 for r in runs if r.status.startswith("SUCCESS"))
        last = max(runs, key=lambda r: r.finished_at)
        return f"💓 {ok}/{len(runs)} runs OK this week · last: {escape(last.mode)} {last.asof:%d %b} {escape(last.status)}"

    def resolve(self, symbol: str) -> str | None:
        sec = rs.resolve(symbol, self.root)
        return sec.isin if sec else None

    def decide(self, action: str, alert_id: str) -> str:
        """A tapped ✅ ❌ 💤 on a suggestion card. A second tap says so and changes nothing."""
        if self.watchlist is None:
            return "The watchlist is not connected to the bot."
        svc = self.watchlist
        try:
            if action == "a":
                res = svc.approve(alert_id, channel="telegram")
            elif action == "r":
                res = svc.reject(alert_id, channel="telegram")
            elif action == "s":
                res = svc.snooze(alert_id, channel="telegram")
            else:
                return "Unknown action."
        except WatchlistError as exc:
            return str(exc)
        suffix = " Add a thesis in the app." if res.needs_thesis else ""
        return res.message + suffix
