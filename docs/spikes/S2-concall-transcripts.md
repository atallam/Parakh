# Spike ②: filed concall transcripts via Screener → BSE (D7)

- **Date:** 29 Sep 2026 · **Script:** `spikes/s2_concalls.py` · **Code kept:** `src/parakh/adapters/concalls.py` (ported from Drishti 2.0 `concall_engine.py`)
- **Question:** does the D7 route find a valid, exchange-filed transcript for every pilot stock, from the cloud?

## Result: 7 of 7, on the runner and in the workspace

| Stock | Calls listed | With transcript | Chosen | Pages · chars |
|---|---|---|---|---|
| INDIGO | 51 | 44 | Jul 2026 | 20 · 54,321 |
| M&M | 109 | 33 | Aug 2026 | 22 · 94,001 |
| HDFCBANK | 27 | 20 | Jul 2026 | 17 · 54,445 |
| GROWW | 5 | 4 | Jul 2026 | 15 · 40,245 |
| MAZDOCK | 32 | 16 | **Nov 2025 (stale)** | 18 · 48,805 |
| ATHERENERG | 6 | 6 | Aug 2026 | 17 · 47,352 |
| SHADOWFAX | 3 | 3 | Aug 2026 | 17 · 49,183 |

Every transcript link redirects to `bseindia.com/xml-data/corpfiling/AttachHis/…pdf` (T1). All passed Drishti's validator.

## Findings

- **MAZDOCK's five newest calls (Feb–Sep 2026) list a presentation but no transcript.** The provider now skips those rows, uses the newest filed one, and marks it `stale` with the reason. The qualitative agent (Phase 4) must show "transcript missing for the latest call" instead of reading a 10-month-old call as current.
- Ported unchanged: PyMuPDF extraction, the four validator heuristics, Q&A-preserving truncation. Changed: one provider instead of five dead ones, the validator returns reasons, every candidate is validated before moving on, no LLM in the adapter.
- OCR for scanned PDFs is deferred to F06 (none of the 7 needed it).

## How it is tested

`tests/unit/test_concalls.py` replays recorded Screener pages (HDFCBANK, MAZDOCK) and a trimmed filed PDF through an httpx mock: parsing, validation reasons, staleness, and moving on after a non-PDF response.
