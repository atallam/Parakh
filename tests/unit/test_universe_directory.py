"""The staged universe (F01 full): directory CSVs, rollout stages, strict row validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakh.configs import load_all
from parakh.configs.directory import STAGES, import_rows, load_directory, read_cap

HEADER = "symbol,isin,name,sector,profile,listed_on\n"
ROW = "TATAPOWER,INE245A01021,Tata Power Co Ltd,Utilities,standard,1996-01-01\n"


def test_stages_add_caps_in_order() -> None:
    assert STAGES["pilot"] == () and STAGES["mid"] == ("mid",)
    assert STAGES["mid_large"] == ("mid", "large") and STAGES["all"] == ("mid", "large", "small")


def test_the_committed_rollout_is_a_known_stage_and_keeps_the_pilot() -> None:
    u = load_all().universe
    assert u.rollout in STAGES
    assert {s.isin for s in u.pilot} <= {s.isin for s in u.active}


def test_the_committed_directory_files_are_valid_and_unique() -> None:
    from parakh.config import config_dir

    root = config_dir() / load_all().universe.directory
    rows = load_directory(root, "all")
    assert len({s.isin for s in rows}) == len(rows) and len({s.symbol for s in rows}) == len(rows)
    by_cap = {c: sum(1 for s in rows if s.cap == c) for c in ("large", "mid", "small")}
    assert by_cap["large"] <= 100 and by_cap["mid"] <= 150 and by_cap["small"] <= 250
    assert sum(by_cap.values()) >= 400  # the 30 Jun 2026 AMFI split: 100 + 148 + 250


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
    priced = {s.symbol for s in wide.priced}
    assert {s.symbol for s in base.pilot} <= priced and "TATAPOWER" in priced
    assert wide.by_isin("INE245A01021") is not None
    # AC-F01.5: the panel widens the priced set only; the analysed (coverage) set is unchanged
    assert {s.symbol for s in wide.active} == {s.symbol for s in base.pilot}
    assert "TATAPOWER" in {s.symbol for s in wide.panel}
    assert not {s.isin for s in wide.panel} & {s.isin for s in wide.coverage}


def test_only_price_paths_may_read_the_panel() -> None:
    """AC-F01.5: `universe.priced` and `universe.panel` are for price loading and calibration only.
    A new caller outside this allow-list would put a panel stock on an analysis path."""
    root = Path(__file__).resolve().parents[2] / "src" / "parakh"
    allowed = {
        "configs/models.py",
        "orchestration/prices.py",
        "cli.py",  # the `prices` command
        "cli_calibration.py",  # momentum calibration on the panel's price history
        "cli_watchlist.py",  # `universe stage` report
    }
    hits = {
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*.py")
        if any(t in p.read_text(encoding="utf-8") for t in ("universe.priced", "universe.panel"))
    }
    assert hits <= allowed, f"panel read outside the allow-list: {sorted(hits - allowed)}"


def _amfi_xlsx(path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "FINAL"
    ws.append(
        [
            "Average Market Capitalization of listed companies during the six months ended 30 June 2026"
        ]
    )
    ws.append(
        [
            "Sr. No.",
            "Company name",
            "ISIN",
            "BSE Symbol",
            "BSE Avg",
            "NSE Symbol",
            "NSE Avg",
            "MSEI Symbol",
            "MSEI Avg",
            "Average of All Exchanges (Rs. Cr.)",
            "Categorization as per SEBI Circular dated Oct 6, 2017",
        ]
    )
    rows = [
        ("Reliance Industries Ltd", "INE002A01018", "RELIANCE", "Large Cap"),
        ("HDFC Bank Ltd.", "INE040A01034", "HDFCBANK", "Large Cap"),
        ("Bse Only Ltd", "INE745G01043", "-", "Mid Cap"),
        ("Cipla Ltd.", "INE059A01026", "CIPLA", "Mid Cap"),
        ("Small One Ltd", "INE177A01018", "SMALL1", "Small Cap"),
        ("Small Two Ltd", "INE616N01034", "SMALL2", "Small Cap"),
        ("Small Three Ltd", "INE903U01023", "SMALL3", "Small Cap"),
    ]
    for i, (name, isin, nse, cat) in enumerate(rows, start=1):
        ws.append([i, name, isin, nse, 1000.0 - i, nse, 1000.0 - i, "-", None, 1000.0 - i, cat])
    wb.save(path)


def test_one_amfi_file_fills_all_three_caps_and_skips_bse_only_stocks(tmp_path: Path) -> None:
    from parakh.configs.directory import import_amfi

    src = tmp_path / "amfi.xlsx"
    _amfi_xlsx(src)
    counts = import_amfi(src, tmp_path / "dir", small_count=2)
    assert counts == {
        "large": 2,
        "mid": 1,
        "small": 2,
    }  # the BSE-only mid is skipped, small is capped
    assert [s.symbol for s in read_cap(tmp_path / "dir" / "small.csv", "small")] == [
        "SMALL1",
        "SMALL2",
    ]
    assert "INE745G01043" not in (tmp_path / "dir" / "mid.csv").read_text(encoding="utf-8")
