"""The staged universe (F01 full): directory CSVs, rollout stages, strict row validation."""

from __future__ import annotations

import pytest

from parakh.configs import load_all
from parakh.configs.directory import STAGES, import_rows, load_directory, read_cap

HEADER = "symbol,isin,name,sector,profile,listed_on\n"
ROW = "TATAPOWER,INE245A01021,Tata Power Co Ltd,Utilities,standard,1996-01-01\n"


def test_stages_add_caps_in_order() -> None:
    assert STAGES["pilot"] == () and STAGES["mid"] == ("mid",)
    assert STAGES["mid_large"] == ("mid", "large") and STAGES["all"] == ("mid", "large", "small")


def test_the_default_rollout_is_the_pilot() -> None:
    u = load_all().universe
    assert u.rollout == "pilot" and u.active == u.pilot


def test_import_validates_and_round_trips(tmp_path) -> None:
    src = tmp_path / "in.csv"
    src.write_text(HEADER + ROW, encoding="utf-8")
    dest = tmp_path / "dir"
    assert import_rows(src, "mid", dest) == 1
    assert [s.symbol for s in load_directory(dest, "mid")] == ["TATAPOWER"]
    assert load_directory(dest, "pilot") == []


def test_a_bad_isin_names_its_file_and_line(tmp_path) -> None:
    f = tmp_path / "mid.csv"
    f.write_text(HEADER + ROW.replace("INE245A01021", "INE245A01022"), encoding="utf-8")
    with pytest.raises(ValueError, match=r"mid\.csv line 2"):
        read_cap(f, "mid")


def test_duplicates_are_refused(tmp_path) -> None:
    src = tmp_path / "in.csv"
    src.write_text(HEADER + ROW + ROW, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate ISIN"):
        import_rows(src, "mid", tmp_path / "d")


def test_a_rollout_stage_widens_active_but_never_drops_the_pilot(tmp_path, monkeypatch) -> None:
    (tmp_path / "universe_directory").mkdir()
    (tmp_path / "universe_directory" / "mid.csv").write_text(HEADER + ROW, encoding="utf-8")
    base = load_all().universe
    wide = base.model_copy(update={"rollout": "mid"})
    monkeypatch.setattr("parakh.config.config_dir", lambda: tmp_path)
    symbols = {s.symbol for s in wide.active}
    assert {s.symbol for s in base.pilot} <= symbols and "TATAPOWER" in symbols
    assert wide.by_isin("INE245A01021") is not None
