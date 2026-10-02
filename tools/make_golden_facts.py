"""Turn a Screener export into the parsed-facts fixture the golden tests use (plan 13 §8.0c).

The export itself is not committed (source terms); the fixture keeps the parsed facts and the export's hash.
Usage: python tools/make_golden_facts.py ISIN path/to/export.xlsx
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from parakh.adapters.screener_export import parse_export  # noqa: E402
from parakh.orchestration.fundamentals import fact_rows  # noqa: E402


def main(isin: str, export: str) -> int:
    data = Path(export).read_bytes()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    rows = fact_rows(parse_export(data), isin, digest, {})
    out = REPO / "tests" / "fixtures" / "golden" / isin / "facts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"export_hash": digest, "rows": rows}, indent=0, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{isin}: {len(rows)} facts, {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:3]))
