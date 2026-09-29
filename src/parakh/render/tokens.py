"""Status styling from config/ui_tokens.yaml, for every surface (plan 12 §3; AC-F22.2, F22.3).

style = status("verdict", "BUY")   # → colour hex, icon, word
label(style)                         # "🟢 ▲ BUY"
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from parakh.configs import load_file
from parakh.configs.models import UiTokens


@lru_cache(maxsize=1)
def tokens() -> UiTokens:
    return load_file("ui_tokens.yaml", UiTokens)


@dataclass(frozen=True)
class Style:
    family: str
    status: str
    token: str
    color: str
    color_dark: str
    icon: str
    word: str
    outline: bool


def status(family: str, value: str) -> Style:
    t = tokens()
    key = value.upper().replace(" ", "_")
    try:
        s = t.statuses[family][key]
    except KeyError as exc:
        raise KeyError(f"no style for {family}.{key} in ui_tokens.yaml") from exc
    return Style(
        family, key, s.token, t.colors[s.token], t.colors_dark[s.token], s.icon, s.word, s.outline
    )


def label(style: Style) -> str:
    """Colour-independent text form: icon + word (colour is never the only carrier)."""
    return f"{style.icon} {style.word}"
