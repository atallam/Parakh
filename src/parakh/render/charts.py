"""Report charts (plan 12 §7). Colours come from config/ui_tokens.yaml only (token lint).

- price chart: close, 50/200 DMA, fair-value band, your average cost, the next event;
- score chart: value and momentum by month with the verdict thresholds and the ±hysteresis
  band around each, so a flip (or a non-flip) explains itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from parakh.render.tokens import tokens  # noqa: E402


def _c(name: str) -> str:
    return tokens().colors[name]


def _style(ax: Any) -> None:
    ax.set_facecolor(_c("bg_card"))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(_c("border"))
    ax.tick_params(colors=_c("text_muted"), labelsize=8)
    ax.grid(axis="y", color=_c("bg_muted"), linewidth=0.8)


def price_chart(snap: dict[str, Any], path: Path, avg_cost: float | None = None) -> Path | None:
    """Close with DMAs, the fair-value band, the next event and (if owned) the average cost."""
    ch = snap.get("chart") or {}
    if not ch.get("dates"):
        return None
    fig, ax = plt.subplots(figsize=(8, 3.9), dpi=140)
    fig.patch.set_facecolor(_c("bg_card"))
    _style(ax)
    x = list(range(len(ch["dates"])))
    ax.plot(x, ch["close"], color=_c("navy"), linewidth=1.6, label="Close")
    ax.plot(
        x,
        [v if v is not None else float("nan") for v in ch["dma50"]],
        color=_c("accent"),
        linewidth=1.0,
        label="50 DMA",
    )
    ax.plot(
        x,
        [v if v is not None else float("nan") for v in ch["dma200"]],
        color=_c("caution"),
        linewidth=1.0,
        label="200 DMA",
    )
    if ch.get("fair_value_low") is not None:
        ax.axhspan(
            ch["fair_value_low"],
            ch["fair_value_high"],
            color=_c("positive"),
            alpha=0.12,
            label="Fair-value band",
        )
    if avg_cost:
        ax.axhline(
            avg_cost, color=_c("neutral"), linestyle="--", linewidth=1.0, label="Average cost"
        )
    ne = ch.get("next_event")
    if ne and ne.get("date") in ch["dates"]:
        i = ch["dates"].index(ne["date"])
        ax.axvline(
            i,
            color=_c("caution_strong"),
            linestyle=":",
            linewidth=1.0,
            label=ne.get("label", "Next event"),
        )
    ticks = list(range(0, len(x), max(1, len(x) // 6)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([ch["dates"][i][:7] for i in ticks])
    closes = [v for v in ch["close"] if v is not None]
    fv_hi = ch.get("fair_value_high")
    if closes and fv_hi is not None and fv_hi <= 3 * max(closes):
        ax.set_ylim(
            top=max(max(closes), fv_hi) * 1.05
        )  # a far-away band would flatten the price line
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        fontsize=7,
        frameon=False,
        labelcolor=_c("text_muted"),
        ncol=5,
    )
    ax.set_title(
        f"{snap['symbol']} · {snap['period']} · price context",
        loc="left",
        fontsize=9,
        color=_c("text"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def score_chart(symbol: str, series: list[dict[str, Any]], policy: Any, path: Path) -> Path | None:
    """Value and momentum by month; thresholds as dashed lines, hysteresis as a shaded band."""
    pts = [
        p for p in series if p.get("value_score") is not None or p.get("momentum_score") is not None
    ]
    if not pts:
        return None
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.0), dpi=140, sharey=True)
    fig.patch.set_facecolor(_c("bg_card"))
    labels = [p["period"] for p in pts]
    for ax, key, title, bands, colour in (
        (axes[0], "value_score", "Value", policy.value_bands, "positive"),
        (axes[1], "momentum_score", "Momentum", policy.momentum_bands, "accent"),
    ):
        _style(ax)
        ys = [p.get(key) for p in pts]
        ax.plot(
            range(len(pts)),
            [float("nan") if y is None else y for y in ys],
            color=_c(colour),
            marker="o",
            markersize=3,
            linewidth=1.5,
        )
        for cut in (bands.high, bands.low):
            ax.axhline(cut, color=_c("neutral"), linestyle="--", linewidth=0.8)
            ax.axhspan(
                cut - policy.hysteresis, cut + policy.hysteresis, color=_c("neutral"), alpha=0.10
            )
        ax.set_ylim(0, 100)
        ax.set_xticks(range(len(pts)))
        ax.set_xticklabels([lb[2:] for lb in labels], rotation=45, fontsize=7)
        ax.set_title(title, loc="left", fontsize=9, color=_c("text"))
    fig.suptitle(
        f"{symbol} · score trajectory (dashed: thresholds; shaded: ±{policy.hysteresis:g} hysteresis)",
        fontsize=8,
        color=_c("text_muted"),
        x=0.01,
        ha="left",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path
