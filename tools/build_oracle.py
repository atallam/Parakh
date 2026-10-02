"""Build the UAT-0 analyst oracle workbook (plan 14 §4.1, D18).

The oracle is an *independent* implementation: Excel formulas written directly on a copy of the raw
Screener "Data Sheet", not on the Python code. For every metric it records the value (a live formula),
the formula in words, the source cells and the tolerance.

Usage:
    python tools/build_oracle.py "HDFC Bank.xlsx" "Interglobe Aviat.xlsx" "M & M.xlsx" [-o out.xlsx]

The workbook contains the raw export values, so it is NOT committed (source terms, plan 13 §8.0c);
`tools/compare_oracle.py` recalculates it and writes `tests/oracles/golden_expected.json`
(derived values only), which is committed.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "tests" / "oracles" / "golden_expected.xlsx"

# sheet key -> (symbol, isin, profile, history break, order of the three exports on the command line)
STOCKS = [
    ("HDFCBANK", "INE040A01034", "bank", dt.date(2024, 3, 31), "HDFC Ltd merger (Jul 2023)"),
    ("INDIGO", "INE646L01027", "airline / lease-heavy", None, ""),
    ("MM", "INE101A01026", "conglomerate (core standalone)", None, ""),
]

YEARS = "BCDEFGHIJK"  # FY2017 … FY2026, same letters on RAW and ORACLE sheets
HEAD = PatternFill("solid", fgColor="1F3A5F")
SUB = PatternFill("solid", fgColor="DCE6F1")
NEED = PatternFill("solid", fgColor="FFF2CC")
WHITE = Font(color="FFFFFF", bold=True)
BOLD = Font(bold=True)

# Tolerances (plan 14 §4.1): ratios and percentages ±0.5% relative; scores/points absolute.
REL = "±0.5% rel"
ABS_PP = "±0.05 abs"
EXACT = "exact"


def _raw_copy(wb: openpyxl.Workbook, name: str, src: Path) -> None:
    ws_src = openpyxl.load_workbook(src)["Data Sheet"]
    ws = wb.create_sheet(name)
    for row in ws_src.iter_rows():
        for c in row:
            if c.value is not None:
                ws[c.coordinate] = c.value
                if isinstance(c.value, dt.datetime):
                    ws[c.coordinate].number_format = "yyyy-mm-dd"
    ws.sheet_properties.tabColor = "999999"
    ws.column_dimensions["A"].width = 34


class Sheet:
    """One stock's oracle sheet: header, workings block, metric table."""

    def __init__(self, wb: openpyxl.Workbook, sym: str, isin: str, profile: str, brk, brk_why: str):
        self.ws = wb.create_sheet(f"ORACLE_{sym}")
        self.R = f"RAW_{sym}"
        self.sym, self.isin, self.profile, self.brk, self.brk_why = sym, isin, profile, brk, brk_why
        self.w: dict[str, int] = {}
        self.metrics: list[tuple[str, int]] = []

    # -- layout --------------------------------------------------------------------------------
    def header(self) -> None:
        ws, R = self.ws, self.R
        ws["A1"] = f"UAT-0 oracle: {self.sym} ({self.isin}), profile: {self.profile}"
        ws["A1"].font = Font(bold=True, size=14)
        rows = [
            ("Company (export)", f"={R}!B1"),
            ("Price used, ₹ (export 'Current Price')", f"={R}!B8"),
            ("Market cap used, ₹ cr (export)", f"={R}!B9"),
            ("Shares, cr = mcap ÷ price", f"={R}!B9/{R}!B8"),
            ("Adjusted shares FY26, cr (export derived)", f"={R}!K93"),
            ("Gap: mcap ÷ price vs adjusted shares", "=B6/B7-1"),
            ("Latest annual period", f"={R}!K16"),
            ("Latest quarter", f"={R}!K41"),
        ]
        for i, (k, f) in enumerate(rows, start=3):
            ws.cell(i, 1, k).font = BOLD
            ws.cell(i, 2, f)
        ws["B8"].number_format = "0.00%"
        ws["B9"].number_format = ws["B10"].number_format = "yyyy-mm-dd"
        if self.brk:
            ws["D3"] = (
                f"History break: {self.brk_why}. Growth windows are cut at {self.brk:%b %Y}; per-share ratios are not."
            )
            ws["D3"].font = Font(bold=True, color="C00000")
        ws["D4"] = (
            "Tolerances (plan 14 §4.1): ratios ±0.5% relative; point scores ±0.05; counts exact."
        )
        ws["D5"] = (
            "Fill the yellow cells only when a metric needs an input the Screener export does not hold."
        )
        ws.column_dimensions["A"].width = 44
        for col, wd in zip("BCDEFGHIJK", (16, 14, 18, 40, 14, 14, 14, 14, 14, 14), strict=False):
            ws.column_dimensions[col].width = wd

    def workings(self, start: int = 80) -> None:
        """Per-year helper series in columns B..K (same letters as RAW)."""
        ws, R = self.ws, self.R
        ws.cell(start - 1, 1, "WORKINGS (per fiscal year, columns B…K = FY2017…FY2026)").font = BOLD
        ws.cell(start - 1, 1).fill = SUB
        r = start
        ws.cell(r, 1, "Fiscal year end").font = BOLD
        for c in YEARS:
            ws[f"{c}{r}"] = f"={R}!{c}16"
            ws[f"{c}{r}"].number_format = "yyyy-mm-dd"
        self.w["date"] = r
        defs = [
            (
                "eps",
                "EPS ₹ = net profit ÷ adjusted shares",
                lambda c, p: f'=IFERROR({R}!{c}30/{R}!{c}93,"")',
                "0.00",
            ),
            (
                "pe",
                "Year-end P/E = year-end price ÷ EPS (EPS > 0)",
                lambda c, p: (
                    f'=IF(AND(ISNUMBER({c}{self.w["eps"]}),{c}{self.w["eps"]}>0),{R}!{c}90/{c}{self.w["eps"]},"")'
                ),
                "0.0",
            ),
            (
                "nw",
                "Net worth ₹ cr = equity + reserves",
                lambda c, p: f"={R}!{c}57+{R}!{c}58",
                "#,##0",
            ),
            (
                "bv",
                "Book value per share ₹",
                lambda c, p: f'=IFERROR({c}{self.w["nw"]}/{R}!{c}93,"")',
                "0.00",
            ),
            (
                "pb",
                "Year-end P/B = year-end price ÷ BVPS (BVPS > 0)",
                lambda c, p: (
                    f'=IF(AND(ISNUMBER({c}{self.w["bv"]}),{c}{self.w["bv"]}>0),{R}!{c}90/{c}{self.w["bv"]},"")'
                ),
                "0.00",
            ),
            (
                "ebitda",
                "EBITDA ₹ cr = PBT + interest + depreciation − other income",
                lambda c, p: f"={R}!{c}28+{R}!{c}27+{R}!{c}26-{R}!{c}25",
                "#,##0",
            ),
            (
                "roce",
                "ROCE = (PBT + interest) ÷ (equity + reserves + borrowings)",
                lambda c, p: f'=IFERROR(({R}!{c}28+{R}!{c}27)/({c}{self.w["nw"]}+{R}!{c}59),"")',
                "0.0%",
            ),
            (
                "roe",
                "ROE = net profit ÷ (equity + reserves); blank when net worth ≤ 0",
                lambda c, p: f'=IF({c}{self.w["nw"]}>0,{R}!{c}30/{c}{self.w["nw"]},"")',
                "0.0%",
            ),
            (
                "roa",
                "ROA = net profit ÷ total assets",
                lambda c, p: f'=IFERROR({R}!{c}30/{R}!{c}66,"")',
                "0.0%",
            ),
            ("gross", "Net block + CWIP ₹ cr", lambda c, p: f"={R}!{c}62+{R}!{c}63", "#,##0"),
            (
                "capex",
                "Capex proxy = Δ(net block + CWIP) + depreciation",
                lambda c, p: (
                    "" if p is None else f"={c}{self.w['gross']}-{p}{self.w['gross']}+{R}!{c}26"
                ),
                "#,##0",
            ),
            (
                "fcf",
                "FCF = CFO − capex proxy",
                lambda c, p: "" if p is None else f"={R}!{c}82-{c}{self.w['capex']}",
                "#,##0",
            ),
            (
                "evy",
                "Year-end EV ₹ cr = price × adjusted shares + borrowings − cash",
                lambda c, p: f"={R}!{c}90*{R}!{c}93+{R}!{c}59-{R}!{c}69",
                "#,##0",
            ),
            (
                "evx",
                "Year-end EV/EBITDA (EBITDA > 0)",
                lambda c, p: (
                    f'=IF({c}{self.w["ebitda"]}>0,{c}{self.w["evy"]}/{c}{self.w["ebitda"]},"")'
                ),
                "0.0",
            ),
            (
                "eps2",
                "2-year average EPS ₹",
                lambda c, p: (
                    "" if p is None else f"=AVERAGE({p}{self.w['eps']},{c}{self.w['eps']})"
                ),
                "0.00",
            ),
            (
                "pe2",
                "Year-end price ÷ 2-year average EPS (> 0)",
                lambda c, p: (
                    ""
                    if p is None
                    else f'=IF({c}{self.w["eps2"]}>0,{R}!{c}90/{c}{self.w["eps2"]},"")'
                ),
                "0.0",
            ),
        ]
        for key, label, fn, fmt in defs:
            r += 1
            self.w[key] = r
            ws.cell(r, 1, label)
            for i, c in enumerate(YEARS):
                f = fn(c, YEARS[i - 1] if i else None)
                if f:
                    ws[f"{c}{r}"] = f
                    ws[f"{c}{r}"].number_format = fmt

    # -- metric table --------------------------------------------------------------------------
    def table(self, start: int = 13) -> None:
        ws, R, w = self.ws, self.R, self.w
        heads = [
            "Metric",
            "Oracle value",
            "Unit",
            "Tolerance",
            "Formula (in words)",
            "Source cells / workings",
            "Applicable?",
            "Notes",
        ]
        for j, h in enumerate(heads, start=1):
            c = ws.cell(start, j, h)
            c.font, c.fill = WHITE, HEAD
            c.alignment = Alignment(wrap_text=True, vertical="center")
        self.row = start + 1

        mc, px = f"{R}!B9", f"{R}!B8"
        ttm = lambda r: f"SUM({R}!H{r}:K{r})"  # noqa: E731  # last four quarters (Sep-25 … Jun-26)
        prev4 = lambda r: f"SUM({R}!D{r}:G{r})"  # noqa: E731
        ev = f"({mc}+{R}!K59-{R}!K69)"

        post = self.brk is not None  # growth windows cut at the break
        na_growth = '="N/A (history restarts at ' + (f"{self.brk:%b %Y}" if self.brk else "") + ')"'

        def cagr(series_row: int, n: int, sheet_ref: str) -> str:
            if post:  # FY24..FY26 gives only 3 points after the break; 4 or 6 are needed
                return na_growth
            a, b = YEARS[-1 - n], YEARS[-1]
            return f'=IF(AND({sheet_ref}{a}{series_row}>0,{sheet_ref}{b}{series_row}>0),({sheet_ref}{b}{series_row}/{sheet_ref}{a}{series_row})^(1/{n})-1,"N/A (loss or zero base)")'

        M = self.metric
        # --- valuation
        M(
            "pe_ttm",
            "x",
            REL,
            "market cap ÷ net profit of the last four quarters",
            "export B9; quarterly Net profit H49:K49",
            f'=IF({ttm(49)}>0,{mc}/{ttm(49)},"N/A (loss)")',
            note="Screener-style: mcap ÷ TTM profit. The code uses price × adjusted shares ÷ TTM profit.",
        )
        pe_row = self.row - 1
        M(
            "pb",
            "x",
            REL,
            "market cap ÷ (equity + reserves)",
            "export B9; balance sheet K57:K58",
            f"={mc}/({R}!K57+{R}!K58)",
        )
        pb_row = self.row - 1
        for n in (3, 5, 10):
            rng = f"{YEARS[-n]}{w['pe']}:K{w['pe']}"
            M(
                f"pe_discount_own_{n}y",
                "ratio",
                REL,
                f"(median year-end P/E, last {n} FYs − current P/E) ÷ that median",
                f"workings P/E row {w['pe']}",
                f'=IFERROR((MEDIAN({rng})-$B${pe_row})/MEDIAN({rng}),"N/A")',
            )
        M(
            "pe_percentile_10y",
            "score",
            ABS_PP,
            "100 × share of the last 10 year-end P/Es at or below the current P/E",
            f"workings P/E row {w['pe']}",
            f'=IF(ISNUMBER($B${pe_row}),100*COUNTIF(B{w["pe"]}:K{w["pe"]},"<="&$B${pe_row})/COUNT(B{w["pe"]}:K{w["pe"]}),"N/A (no current P/E)")',
        )
        M(
            "pb_discount_own_5y",
            "ratio",
            REL,
            "(median year-end P/B, last 5 FYs − current P/B) ÷ that median",
            f"workings P/B row {w['pb']}",
            f'=IFERROR((MEDIAN(G{w["pb"]}:K{w["pb"]})-$B${pb_row})/MEDIAN(G{w["pb"]}:K{w["pb"]}),"N/A")',
        )
        M(
            "pe_normalised",
            "x",
            REL,
            "price ÷ mean EPS of up to ten fiscal years",
            f"export B8; workings EPS row {w['eps']}",
            f'=IFERROR({px}/AVERAGE(B{w["eps"]}:K{w["eps"]}),"N/A")',
        )
        M(
            "ev_ebitda",
            "x",
            REL,
            "(mcap + borrowings − cash) ÷ TTM operating profit",
            "export B9, K59, K69; quarterly Operating Profit H50:K50",
            f'=IF({ttm(50)}>0,{ev}/{ttm(50)},"N/A")',
            ok="not for banks",
        )
        M(
            "ev_sales",
            "x",
            REL,
            "(mcap + borrowings − cash) ÷ TTM sales",
            "export B9, K59, K69; quarterly Sales H42:K42",
            f'=IF({ttm(42)}>0,{ev}/{ttm(42)},"N/A")',
            ok="not for banks",
        )
        M(
            "dividend_yield",
            "ratio",
            REL,
            "FY26 dividend ÷ market cap (N/A when FY26 is blank)",
            "export K31, B9",
            f'=IF(ISNUMBER({R}!K31),{R}!K31/{mc},"N/A (FY26 dividend blank)")',
            note="a blank FY26 must not fall back to an older year",
        )
        M(
            "fcf_yield",
            "ratio",
            REL,
            "mean(CFO − capex proxy, last 3 FYs) ÷ market cap",
            f"workings FCF row {w['fcf']} (I:K); export B9",
            f"=AVERAGE(I{w['fcf']}:K{w['fcf']})/{mc}",
            ok="not for banks",
        )
        M(
            "peg",
            "x",
            REL,
            "P/E ÷ (EPS CAGR 3y × 100)",
            "P/E and EPS CAGR 3y rows above",
            "=__PEG__",
            note="N/A when EPS CAGR ≤ 0",
        )
        peg_row = self.row - 1
        # --- quality
        M(
            "roce_latest",
            "ratio",
            REL,
            "(PBT + interest) ÷ (equity + reserves + borrowings), FY26",
            f"workings ROCE row {w['roce']}",
            f"=K{w['roce']}",
            ok="not for banks",
        )
        M(
            "roce_5y_avg",
            "ratio",
            REL,
            "mean ROCE, FY22–FY26",
            f"workings ROCE row {w['roce']}",
            f"=AVERAGE(G{w['roce']}:K{w['roce']})",
            ok="not for banks",
        )
        M(
            "roce_trend_pp",
            "score",
            ABS_PP,
            "(ROCE FY26 − ROCE FY24) × 100",
            f"workings ROCE row {w['roce']}",
            f"=(K{w['roce']}-I{w['roce']})*100",
            ok="not for banks",
        )
        M(
            "roe_latest",
            "ratio",
            REL,
            "net profit ÷ (equity + reserves), FY26",
            f"workings ROE row {w['roe']}",
            f'=IF(ISNUMBER(K{w["roe"]}),K{w["roe"]},"N/A (net worth not positive)")',
        )
        M(
            "roe_5y_avg",
            "ratio",
            REL,
            "mean ROE, FY22–FY26",
            f"workings ROE row {w['roe']}",
            f'=IFERROR(AVERAGE(G{w["roe"]}:K{w["roe"]}),"N/A")',
            note="years with net worth ≤ 0 are left out (a loss over negative equity is not a positive return)",
        )
        M(
            "roa_latest",
            "ratio",
            REL,
            "net profit ÷ total assets, FY26",
            f"workings ROA row {w['roa']}",
            f"=K{w['roa']}",
        )
        M(
            "roa_5y_avg",
            "ratio",
            REL,
            "mean ROA, FY22–FY26",
            f"workings ROA row {w['roa']}",
            f"=AVERAGE(G{w['roa']}:K{w['roa']})",
        )
        M(
            "cfo_to_ebitda_3y",
            "ratio",
            REL,
            "Σ CFO ÷ Σ EBITDA, FY24–FY26",
            f"export I82:K82; workings EBITDA row {w['ebitda']}",
            f"=SUM({R}!I82:K82)/SUM(I{w['ebitda']}:K{w['ebitda']})",
            ok="not for banks",
        )
        M(
            "cfo_to_pat_3y",
            "ratio",
            REL,
            "Σ CFO ÷ Σ net profit, FY24–FY26",
            "export I82:K82, I30:K30",
            f"=SUM({R}!I82:K82)/SUM({R}!I30:K30)",
            ok="not for banks",
        )
        M(
            "op_margin_trend_pp",
            "score",
            ABS_PP,
            "(op margin of last 4 quarters − previous 4) × 100",
            "quarterly Operating Profit/Sales H:K vs D:G",
            f"=({ttm(50)}/{ttm(42)}-{prev4(50)}/{prev4(42)})*100",
            ok="not for banks",
        )
        M(
            "other_income_share",
            "ratio",
            REL,
            "other income ÷ PBT, FY26",
            "export K25, K28",
            f'=IF({R}!K28>0,{R}!K25/{R}!K28,"N/A")',
        )
        # --- balance sheet
        M(
            "debt_equity",
            "x",
            REL,
            "borrowings ÷ (equity + reserves), FY26",
            "export K59; K57:K58",
            f"={R}!K59/({R}!K57+{R}!K58)",
            ok="not for banks or NBFCs",
        )
        M(
            "interest_coverage",
            "x",
            REL,
            "(PBT + interest) ÷ interest, FY26, capped at 50",
            "export K27, K28",
            f"=IF({R}!K27<=0.01*ABS({R}!K28+{R}!K27),50,MIN(50,({R}!K28+{R}!K27)/{R}!K27))",
            ok="not for banks",
        )
        M(
            "net_cash_to_mcap",
            "ratio",
            REL,
            "(cash & bank − borrowings) ÷ market cap",
            "export K69, K59, B9",
            f"=({R}!K69-{R}!K59)/{mc}",
            ok="not for banks",
        )
        # --- growth
        M(
            "revenue_cagr_3y",
            "ratio",
            REL,
            "(sales FY26 ÷ sales FY23)^(1/3) − 1",
            "export H17, K17",
            cagr(17, 3, f"{R}!"),
            note=self.brk_why and "window cut at the merger",
        )
        M(
            "revenue_cagr_5y",
            "ratio",
            REL,
            "(sales FY26 ÷ sales FY21)^(1/5) − 1",
            "export F17, K17",
            cagr(17, 5, f"{R}!"),
            note=self.brk_why and "window cut at the merger",
        )
        M(
            "eps_cagr_3y",
            "ratio",
            REL,
            "(EPS FY26 ÷ EPS FY23)^(1/3) − 1",
            f"workings EPS row {w['eps']}",
            cagr(w["eps"], 3, ""),
            note=self.brk_why and "window cut at the merger",
        )
        eps3_row = self.row - 1
        M(
            "eps_cagr_5y",
            "ratio",
            REL,
            "(EPS FY26 ÷ EPS FY21)^(1/5) − 1",
            f"workings EPS row {w['eps']}",
            cagr(w["eps"], 5, ""),
            note=self.brk_why and "window cut at the merger",
        )
        if post:
            M(
                "growth_consistency",
                "ratio",
                REL,
                "years with sales up ÷ years compared (last 5; needs 3)",
                "export sales, after the break",
                na_growth,
                note="2 comparisons after the break; needs 3",
            )
        else:
            M(
                "growth_consistency",
                "ratio",
                REL,
                "years with sales up on the prior year ÷ 5",
                "export F17:K17",
                f"=SUMPRODUCT(--({R}!G17:K17>{R}!F17:J17))/5",
            )
        M(
            "revenue_growth_1y",
            "ratio",
            REL,
            "sales FY26 ÷ sales FY25 − 1",
            "export J17, K17",
            f"={R}!K17/{R}!J17-1",
        )
        rev3_row = next(r for k, r in self.metrics if k == "revenue_cagr_3y")
        M(
            "eps_vs_revenue_gap",
            "ratio",
            REL,
            "EPS CAGR 3y − revenue CAGR 3y",
            "rows above",
            f'=IFERROR(B{eps3_row}-B{rev3_row},"N/A")',
        )
        M(
            "dilution_3y",
            "ratio",
            REL,
            "(adjusted shares FY26 ÷ FY23)^(1/3) − 1",
            "export derived row 93, H and K",
            f"=({R}!K93/{R}!H93)^(1/3)-1",
            note="HDFC: the merger issued shares, so this reads high; the code does not cut it at the break"
            if post
            else "",
        )
        # --- metrics the first pass missed (cover every value metric the code computes from the export)
        roe5 = next(r for k, r in self.metrics if k == "roe_5y_avg")
        ev_eb = next(r for k, r in self.metrics if k == "ev_ebitda")
        ev_s = next(r for k, r in self.metrics if k == "ev_sales")
        g1 = next(r for k, r in self.metrics if k == "revenue_growth_1y")
        M(
            "ev_ebitda_discount_own",
            "ratio",
            REL,
            "(median year-end EV/EBITDA, FY22–FY26 − current) ÷ that median (needs 3 usable years)",
            f"workings EV/EBITDA row {w['evx']}",
            f'=IF(AND(ISNUMBER(B{ev_eb}),COUNT(G{w["evx"]}:K{w["evx"]})>=3),(MEDIAN(G{w["evx"]}:K{w["evx"]})-B{ev_eb})/MEDIAN(G{w["evx"]}:K{w["evx"]}),"N/A")',
            ok="not for banks",
            note="five-year window is fixed FY22–FY26; years without a positive EBITDA are left out",
        )
        M(
            "ev_sales_to_growth",
            "x",
            REL,
            "(EV ÷ TTM sales) ÷ (FY26 revenue growth × 100); N/A when growth ≤ 0",
            "rows above",
            f'=IF(AND(ISNUMBER(B{ev_s}),B{g1}>0),B{ev_s}/(B{g1}*100),"N/A")',
        )
        M(
            "pb_justified_gap",
            "ratio",
            REL,
            "(ROE 5y avg ÷ cost of equity) ÷ P/B − 1, cost of equity 12.5%",
            "rows above; cost of equity = value.yaml dcf.cost_of_equity",
            f'=IF(ISNUMBER(B{roe5}),B{roe5}/0.125/B{pb_row}-1,"N/A")',
            note="12.5% is the framework's configured assumption, not derived from the export",
        )
        M(
            "pe_2y_avg_discount_3y",
            "ratio",
            REL,
            "(median of year-end price ÷ 2-yr avg EPS, FY24–FY26 − current price ÷ latest 2-yr avg EPS) ÷ median",
            f"workings row {w['pe2']}",
            f'=IF(AND(K{w["eps2"]}>0,COUNT(I{w["pe2"]}:K{w["pe2"]})=3),(MEDIAN(I{w["pe2"]}:K{w["pe2"]})-{px}/K{w["eps2"]})/MEDIAN(I{w["pe2"]}:K{w["pe2"]}),"N/A")',
        )
        M(
            "piotroski_fraction",
            "ratio",
            REL,
            "passed ÷ 7: ROA>0, CFO>0, ROA up, CFO>profit, leverage down, no dilution (≤+0.5%), asset turnover up",
            "export J:K rows 17, 30, 59, 66, 82, 93",
            f"=(({R}!K30/{R}!K66>0)+({R}!K82>0)+({R}!K30/{R}!K66>{R}!J30/{R}!J66)+({R}!K82>{R}!K30)+({R}!K59/{R}!K66<={R}!J59/{R}!J66)+({R}!K93<={R}!J93*1.005)+({R}!K17/{R}!K66>{R}!J17/{R}!J66))/7",
        )
        M(
            "debtor_days_change",
            "ratio",
            REL,
            "debtor days FY26 ÷ debtor days FY25 − 1 (receivables ÷ sales × 365)",
            "export J67:K67, J17:K17",
            f'=IF(AND(ISNUMBER({R}!K67),ISNUMBER({R}!J67),{R}!J67>0),({R}!K67/{R}!K17)/({R}!J67/{R}!J17)-1,"N/A")',
        )
        M(
            "cash_runway_months",
            "count",
            REL,
            "net cash ÷ monthly FY26 free-cash-flow burn; 999 when not burning; 0 when no net cash",
            f"workings FCF row {w['fcf']}; export K69, K59",
            f"=IF(K{w['fcf']}>=0,999,IF({R}!K69-{R}!K59<=0,0,({R}!K69-{R}!K59)/(-K{w['fcf']}/12)))",
            ok="new-age profile",
        )
        # PEG needs the EPS CAGR row, fill the placeholder now
        ws = self.ws
        ws.cell(
            peg_row, 2
        ).value = f'=IFERROR(IF(AND(ISNUMBER(B{eps3_row}),B{eps3_row}>0),B{pe_row}/(B{eps3_row}*100),"N/A"),"N/A")'

    def metric(self, ident, unit, tol, words, cells, formula, ok="yes", note=""):
        ws, r = self.ws, self.row
        ws.cell(r, 1, f"MET.value.{ident}")
        ws.cell(r, 2, formula)
        ws.cell(r, 3, unit)
        ws.cell(r, 4, tol)
        ws.cell(r, 5, words).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 6, cells).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 7, ok)
        ws.cell(r, 8, note or "").alignment = Alignment(wrap_text=True, vertical="top")
        fmt = {"x": "0.00", "ratio": "0.0000", "score": "0.00"}.get(unit, "General")
        ws.cell(r, 2).number_format = fmt
        self.metrics.append((ident, r))
        self.row += 1

    # -- profile blocks (inputs the export lacks) ----------------------------------------------
    def blocks(self) -> None:
        ws, R = self.ws, self.R
        r = self.row + 1
        if self.sym == "INDIGO":
            ws.cell(
                r,
                1,
                "INDIGO ADD-ONS (plan 14 §4.1, D24): need lease inputs from the filings, not in the Screener export",
            ).font = BOLD
            ws.cell(r, 1).fill = SUB
            labels = [
                ("Lease liabilities, FY26, ₹ cr (non-current + current)", None),
                ("Aircraft and engine rentals (short-term leases), FY26, ₹ cr", None),
            ]
            rows = {}
            for i, (lab, _) in enumerate(labels, start=1):
                ws.cell(r + i, 1, lab)
                ws.cell(r + i, 2).fill = NEED
                ws.cell(r + i, 3, "INPUT NEEDED")
                rows[i] = r + i
            L, RENT = f"B{rows[1]}", f"B{rows[2]}"
            mc = f"{R}!B9"
            r2 = r + 3
            items = [
                (
                    "MET.value.ev_ebitdar",
                    f'=IF(AND(ISNUMBER({L}),ISNUMBER({RENT})),({mc}+{R}!K59+{L}-{R}!K69)/(SUM({R}!H50:K50)+{RENT}),"INPUT NEEDED")',
                    "(mcap + borrowings + lease liabilities − cash) ÷ (TTM operating profit + lease cost)",
                ),
                (
                    "MET.value.lease_adj_leverage",
                    f'=IF(AND(ISNUMBER({L}),ISNUMBER({RENT})),({R}!K59+{L}-{R}!K69)/(SUM({R}!H50:K50)+{RENT}),"INPUT NEEDED")',
                    "(borrowings + lease liabilities − cash) ÷ (TTM operating profit + lease cost)",
                ),
            ]
            for i, (ident, f, words) in enumerate(items):
                ws.cell(r2 + i, 1, ident)
                ws.cell(r2 + i, 2, f)
                ws.cell(r2 + i, 3, "x")
                ws.cell(r2 + i, 4, REL)
                ws.cell(r2 + i, 5, words)
                self.metrics.append((ident.removeprefix("MET.value."), r2 + i))
            self.row = r2 + len(items)
        if self.sym == "MM":
            ws.cell(
                r,
                1,
                "M&M SOTP (plan 14 §4.1, D24): needs listed-stake market caps and the holdco discount",
            ).font = BOLD
            ws.cell(r, 1).fill = SUB
            ws.cell(
                r + 1,
                1,
                "Core standalone value, ₹ cr (core P/E × standalone profit, or the code's DCF mid)",
            )
            ws.cell(r + 2, 1, "Listed stakes at market, ₹ cr (Σ investee market cap × stake %)")
            ws.cell(r + 3, 1, "Unlisted holdings at book, ₹ cr")
            ws.cell(r + 4, 1, "Holdco discount (value.yaml)")
            for i in (1, 2, 3, 4):
                ws.cell(r + i, 2).fill = NEED
                ws.cell(r + i, 3, "INPUT NEEDED")
            ws.cell(r + 5, 1, "MET.value.sotp_discount")
            ws.cell(
                r + 5,
                2,
                f'=IF(COUNT(B{r + 1}:B{r + 4})=4,((B{r + 1}+B{r + 2}*(1-B{r + 4})+B{r + 3})-{R}!B9)/(B{r + 1}+B{r + 2}*(1-B{r + 4})+B{r + 3}),"INPUT NEEDED")',
            )
            ws.cell(r + 5, 3, "ratio")
            ws.cell(r + 5, 4, REL)
            ws.cell(r + 5, 5, "(SOTP − market cap) ÷ SOTP")
            self.metrics.append(("sotp_discount", r + 5))
            self.row = r + 6


def _readme(wb: openpyxl.Workbook) -> None:
    ws = wb.active
    assert ws is not None
    ws.title = "README"
    lines = [
        ("UAT-0 analyst oracle: golden stocks HDFCBANK, INDIGO, M&M", True),
        (
            "Plan 14 §4.1 and §7.2. Built independently of the Python code: Excel formulas on a copy of each stock's raw Screener export ('RAW_*' sheets).",
            False,
        ),
        ("", False),
        ("How to review (about 45 minutes)", True),
        (
            "1. Open a stock's ORACLE sheet. Read the 'Formula (in words)' column and check it is the definition you want. That is the real review.",
            False,
        ),
        (
            "2. Click 3-4 'Oracle value' cells per stock and confirm the formula points at the right raw cells (column F lists them).",
            False,
        ),
        (
            "3. Open SPOT_CHECKS. Type what screener.in shows for each ratio; the sheet computes the gap.",
            False,
        ),
        (
            "4. Open COMPARE (written by tools/compare_oracle.py). Every row marked DIFF is a disagreement between the oracle and the code. Decide per row: oracle wrong, code wrong, or definition choice.",
            False,
        ),
        ("5. Sign on SIGN_OFF.", False),
        ("", False),
        (
            "Rule (plan 14 §4.1): code is changed to match the oracle, never the other way round. Changing the oracle later needs an oracle-change PR and a re-signed note.",
            False,
        ),
        (
            "Scope now: the value metrics derivable from the Screener export. Momentum / DMA oracle needs the frozen 30 Oct price files and is not in this workbook yet.",
            False,
        ),
        (
            "Inputs not in the export (INDIGO leases, M&M investee market caps, bank asset quality) are yellow cells marked INPUT NEEDED. They stay open until the filing inputs land.",
            False,
        ),
        (
            "Price basis: the export's 'Current Price' (B8) and 'Market Capitalization' (B9) at export date. The code is fed the same price when compared.",
            False,
        ),
    ]
    for i, (t, b) in enumerate(lines, start=1):
        ws.cell(i, 1, t).font = Font(bold=b, size=13 if i == 1 else 11)
    ws.column_dimensions["A"].width = 150


def _spot(wb: openpyxl.Workbook, sheets: list[Sheet]) -> None:
    ws = wb.create_sheet("SPOT_CHECKS")
    heads = [
        "Stock",
        "Ratio as screener.in displays it",
        "Oracle value",
        "Screener shows (you type)",
        "Gap %",
        "OK within 0.5%?",
    ]
    for j, h in enumerate(heads, start=1):
        c = ws.cell(1, j, h)
        c.font, c.fill = WHITE, HEAD
    picks = ["pe_ttm", "pb", "roce_latest", "roe_latest", "dividend_yield"]
    r = 2
    for s in sheets:
        look = dict(s.metrics)
        for key in picks:
            if key not in look:
                continue
            ws.cell(r, 1, s.sym)
            ws.cell(r, 2, f"MET.value.{key}")
            ws.cell(r, 3, f"='{s.ws.title}'!B{look[key]}")
            ws.cell(r, 4).fill = NEED
            ws.cell(r, 5, f'=IF(ISNUMBER(D{r}),C{r}/D{r}-1,"")')
            ws.cell(r, 5).number_format = "0.00%"
            ws.cell(r, 6, f'=IF(ISNUMBER(E{r}),IF(ABS(E{r})<=0.005,"OK","CHECK"),"")')
            r += 1
    ws.cell(
        r + 1,
        1,
        "Screener shows ROCE/ROE/dividend yield as percentages: type them as decimals (18.4% → 0.184). Its P/E is TTM on consolidated results.",
    )
    for col, wd in zip("ABCDEF", (14, 34, 16, 26, 10, 18), strict=False):
        ws.column_dimensions[col].width = wd


def _signoff(wb: openpyxl.Workbook) -> None:
    ws = wb.create_sheet("SIGN_OFF")
    rows = [
        (
            "UAT-0 sign-off (plan 14 §7.2: all 3 signed; every disputed value resolved and noted)",
            True,
        ),
        ("", False),
        (
            "HDFCBANK: signed by ______________   date ________   disputed values and resolution: ____________________",
            False,
        ),
        (
            "INDIGO:   signed by ______________   date ________   disputed values and resolution: ____________________",
            False,
        ),
        (
            "M&M:      signed by ______________   date ________   disputed values and resolution: ____________________",
            False,
        ),
        ("", False),
        (
            "Open (cannot be signed until inputs land): INDIGO lease inputs, M&M SOTP inputs, bank asset-quality inputs, momentum oracle on frozen prices.",
            False,
        ),
    ]
    for i, (t, b) in enumerate(rows, start=1):
        ws.cell(i, 1, t).font = Font(bold=b)
    ws.column_dimensions["A"].width = 130


def build(exports: list[Path], out: Path) -> dict[str, dict[str, int]]:
    wb = openpyxl.Workbook()
    _readme(wb)
    sheets: list[Sheet] = []
    for (sym, isin, profile, brk, why), src in zip(STOCKS, exports, strict=True):
        s = Sheet(wb, sym, isin, profile, brk, why)
        s.header()
        s.workings()
        s.table()
        s.blocks()
        _raw_copy(wb, s.R, src)
        s.ws.freeze_panes = "B14"
        sheets.append(s)
    _spot(wb, sheets)
    _signoff(wb)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return {s.sym: dict(s.metrics) for s in sheets}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "exports", nargs=3, type=Path, help="HDFCBANK, INDIGO, M&M Screener exports, in that order"
    )
    ap.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    layout = build(a.exports, a.out)
    print(f"wrote {a.out}: " + ", ".join(f"{k} {len(v)} metrics" for k, v in layout.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
