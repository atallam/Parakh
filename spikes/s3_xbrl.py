"""Spike ③b: can we fetch and parse an exchange XBRL financial result? (plan 00 §7: T1 cross-check)

Tries NSE's financial-results API for M&M (cookie handshake first), downloads the newest XBRL,
and extracts a few Ind-AS tags to compare with the Screener export (Jun 2026 quarter).
"""

from __future__ import annotations

import re

from _common import Recorder, client

TAGS = ("RevenueFromOperations", "ProfitLossForPeriod", "ProfitBeforeTax", "FinanceCosts")


def main() -> None:
    rec = Recorder("s3")
    with client() as c:
        rec.probe("nse.homepage", lambda: c.get("https://www.nseindia.com/"))
        hdr = {"Referer": "https://www.nseindia.com/", "Accept": "application/json"}
        resp = rec.probe(
            "nse.api.financial_results M&M",
            lambda: c.get(
                "https://www.nseindia.com/api/corporates-financial-results",
                params={"index": "equities", "symbol": "M&M", "period": "Quarterly"},
                headers=hdr,
            ),
            sample_name="nse_financial_results_MM.json",
        )
        xbrl_urls: list[str] = []
        if resp is not None and resp.status_code == 200:
            try:
                rows = resp.json()
                rows = rows if isinstance(rows, list) else rows.get("data", [])
                for row in rows[:8]:
                    for value in row.values():
                        if isinstance(value, str) and value.lower().endswith(".xml"):
                            xbrl_urls.append(value)
                rec.note(
                    probe="nse.financial_results.rows",
                    count=len(rows),
                    keys=sorted(rows[0].keys()) if rows else [],
                    xbrl=xbrl_urls[:4],
                )
            except Exception as exc:
                rec.note(probe="nse.financial_results.parse", ok=False, error=str(exc)[:200])
        for i, url in enumerate(xbrl_urls[:2]):
            x = rec.probe(
                f"nse.xbrl {i}",
                lambda url=url: c.get(url, headers=hdr),
                sample_name=f"mm_xbrl_{i}.xml",
            )
            if x is not None and x.status_code == 200:
                found = {}
                for tag in TAGS:
                    m = re.findall(
                        rf"<[^>]*:{tag}\b[^>]*contextRef=\"([^\"]+)\"[^>]*>([^<]+)<", x.text
                    )
                    found[tag] = m[:4]
                rec.note(probe=f"nse.xbrl {i} facts", facts=found)
    rec.save()


if __name__ == "__main__":
    main()
