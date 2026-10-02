"""AMFI list, index constituents and the reference load job (recorded files). T-REF-01…"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from parakh.adapters.reference import (
    ReferenceFormatError,
    parse_amfi_list,
    parse_index_constituents,
)
from parakh.configs import load_all
from parakh.orchestration.reference import load_reference, membership_changes

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
AMFI = (SRC / "amfi" / "AverageMarketCapitalization30Jun2026.xlsx").read_bytes()
INDEX = {
    "NIFTY 100": (SRC / "niftyindices" / "ind_nifty100list_2026-09-29.csv").read_bytes(),
    "NIFTY MIDCAP 150": (
        SRC / "niftyindices" / "ind_niftymidcap150list_2026-09-29.csv"
    ).read_bytes(),
    "NIFTY SMALLCAP 250": (
        SRC / "niftyindices" / "ind_niftysmallcap250list_2026-09-29.csv"
    ).read_bytes(),
}
BUNDLE = load_all()
ASOF = dt.date(2026, 9, 29)
ATHER, MAZDOCK, GROWW, SHADOWFAX = "INE0LEZ01016", "INE249Z01020", "INE0HOQ01053", "INE12UN01015"


class MemoryWriter:
    def __init__(self) -> None:
        self.caps: list[dict[str, Any]] = []
        self.members: list[dict[str, Any]] = []

    def open_memberships(self) -> list[dict[str, Any]]:
        return [m for m in self.members if m.get("valid_to") is None]

    def write_reference(self, caps, joins, leaves) -> None:  # type: ignore[no-untyped-def]
        self.caps += caps
        self.members += [dict(j) for j in joins]
        for leave in leaves:
            for m in self.members:
                if (m["index_id"], m["isin"]) == (leave["index_id"], leave["isin"]) and m.get(
                    "valid_to"
                ) is None:
                    m["valid_to"] = leave["valid_to"]


def test_amfi_list_ranks_and_buckets() -> None:
    """T-REF-01: SEBI's 100 / 150 / rest split, and the period the list covers."""
    amfi = parse_amfi_list(AMFI)
    rows = amfi.by_isin()
    assert amfi.period_end == dt.date(2026, 6, 30) and len(amfi.rows) > 5000
    assert (rows[ATHER].rank, rows[ATHER].bucket) == (260, "small")
    assert (rows[MAZDOCK].rank, rows[MAZDOCK].bucket) == (112, "mid")
    assert {r.bucket for r in amfi.rows if r.rank <= 100} == {"large"}
    with pytest.raises(ReferenceFormatError):
        parse_index_constituents(b"a,b\n1,2\n", "NIFTY 100")


def test_config_caps_agree_with_amfi_and_membership_is_stored() -> None:
    """T-REF-02: every pilot's config bucket equals AMFI's; index membership differs from it."""
    writer = MemoryWriter()
    ctx, outcome, report = load_reference(BUNDLE, AMFI, INDEX, ASOF, writer)
    caps = [r for r in report.dq if r.check_id == "DQ.reference.cap_bucket"]
    assert len(caps) == 7 and {r.status for r in caps} == {"pass"}
    assert report.membership[MAZDOCK] == ["NIFTY 100"]  # AMFI mid cap, yet in the Nifty 100
    assert report.membership[GROWW] == ["NIFTY MIDCAP 150"]  # AMFI large cap
    assert report.membership[SHADOWFAX] == []  # rank 589: outside the Smallcap 250 (D9)
    assert len(writer.caps) == 7 and len(writer.members) == 6
    sizes = {
        r.detail["index"]: r.status
        for r in report.dq
        if r.check_id.startswith("DQ.reference.index_size_")
    }
    assert sizes["NIFTY SMALLCAP 250"] == "warn"  # 251 rows on 29 Sep 2026
    assert report.status == "warn"


def test_a_wrong_config_bucket_fails() -> None:
    """T-REF-03: the config is corrected by a reviewed change, never silently."""
    pilot = [
        s.model_copy(update={"cap": "mid"}) if s.isin == ATHER else s for s in BUNDLE.universe.pilot
    ]
    bundle = dataclasses.replace(
        BUNDLE, universe=BUNDLE.universe.model_copy(update={"pilot": pilot})
    )
    _, _, report = load_reference(bundle, AMFI, {}, ASOF)
    bad = [r for r in report.dq if r.status == "fail"]
    assert [(r.isin, r.detail["amfi"]) for r in bad] == [(ATHER, "small")]


@pytest.mark.ac("AC-F01.3")
def test_membership_history_opens_and_closes() -> None:
    """T-REF-04: point-in-time membership; a reload changes nothing."""
    writer = MemoryWriter()
    load_reference(BUNDLE, AMFI, INDEX, ASOF, writer)
    _, _, again = load_reference(BUNDLE, AMFI, INDEX, ASOF + dt.timedelta(days=30), writer)
    assert again.joins == [] and again.leaves == []
    universe = {s.isin for s in BUNDLE.universe.pilot}
    later = dt.date(2027, 3, 31)
    joins, leaves = membership_changes(
        {"NIFTY 100": {GROWW}, "NIFTY MIDCAP 150": {MAZDOCK}},
        writer.open_memberships(),
        universe,
        later,
    )
    assert {(j["index_id"], j["isin"]) for j in joins} == {
        ("NIFTY 100", GROWW),
        ("NIFTY MIDCAP 150", MAZDOCK),
    }
    assert ("NIFTY 100", MAZDOCK) in {(x["index_id"], x["isin"]) for x in leaves}
    assert all(x["index_id"] != "NIFTY SMALLCAP 250" for x in leaves)  # that file wasn't loaded


def test_dq_results_have_unique_keys() -> None:
    """T-REF-05: (check_id, isin) is the stored key, so no two results may share it."""
    _, _, report = load_reference(BUNDLE, AMFI, INDEX, ASOF, MemoryWriter())
    keys = [(r.check_id, r.isin) for r in report.dq]
    assert len(keys) == len(set(keys))
