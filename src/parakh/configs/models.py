"""Pydantic schemas for every file in config/ (plan 04 §3.2: thresholds only in YAML).

A config file that doesn't match its schema stops the run before any data is fetched;
`parakh config validate` runs the same checks in CI.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
MCP_TOOL_PREFIX = "mcp__parakh__"
# Claude Agent SDK built-in tools. None may appear in an agent's allow-list (plan 15 §6.2, AG-01).
SDK_BUILTIN_TOOLS = frozenset(
    {
        "Agent",
        "Bash",
        "BashOutput",
        "Edit",
        "Glob",
        "Grep",
        "KillShell",
        "MultiEdit",
        "NotebookEdit",
        "Read",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)


def isin_check_digit_ok(isin: str) -> bool:
    """ISO 6166 check: letters → numbers (A=10…Z=35), then Luhn over the digits."""
    if not ISIN_RE.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# -- universe.yaml ---------------------------------------------------------------------------
Cap = Literal["large", "mid", "small"]
Profile = Literal[
    "standard",
    "bank",
    "nbfc",
    "insurance",
    "airline_lease_heavy",
    "conglomerate_sotp",
    "order_book",
    "capital_market_intermediary",
    "new_age",
    "cyclical",
    "utility",
]


class PreviousIsin(Strict):
    """An ISIN the security had before a split or face-value change (spike ④; plan 05 isin_history)."""

    isin: str
    changed_on: dt.date
    reason: Literal["split", "face_value", "merger", "other"]
    source: str

    @field_validator("isin")
    @classmethod
    def _isin(cls, v: str) -> str:
        if not isin_check_digit_ok(v):
            raise ValueError(f"{v} is not a valid ISIN (format or check digit)")
        return v


class Security(Strict):
    symbol: str
    isin: str
    name: str
    cap: Cap
    cap_source: str
    profile: Profile
    golden: bool = False
    listed_on: dt.date | None = None
    previous_isins: list[PreviousIsin] = []

    @field_validator("isin")
    @classmethod
    def _isin(cls, v: str) -> str:
        if not isin_check_digit_ok(v):
            raise ValueError(f"{v} is not a valid ISIN (format or check digit)")
        return v


class UniverseConfig(Strict):
    mode: Literal["pilot", "cap", "all"]
    small_cap_index: str
    pilot: list[Security]

    @model_validator(mode="after")
    def _unique(self) -> UniverseConfig:
        for attr in ("isin", "symbol"):
            values = [getattr(s, attr) for s in self.pilot]
            dupes = {v for v in values if values.count(v) > 1}
            if dupes:
                raise ValueError(f"duplicate {attr} in pilot: {sorted(dupes)}")
        return self

    @property
    def golden(self) -> list[Security]:
        return [s for s in self.pilot if s.golden]

    def by_isin(self, isin: str) -> Security | None:
        return next((s for s in self.pilot if s.isin == isin), None)


# -- sources.yaml ----------------------------------------------------------------------------
class SourceSpec(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    tier: Literal["T1", "T2", "T3"]
    data_types: list[str] = Field(min_length=1)
    access: str
    terms: str
    cadence: str


class SourcesConfig(Strict):
    sources: list[SourceSpec]

    @model_validator(mode="after")
    def _unique(self) -> SourcesConfig:
        ids = [s.id for s in self.sources]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate source ids: {sorted(dupes)}")
        return self

    def ids(self) -> set[str]:
        return {s.id for s in self.sources}


# -- data_quality.yaml -----------------------------------------------------------------------
class PriceDq(Strict):
    history_years: int = Field(ge=1, le=30)
    close_mismatch_pct: float = Field(gt=0, le=10)
    cross_check_sessions: int = Field(ge=1, le=60)
    max_unexplained_move_ratio: float = Field(gt=0, lt=1)
    max_stale_trading_days: int = Field(ge=1, le=30)


class FundamentalsDq(Strict):
    min_annual_years: int = Field(ge=1, le=30)
    xbrl_tolerance_cr: float = Field(gt=0)
    xbrl_tolerance_pct: float = Field(gt=0, le=10)
    xbrl_quarters: int = Field(ge=1, le=20)
    max_latest_quarter_age_days: int = Field(ge=30, le=400)


class DataQualityConfig(Strict):
    prices: PriceDq
    fundamentals: FundamentalsDq


# -- lenses.yaml -----------------------------------------------------------------------------
class LensToggle(Strict):
    enabled: bool
    caps: list[Cap]
    informational: bool = False  # shown in reports, no verdict-policy row yet (plan 04 §1.3)


class LensesConfig(Strict):
    lenses: dict[str, LensToggle]

    @field_validator("lenses")
    @classmethod
    def _ids(cls, v: dict[str, LensToggle]) -> dict[str, LensToggle]:
        bad = [k for k in v if not re.fullmatch(r"[a-z][a-z0-9_]*", k)]
        if bad:
            raise ValueError(f"lens ids must be snake_case: {bad}")
        return v


# -- flags.yaml (plan 09 §1 feature flags) ----------------------------------------------------
class Toggle(Strict):
    enabled: bool


class AlertsFlags(Strict):
    dry_run: bool


class LlmFlags(Strict):
    budget_tokens: int = Field(ge=0)


class McpFlags(Strict):
    toolsets: dict[str, bool]


class FlagsConfig(Strict):
    alerts: AlertsFlags
    watchlist: Toggle
    qualitative: Toggle
    llm: LlmFlags
    ui: Toggle
    mcp: McpFlags


# -- agents.yaml (plan 15 §6.2) ---------------------------------------------------------------
class AgentDefaults(Strict):
    model_id: str
    max_turns: int = Field(ge=1, le=50)
    token_budget: int = Field(ge=0)


class AgentConfig(Strict):
    enabled: bool = False
    description: str
    first_phase: int = Field(ge=0, le=7)
    prompt_id: str | None = None
    model_id: str | None = None
    max_turns: int | None = Field(default=None, ge=1, le=50)
    token_budget: int | None = Field(default=None, ge=0)
    allowed_tools: list[str]

    @field_validator("allowed_tools")
    @classmethod
    def _tools(cls, v: list[str]) -> list[str]:
        builtin = sorted(set(v) & SDK_BUILTIN_TOOLS)
        if builtin:
            raise ValueError(f"built-in SDK tools are never allowed (AG-01): {builtin}")
        foreign = [t for t in v if not t.startswith(MCP_TOOL_PREFIX)]
        if foreign:
            raise ValueError(f"agents may only use {MCP_TOOL_PREFIX}* tools (AG-01): {foreign}")
        return v

    @model_validator(mode="after")
    def _enabled_needs_prompt(self) -> AgentConfig:
        if self.enabled and not self.prompt_id:
            raise ValueError("an enabled agent needs a pinned prompt_id (P3)")
        return self


class AgentsConfig(Strict):
    dry_run: bool
    defaults: AgentDefaults
    agents: dict[str, AgentConfig]

    @field_validator("agents")
    @classmethod
    def _ids(cls, v: dict[str, AgentConfig]) -> dict[str, AgentConfig]:
        bad = [k for k in v if not re.fullmatch(r"AGENT\.[a-z][a-z0-9_]*", k)]
        if bad:
            raise ValueError(f"agent ids must look like AGENT.<name>: {bad}")
        return v


# -- ui_tokens.yaml (plan 12 §3) --------------------------------------------------------------
class StatusStyle(Strict):
    token: str
    icon: str
    word: str
    outline: bool = False


class UiTokens(Strict):
    colors: dict[str, str]
    colors_dark: dict[str, str]
    fonts: dict[str, str]
    statuses: dict[str, dict[str, StatusStyle]]

    @model_validator(mode="after")
    def _check(self) -> UiTokens:
        for palette_name, palette in (("colors", self.colors), ("colors_dark", self.colors_dark)):
            bad = {k: v for k, v in palette.items() if not HEX_RE.match(v)}
            if bad:
                raise ValueError(f"{palette_name}: not #RRGGBB: {bad}")
        missing_dark = sorted(set(self.colors) - set(self.colors_dark))
        if missing_dark:
            raise ValueError(f"colors_dark is missing: {missing_dark}")
        for family, styles in self.statuses.items():
            for status, style in styles.items():
                if style.token not in self.colors:
                    raise ValueError(f"statuses.{family}.{status}: unknown token {style.token}")
        return self
