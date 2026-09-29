"""Spike ②: latest valid filed transcript for every pilot stock via Screener → BSE (D7)."""

from __future__ import annotations

import time

from _common import Recorder

from parakh.adapters.concalls import ScreenerConcallsProvider
from parakh.configs import load_all


def main() -> None:
    rec = Recorder("s2")
    provider = ScreenerConcallsProvider()
    for sec in load_all().universe.pilot:
        start = time.perf_counter()
        try:
            calls = provider.list_calls(sec.symbol)
            transcript, log = provider.latest_valid(sec.symbol)
            rec.note(
                probe=f"concalls {sec.symbol}",
                isin=sec.isin,
                ok=transcript is not None,
                calls_listed=len(calls),
                with_transcript=sum(1 for c in calls if c.transcript_url),
                newest=calls[0].label if calls else None,
                chosen=transcript.period.isoformat() if transcript else None,
                pages=transcript.pages if transcript else None,
                chars=len(transcript.text) if transcript else None,
                final_host=transcript.final_url.split("/")[2] if transcript else None,
                log=log,
                ms=round((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            rec.note(
                probe=f"concalls {sec.symbol}", ok=False, error=f"{type(exc).__name__}: {exc}"[:300]
            )
        time.sleep(2)  # why: polite to Screener (plan 04 §4 #7)
    rec.save()


if __name__ == "__main__":
    main()
