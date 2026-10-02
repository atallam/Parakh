"""Pre-commit hook: the `original` block of a THESIS.md never changes after it is first committed (F23).

A thesis is amended in `current`/`breakers` and by the review log; the words you wrote on the day you bought
stay as written so the review can compare against them. Usage: check_thesis_original.py [files...]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from parakh.thesis.model import parse_text  # noqa: E402


def committed_original(path: Path) -> dict | None:
    rel = path.resolve().relative_to(REPO).as_posix()
    res = subprocess.run(
        ["git", "show", f"HEAD:{rel}"], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )
    if res.returncode != 0:
        return None  # a new file: nothing to compare with
    return parse_text(res.stdout, path).raw_original


def problems(paths: list[Path]) -> list[str]:
    out = []
    for p in paths:
        if p.name != "THESIS.md" or not p.exists():
            continue
        before = committed_original(p)
        after = parse_text(p.read_text(encoding="utf-8"), p).raw_original
        if before is not None and after != before:
            out.append(
                f"{p}: the `original` block changed. Add to `current` instead; the original stays as first written."
            )
    return out


def main(argv: list[str]) -> int:
    bad = problems([Path(a) for a in argv])
    for line in bad:
        print(line, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
