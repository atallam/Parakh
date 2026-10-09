"""The wider stock universe for the staged scale-up (F01 full; plan 09 Phase 4; plan 05 §1).

    config/universe_directory/{mid,large,small}.csv      symbol,isin,name,sector,profile,listed_on
    universe.yaml  rollout: pilot | mid | mid_large | all

The pilot stays in universe.yaml. A rollout stage adds the directory files for the caps it names, so
Mid goes first (150), then Large (100), then Small (250), each only after the previous stage ran clean.
Rows are validated like pilot ones (ISO 6166 check digit, known profile); a bad row stops the load with
its file and line, never a silent skip. The CSVs come from `parakh universe import`.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from parakh.configs.models import Cap, Security

STAGES: dict[str, tuple[Cap, ...]] = {
    "pilot": (),
    "mid": ("mid",),
    "mid_large": ("mid", "large"),
    "all": ("mid", "large", "small"),
}
COLUMNS = ["symbol", "isin", "name", "sector", "profile", "listed_on"]
SOURCE = {"large": "AMFI list", "mid": "AMFI list", "small": "Nifty Smallcap 250"}


def read_cap(path: Path, cap: Cap) -> list[Security]:
    if not path.exists():
        return []
    out: list[Security] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            try:
                out.append(
                    Security(
                        symbol=row["symbol"].strip(), isin=row["isin"].strip(), name=row["name"].strip(),
                        cap=cap, cap_source=SOURCE[cap], profile=(row.get("profile") or "standard").strip(),  # type: ignore[arg-type]
                        sector=(row.get("sector") or "").strip() or None,
                        listed_on=dt.date.fromisoformat(row["listed_on"]) if row.get("listed_on") else None,
                    )
                )  # fmt: skip
            except Exception as exc:
                raise ValueError(f"{path.name} line {n}: {exc}") from exc
    return out


def load_directory(root: Path, stage: str) -> list[Security]:
    out: list[Security] = []
    for cap in STAGES[stage]:
        out += read_cap(root / f"{cap}.csv", cap)
    return out


def import_rows(src: Path, cap: Cap, dest_root: Path) -> int:
    """Validate a vendor CSV (same columns) and write it as the cap's directory file."""
    rows = read_cap(src, cap)
    seen: set[str] = set()
    for s in rows:
        if s.isin in seen:
            raise ValueError(f"duplicate ISIN {s.isin} in {src.name}")
        seen.add(s.isin)
    dest_root.mkdir(parents=True, exist_ok=True)
    with (dest_root / f"{cap}.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        for s in sorted(rows, key=lambda x: x.symbol):
            w.writerow([s.symbol, s.isin, s.name, s.sector or "", s.profile, s.listed_on or ""])
    return len(rows)
