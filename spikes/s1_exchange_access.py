"""Spike ①: can a GitHub-hosted runner reach NSE and BSE? (plan 04 §4 #2, plan 09 Phase 0.5)

Probes every exchange source Phase 1 needs, the way an adapter would: bhavcopies (UDiFF),
the NSE equity list, NSE announcement/corporate-action APIs (cookie handshake first), BSE
bhavcopy and announcements API, Nifty index constituents, the AMFI cap list and Yahoo prices.
"""

from __future__ import annotations

import re

from _common import Recorder, client, recent_weekdays

PILOT = {"HDFCBANK": "500180", "INDIGO": "539448", "MAZDOCK": "543237"}


def main() -> None:
    rec = Recorder("s1")
    days = recent_weekdays(6)

    with client() as c:
        # --- NSE archives (static files) -------------------------------------------------
        for d in days:
            r = rec.probe(
                f"nse.bhavcopy_udiff {d}",
                lambda d=d: c.get(
                    f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
                ),
                sample_name=f"nse_bhavcopy_{d:%Y%m%d}.csv.zip",
            )
            if r is not None and r.status_code == 200:
                break
        rec.probe(
            "nse.equity_list",
            lambda: c.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"),
            sample_name="nse_EQUITY_L.csv",
        )

        # --- NSE JSON APIs: homepage first for cookies ------------------------------------
        rec.probe("nse.homepage", lambda: c.get("https://www.nseindia.com/"))
        api_headers = {"Referer": "https://www.nseindia.com/", "Accept": "application/json"}
        rec.probe(
            "nse.api.corporate_announcements HDFCBANK",
            lambda: c.get(
                "https://www.nseindia.com/api/corporate-announcements",
                params={"index": "equities", "symbol": "HDFCBANK"},
                headers=api_headers,
            ),
            sample_name="nse_announcements_HDFCBANK.json",
        )
        rec.probe(
            "nse.api.corporate_actions MAZDOCK",
            lambda: c.get(
                "https://www.nseindia.com/api/corporates-corporateActions",
                params={"index": "equities", "symbol": "MAZDOCK"},
                headers=api_headers,
            ),
            sample_name="nse_corp_actions_MAZDOCK.json",
        )
        rec.probe(
            "nse.api.quote HDFCBANK",
            lambda: c.get(
                "https://www.nseindia.com/api/quote-equity",
                params={"symbol": "HDFCBANK"},
                headers=api_headers,
            ),
            sample_name="nse_quote_HDFCBANK.json",
        )

        # --- Index constituents (niftyindices) ------------------------------------------
        for name, slug in [
            ("nifty100", "ind_nifty100list"),
            ("midcap150", "ind_niftymidcap150list"),
            ("smallcap250", "ind_niftysmallcap250list"),
        ]:
            rec.probe(
                f"niftyindices.constituents {name}",
                lambda slug=slug: c.get(
                    f"https://www.niftyindices.com/IndexConstituent/{slug}.csv"
                ),
                sample_name=f"{slug}.csv",
            )

        # --- BSE ------------------------------------------------------------------------
        for d in days:
            r = rec.probe(
                f"bse.bhavcopy_udiff {d}",
                lambda d=d: c.get(
                    f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{d:%Y%m%d}_F_0000.CSV",
                    headers={"Referer": "https://www.bseindia.com/"},
                ),
                sample_name=f"bse_bhavcopy_{d:%Y%m%d}.csv",
            )
            if r is not None and r.status_code == 200:
                break
        start, end = days[-1], days[0]
        rec.probe(
            "bse.api.announcements HDFCBANK",
            lambda: c.get(
                "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w",
                params={
                    "pageno": 1,
                    "strCat": -1,
                    "strPrevDate": f"{start:%Y%m%d}",
                    "strScrip": PILOT["HDFCBANK"],
                    "strSearch": "P",
                    "strToDate": f"{end:%Y%m%d}",
                    "strType": "C",
                    "subcategory": -1,
                },
                headers={
                    "Referer": "https://www.bseindia.com/",
                    "Origin": "https://www.bseindia.com",
                    "Accept": "application/json",
                },
            ),
            sample_name="bse_announcements_HDFCBANK.json",
        )

        # --- AMFI cap list: find the latest xlsx link on the page ------------------------
        page = rec.probe(
            "amfi.categorisation_page",
            lambda: c.get("https://www.amfiindia.com/otherdata/categorisation-of-stocks"),
        )
        if page is not None and page.status_code == 200:
            links = re.findall(r'href="([^"]+\.xlsx?)"', page.text, flags=re.I)
            rec.note(probe="amfi.xlsx_links", count=len(links), first=links[:3])
            if links:
                url = (
                    links[0]
                    if links[0].startswith("http")
                    else "https://www.amfiindia.com" + links[0]
                )
                rec.probe(
                    "amfi.latest_xlsx", lambda: c.get(url), sample_name="amfi_categorisation.xlsx"
                )

    # --- Yahoo (yfinance), the Phase 1 primary price source -----------------------------
    try:
        import yfinance as yf

        for sym in ("HDFCBANK.NS", "M&M.NS", "MAZDOCK.NS"):
            df = yf.download(sym, period="1mo", auto_adjust=False, progress=False)
            rec.note(
                probe=f"yfinance {sym}",
                ok=not df.empty,
                rows=len(df),
                last=str(df.index.max()) if not df.empty else None,
            )
    except Exception as exc:
        rec.note(probe="yfinance", ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
    rec.save()


if __name__ == "__main__":
    main()
