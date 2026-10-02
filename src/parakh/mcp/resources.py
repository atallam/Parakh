"""parakh:// resources and the /monthly-review and /explain prompts (plan 15 §4.3).

Resources are read-only and masked like the tools: a held stock shows weight and percentages,
never quantity or ₹ amounts. Prompts only tell Claude which tools to call and in what order.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from parakh.services import report_service as svc


def register(server: MCPServer) -> None:
    @server.resource(
        "parakh://stock/{symbol}/snapshot/{period}",
        name="snapshot",
        mime_type="application/json",
        description="The canonical monthly snapshot for a stock (position masked to weight and percentages).",
    )
    def snapshot(symbol: str, period: str) -> str:
        return svc.masked_snapshot_json(symbol, None if period == "latest" else period)

    @server.resource(
        "parakh://stock/{symbol}/report/{period}",
        name="report",
        mime_type="text/markdown",
        description="The monthly Markdown report for a stock (position masked). Use period 'latest' for the newest.",
    )
    def report(symbol: str, period: str) -> str:
        return svc.report_markdown(symbol, None if period == "latest" else period)

    @server.resource(
        "parakh://segment/{cap}/summary/{period}",
        name="segment_summary",
        mime_type="text/markdown",
        description="The monthly segment summary for large, mid or small cap.",
    )
    def segment(cap: str, period: str) -> str:
        return svc.segment_markdown(cap, None if period == "latest" else period)

    @server.resource(
        "parakh://plan/{doc}",
        name="plan_doc",
        mime_type="text/markdown",
        description="A framework plan document (e.g. 08_FEATURE_SPEC) so a task can load its owner doc.",
    )
    def plan(doc: str) -> str:
        return svc.plan_doc(doc)

    @server.prompt(name="monthly-review", description="What needs my attention this month?")
    def monthly_review() -> str:
        return (
            "Do my monthly Parakh review. Call reports_what_changed first and report verdict changes, "
            "thesis changes and flagged checks for stocks I own before anything else. For each owned stock "
            "with a change, call reports_get_stock and give the TL;DR, the verdict chip and the first "
            "'what changed' bullet. Then list non-owned upgrades. Quote scores with their as-of date and "
            "run_id. Say plainly which checks could not run (UNKNOWN); never describe them as clean. "
            "Do not give price targets."
        )

    @server.prompt(name="explain", description="Walk through why a stock has its latest verdict.")
    def explain(symbol: str) -> str:
        return (
            f"Explain the latest {symbol} verdict in plain words. Call analytics_explain_verdict for {symbol}, "
            "then walk the tree: the policy rule, the value and momentum bands, the biggest sub-scores, "
            "and any driver of change. Name the metrics with their sources and as-of dates, and say what "
            "is N/A and why. Do not recompute anything."
        )
