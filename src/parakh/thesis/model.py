"""THESIS.md front matter schema (plan 05 §2.4; AC-F09.9) and its parser. Read-only on the file."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from parakh.configs.models import ISIN_RE

KM_ID = re.compile(r"^KM[1-5]$")
BR_ID = re.compile(r"^BR[1-5]$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ThesisOriginal(_Strict):
    written_on: dt.date
    statement: str = Field(min_length=10)


class KeyMetric(_Strict):
    id: str
    text: str = Field(min_length=3)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not KM_ID.match(v):
            raise ValueError("key metric ids are KM1…KM5")
        return v


class Breaker(_Strict):
    id: str
    text: str = Field(min_length=3)
    check: Literal["metric", "llm_flag"]
    rule: str | None = None

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not BR_ID.match(v):
            raise ValueError("breaker ids are BR1…BR5")
        return v

    @model_validator(mode="after")
    def _rule_matches_check(self) -> Breaker:
        if self.check == "metric" and not self.rule:
            raise ValueError(
                f"{self.id}: a metric breaker needs a rule, e.g. revenue_growth_yoy_pct < -10"
            )
        if self.check == "llm_flag" and self.rule:
            raise ValueError(
                f"{self.id}: an llm_flag breaker has no rule; the concall agent only flags it"
            )
        return self


class ThesisFront(_Strict):
    symbol: str
    isin: str
    thesis_version: int = Field(ge=1)
    original: ThesisOriginal
    key_metrics: list[KeyMetric] = Field(default_factory=list, max_length=5)
    breakers: list[Breaker] = Field(default_factory=list, max_length=5)
    sizing_rationale: str | None = None
    review_by: dt.date | None = None

    @field_validator("isin")
    @classmethod
    def _isin(cls, v: str) -> str:
        if not ISIN_RE.match(v):
            raise ValueError("isin must be a 12-character ISIN")
        return v

    @model_validator(mode="after")
    def _unique(self) -> ThesisFront:
        for label, items in (("key metric", self.key_metrics), ("breaker", self.breakers)):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ids must be unique")
        return self


@dataclass
class ParsedThesis:
    path: Path
    exists: bool
    front: ThesisFront | None = None
    body: str = ""
    errors: list[str] = field(default_factory=list)
    raw_original: dict | None = None  # for the "original never changes" hook


FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)(.*)\Z", re.DOTALL)


def parse_text(text: str, path: Path | None = None) -> ParsedThesis:
    out = ParsedThesis(path=path or Path("THESIS.md"), exists=True)
    m = FRONT.match(text.lstrip("﻿"))
    if not m:
        out.errors.append("THESIS.md must start with a YAML front matter block between --- lines")
        return out
    out.body = m.group(2).strip()
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        out.errors.append(f"front matter is not valid YAML: {str(exc).splitlines()[0]}")
        return out
    if not isinstance(data, dict):
        out.errors.append("front matter must be a mapping")
        return out
    out.raw_original = data.get("original") if isinstance(data.get("original"), dict) else None
    try:
        out.front = ThesisFront.model_validate(data)
    except ValidationError as exc:
        out.errors.extend(
            f"{'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in exc.errors()
        )
    return out


def read_thesis(path: Path) -> ParsedThesis:
    """Read THESIS.md; the file is never opened for writing anywhere in Parakh (AC-F09.4)."""
    if not path.exists():
        return ParsedThesis(path=path, exists=False)
    return parse_text(path.read_text(encoding="utf-8"), path)
