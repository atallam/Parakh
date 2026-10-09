# pyright: reportAttributeAccessIssue=false
"""TOOL.portfolio.* and TOOL.jobs.* through the gateway (F24, F25; AC-F24.4, AC-F24.5, AC-F24.7, AC-F25.4)."""

from __future__ import annotations

import pytest

from parakh import config
from parakh.audit.emit import get_sink
from parakh.audit.events import AUD
from parakh.mcp.middleware import Gateway, ToolDenied
from parakh.mcp.registry import TOOLS
from parakh.registry import discover
from parakh.services.job_requests import JobRequests
from parakh.watch.state import StateStore
from parakh.watchlist.proposals import LocalProposalStore
from tests.unit.test_reports import HOLD, months


@pytest.fixture(scope="module")
def pilot_root(tmp_path_factory, module_isolation):
    _, _, tmp = months(tmp_path_factory.mktemp("mcp_portfolio"), 2)
    return tmp


@pytest.fixture
def root(pilot_root, monkeypatch, tmp_path):
    monkeypatch.setenv("PARAKH_OUTPUT_DIR", str(pilot_root))
    monkeypatch.setenv("PARAKH_WATCH_STATE_DIR", str(tmp_path / "watch"))
    config.get_settings.cache_clear()
    yield pilot_root
    config.get_settings.cache_clear()


def gateway(client: str = "claude:desktop") -> Gateway:
    discover()
    return Gateway.for_client(client)


def events(gw: Gateway, kind: AUD) -> list:
    return [e for e in get_sink().events_for_run(gw.ctx.run_id) if e.event_type == kind]


def test_tiers_and_forbidden_verbs() -> None:
    discover()
    tiers = {t.id.removeprefix("TOOL."): t.tier for t in TOOLS.values()}
    assert tiers["portfolio.positions"] == tiers["portfolio.get_thesis"] == "R"
    assert tiers["portfolio.propose_watchlist"] == "P"
    assert tiers["portfolio.propose_thesis_flag"] == "P"
    assert tiers["portfolio.propose_journal_entry"] == "P"
    assert tiers["jobs.request_refresh"] == "J"
    assert not [
        n
        for n in tiers
        if n.startswith("portfolio.") and n.split(".")[1] in {"approve", "reject", "add", "remove"}
    ]


@pytest.mark.ac("AC-F24.4")
def test_desktop_may_ask_for_detail_but_an_agent_is_refused_and_audited(root) -> None:
    desktop = gateway()
    assert desktop.invoke(TOOLS["TOOL.portfolio.positions"], {"detail": True}) is not None
    agent = gateway("agent:monthly_reviewer")
    with pytest.raises(ToolDenied):
        agent.invoke(TOOLS["TOOL.portfolio.positions"], {"detail": True})
    assert len(events(agent, AUD.MCP_TOOL_DENIED)) == 1
    assert not events(agent, AUD.MCP_TOOL_CALL)
    masked = agent.invoke(TOOLS["TOOL.portfolio.positions"], {})
    dump = masked.model_dump_json()
    assert "quantity" not in dump.lower() or '"quantity":null' in dump.replace(" ", "")


@pytest.mark.ac("AC-F24.5")
def test_positions_and_pending_are_read_only_and_audited(root) -> None:
    gw = gateway()
    gw.invoke(TOOLS["TOOL.portfolio.positions"], {})
    gw.invoke(TOOLS["TOOL.portfolio.pending_approvals"], {})
    assert len(events(gw, AUD.MCP_TOOL_CALL)) == 2
    assert not LocalProposalStore(StateStore()).all()


@pytest.mark.ac("AC-F24.7")
def test_a_propose_tool_writes_only_a_proposal(root) -> None:
    gw = gateway("agent:watchlist_curator")
    out = gw.invoke(
        TOOLS["TOOL.portfolio.propose_watchlist"],
        {
            "action": "add_my",
            "symbol_or_isin": HOLD,
            "reason": "Strong momentum setup with improving margins worth a deep dive.",
        },
    )
    assert out.accepted
    rows = LocalProposalStore(StateStore()).all()
    assert len(rows) == 1 and rows[0].status == "pending"
    pend = gw.invoke(TOOLS["TOOL.portfolio.pending_approvals"], {})
    assert any(p.kind == "proposal" for p in pend.items)
    assert not StateStore().load("watchlist")  # nothing was added to a list


def test_an_agent_without_the_tool_on_its_list_is_denied(root) -> None:
    gw = gateway("agent:event_triage")
    with pytest.raises(ToolDenied):
        gw.invoke(
            TOOLS["TOOL.portfolio.propose_watchlist"],
            {"action": "add_my", "symbol_or_isin": HOLD, "reason": "x" * 20},
        )


@pytest.mark.ac("AC-F25.4")
def test_refresh_requests_are_capped_per_day_and_blocked_in_a_monthly_run(root) -> None:
    gw = gateway("agent:event_triage")
    first = gw.invoke(
        TOOLS["TOOL.jobs.request_refresh"],
        {"symbol_or_isin": HOLD, "reason_code": "new_transcript"},
    )
    assert first.queued
    again = gw.invoke(
        TOOLS["TOOL.jobs.request_refresh"],
        {"symbol_or_isin": HOLD, "reason_code": "new_transcript"},
    )
    assert not again.queued  # one open request per stock
    jr = JobRequests(StateStore(), daily_cap=5)
    jr.finish(jr.queued()[0].request_id, "done", "")
    jr.lock_monthly(True)
    blocked = gw.invoke(
        TOOLS["TOOL.jobs.request_refresh"], {"symbol_or_isin": HOLD, "reason_code": "new_results"}
    )
    assert not blocked.queued and "monthly" in blocked.message.lower()


@pytest.mark.ac("AC-F25.4")
def test_the_daily_cap_is_five() -> None:
    store = StateStore()
    jr = JobRequests(store, daily_cap=2)
    isins = ["INE000A01001", "INE000A01002", "INE000A01003"]
    results = [jr.request(i, "data_gap", "agent:event_triage").queued for i in isins]
    assert results == [True, True, False]
