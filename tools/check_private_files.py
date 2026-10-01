"""Block private files from commits (AC-F03.4; plan 13 P6, D19).

Refuses staged paths that look like holdings data, depository or broker statements, Screener
exports or private keys, and any file containing an age secret key. Recorded third-party
fixtures under tests/fixtures/sources/ and the synthetic CAS/broker fixtures are allowed.
Run by pre-commit with the staged file names; exits 1 with the reasons.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_PREFIXES = (
    "tests/fixtures/sources/",
    "tests/fixtures/cas/synthetic_",
    "tests/fixtures/broker/synthetic_",
)
BLOCKED = [
    (re.compile(r"(^|/)holdings[^/]*\.(ya?ml|json|csv|xlsx?)$", re.I), "plaintext holdings file"),
    (re.compile(r"(^|/)[^/]*cas[^/]*\.pdf$", re.I), "depository CAS statement"),
    (re.compile(r"(^|/)Stocks_PnL_Report[^/]*$", re.I), "broker P&L report"),
    (re.compile(r"(^|/)parakh-backup-key[^/]*$", re.I), "backup private key"),
    (re.compile(r"(^|/)FILES FOR ANALYSIS/", re.I), "private inbox folder"),
    (re.compile(r"(^|/)\.env(\.|$)(?!example)", re.I), ".env file"),
]
SECRET_CONTENT = re.compile(rb"AGE-SECRET-KEY-1[0-9A-Z]{58}")


def problems(paths: list[str], read=lambda p: Path(p).read_bytes()) -> list[str]:  # type: ignore[no-untyped-def]
    out = []
    for raw in paths:
        path = raw.replace("\\", "/")
        if path.startswith(ALLOWED_PREFIXES):
            continue
        for pattern, why in BLOCKED:
            if pattern.search(path):
                out.append(f"{path}: {why} must never be committed")
                break
        else:
            try:
                if SECRET_CONTENT.search(read(raw)):
                    out.append(f"{path}: contains an age private key")
            except OSError:
                pass
    return out


def main(argv: list[str]) -> int:
    found = problems(argv)
    for p in found:
        print(p, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
