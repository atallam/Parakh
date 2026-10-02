"""Compare the analyst oracle with the Python value metrics (UAT-0, plan 14 §4.1).

Builds the oracle workbook from three Screener exports, recalculates it with LibreOffice, runs the
real `MET.value.*` code on the parsed golden facts at the same price, and writes:
  - the final workbook with a COMPARE sheet (formulas and cached values),
  - `tests/oracles/golden_expected.json` (derived oracle values only; safe to commit),
  - `docs/uat/UAT-0_oracle_compare.md` (one row per disagreement).

Usage: python tools/compare_oracle.py "HDFC Bank.xlsx" "Interglobe Aviat.xlsx" "M & M.xlsx" [-o out.xlsx]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

import build_oracle as bo  # noqa: E402

from parakh.analytics.metrics.value import compute_all  # noqa: E402
from parakh.analytics.value_build import build_inputs  # noqa: E402
from parakh.analytics.value_calc import VCalc  # noqa: E402
from parakh.lenses.value import default_settings  # noqa: E402

GOLD = REPO / "tests" / "fixtures" / "golden"
REL_TOL, ABS_TOL = 0.005, 0.05
RED, GREEN, AMBER = (PatternFill("solid", fgColor=c) for c in ("F8CBAD", "C6E0B4", "FFE699"))


def recalc(src: Path, out_dir: Path) -> Path:
    """LibreOffice headless recalculation; the result keeps formulas and caches their values."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(out_dir), str(src)],
        check=True,
        capture_output=True,
        timeout=240,
    )
    return out_dir / src.name


def oracle_values(path: Path) -> dict[str, dict[str, tuple[Any, str]]]:
    wb = openpyxl.load_workbook(path, data_only=True)
    out: dict[str, dict[str, tuple[Any, str]]] = {}
    for sym, *_ in bo.STOCKS:
        ws = wb[f"ORACLE_{sym}"]
        vals: dict[str, tuple[Any, str]] = {"__price__": (ws["B4"].value, "")}
        for r in range(14, 72):
            ident = ws.cell(r, 1).value
            if isinstance(ident, str) and ident.startswith("MET.value."):
                vals[ident] = (ws.cell(r, 2).value, str(ws.cell(r, 3).value or ""))
        out[sym] = vals
    return out


def code_values(
    isin: str, symbol: str, price: float
) -> tuple[dict[str, float | None], dict[str, str]]:
    rows = json.loads((GOLD / isin / "facts.json").read_text(encoding="utf-8"))["rows"]
    inp = build_inputs(
        isin, symbol, "large", "standard", dt.date(2026, 10, 3), price, rows, default_settings()
    )
    return compute_all(VCalc(inp, default_settings()))


def judge(oracle: Any, unit: str, code: float | None, why: str) -> tuple[str, str]:
    num = isinstance(oracle, int | float) and not isinstance(oracle, bool)
    if isinstance(oracle, str) and oracle.startswith("INPUT NEEDED"):
        return "OPEN", "needs an input the export does not hold"
    if not num:
        return (
            ("MATCH", "both N/A")
            if code is None
            else ("DIFF", f"oracle {oracle}; code gives a number")
        )
    if code is None:
        return "DIFF", f"code N/A ({why})"
    if unit == "score":
        gap = abs(code - float(oracle))
        return ("MATCH", "") if gap <= ABS_TOL else ("DIFF", f"abs gap {gap:.3f}")
    base = abs(float(oracle)) or 1e-12
    gap = abs(code - float(oracle)) / base
    return ("MATCH", "") if gap <= REL_TOL else ("DIFF", f"rel gap {gap:.2%}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("exports", nargs=3, type=Path)
    ap.add_argument("-o", "--out", type=Path, default=bo.DEFAULT_OUT)
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    base = tmp / "oracle.xlsx"
    bo.build(a.exports, base)
    ov = oracle_values(recalc(base, tmp / "r1"))

    rows: list[
        tuple[str, str, Any, float | None, str, str]
    ] = []  # sym, id, oracle, code, verdict, note
    expected: dict[str, dict[str, Any]] = {}
    for sym, isin, *_ in bo.STOCKS:
        price = float(ov[sym]["__price__"][0])  # type: ignore[arg-type]
        vals, reasons = code_values(isin, sym, price)
        expected[isin] = {"symbol": sym, "price": price}
        for ident, (o, unit) in ov[sym].items():
            if ident == "__price__":
                continue
            c = vals.get(ident)
            verdict, note = judge(o, unit, c, reasons.get(ident, ""))
            rows.append((sym, ident, o, c, verdict, note))
            expected[isin][ident] = (
                o if isinstance(o, int | float) and not isinstance(o, bool) else None
            )
        for ident in sorted(set(vals) - set(ov[sym])):
            if vals[ident] is not None:
                rows.append(
                    (
                        sym,
                        ident,
                        "(not in oracle)",
                        vals[ident],
                        "NOT IN ORACLE",
                        "code gives a value; oracle has no row",
                    )
                )

    wb = openpyxl.load_workbook(base)
    ws = wb.create_sheet("COMPARE", 1)
    for j, h in enumerate(
        [
            "Stock",
            "Metric",
            "Oracle",
            "Code",
            "Result",
            "Note",
            "Decision: oracle wrong / code wrong / definition",
        ],
        1,
    ):
        c = ws.cell(1, j, h)
        c.font, c.fill = Font(color="FFFFFF", bold=True), PatternFill("solid", fgColor="1F3A5F")
    for i, (sym, ident, o, c, verdict, note) in enumerate(rows, 2):
        for j, v in enumerate([sym, ident, o, c, verdict, note], 1):
            ws.cell(i, j, v)
        ws.cell(i, 5).fill = {"MATCH": GREEN, "DIFF": RED}.get(verdict, AMBER)
        if verdict == "DIFF":
            ws.cell(i, 7).fill = bo.NEED
    for col, wd in zip("ABCDEFG", (12, 38, 22, 22, 14, 52, 40), strict=False):
        ws.column_dimensions[col].width = wd
    ws.freeze_panes = "A2"
    wb.save(tmp / "oracle_cmp.xlsx")
    final = recalc(tmp / "oracle_cmp.xlsx", tmp / "r2")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(final, a.out)

    (a.out.parent / "golden_expected.json").write_text(
        json.dumps(
            {
                "as_of_basis": "Screener export Current Price",
                "tolerance": {"rel": REL_TOL, "abs_score": ABS_TOL},
                "stocks": expected,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    diffs = [r for r in rows if r[4] in ("DIFF", "NOT IN ORACLE")]
    tally = {
        k: sum(1 for r in rows if r[4] == k) for k in ("MATCH", "DIFF", "OPEN", "NOT IN ORACLE")
    }
    md = REPO / "docs" / "uat" / "UAT-0_oracle_compare.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# UAT-0 oracle vs code",
        "",
        f"Generated {dt.date.today()} by `tools/compare_oracle.py`. Tally: "
        + ", ".join(f"{k} {v}" for k, v in tally.items()),
        "",
        "| Stock | Metric | Oracle | Code | Result | Note |",
        "|---|---|---|---|---|---|",
    ]
    for sym, ident, o, c, verdict, note in diffs:
        f = lambda x: f"{x:.4g}" if isinstance(x, float) else str(x)  # noqa: E731
        lines.append(
            f"| {sym} | {ident.removeprefix('MET.value.')} | {f(o)} | {f(c)} | {verdict} | {note} |"
        )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(tally, "->", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
