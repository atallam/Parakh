"""TOOL.reports.* / TOOL.analytics.* through the gateway, resources and prompts (F24; AC-F24.2).

One pilot run is shared by the module; tools read it from PARAKH_OUTPUT_DIR.
"""

from __future__ import annotations

import json

import pytest

from parakh import config
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.mcp.middleware import Gateway
from parakh.mcp.registry import TOOLS
from parakh.registry import discover
from parakh.services import report_service as svc
from tests.unit.test_reports import HOLD, months


@pytest.fixture(scope="module")
def pilot_root(tmp_path_factory):
    _, _, tmp = months(tmp_path_factory.mktemp("mcp_pilot"), 2)
    return tmp


@pytest.fixture
def root(pilot_root, monkeypatch):
    monkeypatch.setenv("PARAKH_OUTPUT_DIR", str(pilot_root))
    config.get_settings.cache_clear()
    yield pilot_root
    config.get_settings.cache_clear()


def call(tool: str, args: dict, client: str = "claude:desktop"):
    discover()
    gw = Gateway.for_client(client)
    return gw, gw.invoke(TOOLS[f"TOOL.{tool}"], args)


def test_reports_and_analytics_tools_are_registered_read_only() -> None:
    discover()
    names = {
        "reports.get_stock",
        "reports.what_changed",
        "reports.segment_summary",
        "reports.get_history",
        "analytics.explain_verdict",
        "analytics.list_catalogue",
    }
    assert names <= {t.id.removeprefix("TOOL.") for t in TOOLS.values()}
    assert all(TOOLS[f"TOOL.{n}"].tier == "R" for n in names)


@pytest.mark.ac("AC-F24.2")
def test_mcp_and_cli_return_the_same_stock_view(root) -> None:
    gw, out = call("reports.get_stock", {"symbol_or_isin": "HDFCBANK"})
    direct = svc.get_stock("HDFCBANK")
    assert out.found and out.model_dump() == direct.model_dump()  # type: ignore[attr-defined]
    events = [
        e for e in get_sink().events_for_run(gw.ctx.run_id) if e.event_type == AUD.MCP_TOOL_CALL
    ]
    assert len(events) == 1 and events[0].details["tool_id"] == "TOOL.reports.get_stock"


@pytest.mark.ac("AC-F24.2")
def test_mcp_and_cli_return_the_same_explanation_and_history(root) -> None:
    _, ex = call("analytics.explain_verdict", {"symbol_or_isin": HOLD})
    assert ex.model_dump() == svc.explain(HOLD).model_dump()  # type: ignore[attr-defined]
    _, hist = call("reports.get_history", {"symbol_or_isin": "HDFCBANK"})
    assert hist.model_dump() == svc.get_history("HDFCBANK").model_dump()  # type: ignore[attr-defined]


@pytest.mark.ac("AC-F22.1")
def test_a_held_stock_over_mcp_shows_weight_and_percent_only(root) -> None:
    _, out = call("reports.get_stock", {"symbol_or_isin": "HDFCBANK"})
    text = json.dumps(out.model_dump(mode="json"), ensure_ascii=False)  # type: ignore[attr-defined]
    pos = out.view["position"]  # type: ignore[attr-defined]
    assert pos is not None and pos["weight_pct"] is not None
    for banned in ("quantity", "cost_inr", "tax_if_sold_now_inr", "value_inr", "pnl_inr", "123.0"):
        assert banned not in text, banned


def test_unknown_stock_or_period_is_a_message_not_an_error(root) -> None:
    _, out = call("reports.get_stock", {"symbol_or_isin": "NOPE"})
    assert out.found is False and "not in the pilot universe" in out.message  # type: ignore[attr-defined]
    _, out = call("reports.get_stock", {"symbol_or_isin": "HDFCBANK", "period": "1999-01"})
    assert out.found is False and "Available:" in out.message  # type: ignore[attr-defined]


def test_what_changed_and_segment_summary(root) -> None:
    _, wc = call("reports.what_changed", {})
    assert wc.model_dump()  # type: ignore[attr-defined]
    _, seg = call("reports.segment_summary", {"cap": "large"})
    assert seg.found  # type: ignore[attr-defined]


def test_catalogue_lists_registered_items(root) -> None:
    _, out = call("analytics.list_catalogue", {"kind": "metric"})
    assert out.items  # type: ignore[attr-defined]


def test_resources_return_masked_documents(root) -> None:
    snap = json.loads(svc.masked_snapshot_json("HDFCBANK"))
    assert "quantity" not in json.dumps(snap) and snap["symbol"] == "HDFCBANK"
    md = svc.report_markdown("HDFCBANK")
    assert "## 0. TL;DR" in md and "123.0" not in md
    assert "[[HDFCBANK]]" in svc.segment_markdown("large")
    assert "Feature" in svc.plan_doc("08_FEATURE_SPEC") or svc.plan_doc("08_FEATURE_SPEC")


def test_prompts_and_resources_are_registered() -> None:
    import asyncio

    from parakh.mcp.server import build_server

    async def go() -> None:
        server = build_server("claude:code")
        prompts = {p.name for p in await server.list_prompts()}
        assert {"monthly-review", "explain"} <= prompts
        templates = {
            str(t.uri_template if hasattr(t, "uri_template") else t.uriTemplate)
            for t in await server.list_resource_templates()
        }
        assert any("snapshot" in t for t in templates) and any("plan" in t for t in templates)

    asyncio.run(go())
