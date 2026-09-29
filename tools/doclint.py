"""Doc lint (AC-F21.14; plan 14 L0): one owner per fact in docs/plan/.

1. Milestone dates are owned by plan 09's milestone table. Any other doc may repeat a milestone
   date only if it matches 09 (derived copies are allowed only while this check keeps them in
   step). A line that names a milestone and carries a different date fails.
2. Phase-placement tables (a table with a "Phase" column) live only in 09, except the test
   gates in 14 §9.
3. Decision IDs (D1, D2, …) are defined only in plan 13's decision log.

Run: `uv run python tools/doclint.py` (CI runs it).
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "plan"
OWNER_DATES = "09_PHASED_ROLLOUT_PLAN.md"
OWNER_DECISIONS = "13_PLAN_BASELINE_V1.md"
PHASE_TABLE_ALLOWED = {OWNER_DATES, "14_TEST_AND_UAT_PLAN.md"}

MILESTONE_ROW = re.compile(r"^\|\s*\*\*(M\d|v1\.0 GA)[^|]*\|\s*(\d{4}-\d{2}-\d{2})\s*\|")
MILESTONE_NAME = re.compile(r"\b(M[123])\b|(v1\.0 GA|v1\.0 target|v1\.0)")
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
TEXT_DATE = re.compile(
    r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b"
)
DECISION_DEF = re.compile(r"^\|\s*(D\d+)\b")


def milestones(plan: Path = PLAN) -> dict[str, dt.date]:
    out: dict[str, dt.date] = {}
    for line in (plan / OWNER_DATES).read_text(encoding="utf-8").splitlines():
        m = MILESTONE_ROW.match(line)
        if m:
            out["v1.0" if m.group(1).startswith("v1.0") else m.group(1)] = dt.date.fromisoformat(
                m.group(2)
            )
    return out


NEAR = 20  # characters between a milestone name and a date that states that milestone's date
NOT_A_MILESTONE_DATE = re.compile(
    r"as[- ]of|updated|confirmed|decided|locked|from|since|until", re.I
)


def _dated_spans(line: str) -> list[tuple[int, int, dt.date]]:
    spans = [
        (m.start(), m.end(), dt.date.fromisoformat(m.group(1))) for m in ISO_DATE.finditer(line)
    ]
    for m in TEXT_DATE.finditer(line):
        day, mon, year = m.groups()
        spans.append(
            (m.start(), m.end(), dt.datetime.strptime(f"{day} {mon} {year}", "%d %b %Y").date())
        )
    return spans


def milestone_dates(line: str) -> list[tuple[str, dt.date]]:
    """(milestone, date) pairs where the date sits next to the name and states its date.

    Dates qualified as something else ("as-of 30 Oct", "updated 27 Sep", "from 28 Sep until
    the M1 review") are ignored.
    """
    pairs = []
    for name_m in MILESTONE_NAME.finditer(line):
        name = name_m.group(1) or "v1.0"
        for start, end, date in _dated_spans(line):
            gap = (
                line[end : name_m.start()] if end <= name_m.start() else line[name_m.end() : start]
            )
            if len(gap) > NEAR:
                continue
            context = line[max(0, start - 14) : end] + gap
            if NOT_A_MILESTONE_DATE.search(context):
                continue
            pairs.append((name, date))
    return pairs


def _docs(plan: Path) -> list[Path]:
    return sorted(p for p in plan.glob("*.md"))


def check(plan: Path = PLAN) -> list[str]:
    problems: list[str] = []
    owned = milestones(plan)
    if set(owned) != {"M1", "M2", "M3", "v1.0"}:
        return [f"{OWNER_DATES}: milestone table not found or incomplete (got {sorted(owned)})"]
    for doc in _docs(plan):
        lines = doc.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            where = f"{doc.name}:{n}"
            # 1. milestone dates in step with 09
            if doc.name != OWNER_DATES:
                for name, date in milestone_dates(line):
                    if date != owned[name]:
                        problems.append(
                            f"{where}: {name} date {date} disagrees with plan 09 ({owned[name]})"
                        )
            # 2. phase-placement tables only in 09 (and 14 §9)
            if doc.name not in PHASE_TABLE_ALLOWED and line.startswith("|") and n < len(lines):
                cells = [c.strip().strip("*") for c in line.strip("|").split("|")]
                if "Phase" in cells and set(lines[n].replace("|", "").strip()) <= set("-: "):
                    problems.append(f"{where}: phase-placement table outside plan 09")
            # 3. decisions defined only in 13
            decision = DECISION_DEF.match(line)
            if doc.name != OWNER_DECISIONS and decision:
                problems.append(
                    f"{where}: decision row {decision.group(1)} defined outside plan 13"
                )
    return problems


def main() -> int:
    problems = check()
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print(f"doc lint OK · milestones {', '.join(f'{k} {v}' for k, v in milestones().items())}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
