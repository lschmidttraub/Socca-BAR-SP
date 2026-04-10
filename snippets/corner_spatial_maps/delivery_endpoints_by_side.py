"""Delivery endpoints of Barcelona's corners, split by side.

Renders ``delivery_endpoints_by_side.png`` — a 2-panel dark-themed
half-pitch figure. The left panel shows every left-side corner (taken
from the bottom of the pitch) and the right panel every right-side
corner, each scatter-plotted at its first-meaningful-delivery endpoint
and coloured by target zone. Dashed boxes outline the six target
zones as a guide.

Unlike the 3-panel ``spatial_profile`` view (which mirrors all corners
onto the same side), this plot keeps every corner on its original
side, so the spatial asymmetry between Barcelona's left- and
right-side routines is directly visible.

Run from the repo root:

    uv run python snippets/corner_spatial_maps/delivery_endpoints_by_side.py
    uv run python snippets/corner_spatial_maps/delivery_endpoints_by_side.py Barcelona ./my_out
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from mplsoccer import Pitch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    DARK_FIG_COLOR,
    DARK_LINE_COLOR,
    DARK_PITCH_COLOR,
    ZONE_COLORS,
    ZONE_ORDER,
    collect_corner_sequences,
    display_point,
    iter_side_subsets,
    side_title,
)

DEFAULT_OUTPUT_DIR = Path("corner_spatial_plots")
OUTPUT_NAME = "delivery_endpoints_by_side.png"


def _apply_dark_header(
    fig: plt.Figure,
    title: str,
    subtitle: str | None = None,
    *,
    title_y: float = 0.975,
    subtitle_y: float = 0.935,
    title_size: int = 18,
    subtitle_size: float = 11.0,
) -> None:
    fig.text(
        0.5, title_y, title,
        ha="center", va="top",
        color="white", fontsize=title_size, fontweight="bold",
    )
    if subtitle:
        fig.text(
            0.5, subtitle_y, subtitle,
            ha="center", va="top",
            color="white", fontsize=subtitle_size,
        )


def _dark_pitch_figure(
    ncols: int,
    *,
    figsize: tuple[float, float],
) -> tuple[plt.Figure, list[plt.Axes], Pitch]:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color=DARK_PITCH_COLOR,
        line_color=DARK_LINE_COLOR,
        linewidth=1.7,
    )
    fig, axes = plt.subplots(1, ncols, figsize=figsize)
    axes = [axes] if ncols == 1 else list(axes)
    fig.patch.set_facecolor(DARK_FIG_COLOR)

    for ax in axes:
        ax.set_facecolor(DARK_FIG_COLOR)
        ax.grid(False)
        pitch.draw(ax=ax)
        ax.set_xticks([])
        ax.set_yticks([])

    fig.subplots_adjust(top=0.8, bottom=0.14, wspace=0.22)
    return fig, axes, pitch


def _draw_corner_marker(pitch: Pitch, ax: plt.Axes, side: str) -> None:
    y = 79.4 if side == "top" else 0.6
    marker = "v" if side == "top" else "^"
    pitch.scatter(
        [119.6], [y], ax=ax, marker=marker, s=260,
        color="#ffd100", edgecolors=DARK_FIG_COLOR, linewidth=0.8, zorder=6,
    )


def _draw_zone_boxes(ax: plt.Axes, *, line_color: str) -> None:
    boxes = [
        (114, 0, 6, 33),
        (114, 33, 6, 14),
        (114, 47, 6, 33),
        (102, 28, 12, 24),
        (96, 18, 6, 44),
    ]
    for x, y, w, h in boxes:
        rect = Rectangle(
            (x, y), w, h,
            fill=False, lw=1.2, ls="--",
            ec=line_color, alpha=0.65,
        )
        ax.add_patch(rect)


def _add_dark_legend(
    fig: plt.Figure,
    handles: list[Any],
    ncol: int = 4,
) -> None:
    legend = fig.legend(
        handles=handles,
        loc="lower center",
        ncol=ncol,
        frameon=True,
        bbox_to_anchor=(0.5, 0.02),
        fontsize=10,
    )
    legend.get_frame().set_facecolor("#1d1d1d")
    legend.get_frame().set_edgecolor("#1d1d1d")
    for text in legend.get_texts():
        text.set_color("white")


def plot_delivery_endpoints_by_side(
    sequences: list[dict[str, Any]],
    output_path: Path,
    focus_team: str = "Barcelona",
) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        f"{focus_team} corners - delivery endpoints by side",
        "Dot = first meaningful delivery endpoint   Dashed boxes = target-zone guide",
    )

    for ax, (side, subset) in zip(axes, iter_side_subsets(sequences)):
        _draw_zone_boxes(ax, line_color=DARK_LINE_COLOR)
        _draw_corner_marker(pitch, ax, side)
        for zone in ZONE_ORDER:
            pts = [
                display_point((seq["delivery_end_x"], seq["delivery_end_y"]), side)
                for seq in subset
                if seq["delivery_zone"] == zone
            ]
            pts = [pt for pt in pts if pt is not None]
            if not pts:
                continue
            xs, ys = zip(*pts)
            pitch.scatter(
                xs, ys, ax=ax, s=58, color=ZONE_COLORS[zone],
                edgecolors="white", linewidth=0.55, alpha=0.9, label=zone,
            )
        ax.set_title(
            f"{side_title(side)}  -  n = {len(subset)}",
            color="white",
            fontsize=13,
            pad=12,
        )

    _add_dark_legend(
        fig,
        [
            Line2D(
                [0], [0], marker="o", color="w",
                markerfacecolor=ZONE_COLORS[zone],
                markeredgecolor="white", markersize=8, lw=0, label=zone,
            )
            for zone in ZONE_ORDER
            if any(seq["delivery_zone"] == zone for seq in sequences)
        ]
        + [
            Line2D(
                [0], [0], marker="^", color="w",
                markerfacecolor="#ffd100",
                markeredgecolor=DARK_FIG_COLOR,
                markersize=11, lw=0, label="Corner kick",
            )
        ],
        ncol=4,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_path,
        dpi=150,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
    )
    plt.close(fig)


def main(argv: list[str]) -> int:
    # Positional CLI args: [team] [output_dir]. No argparse.
    # NOTE: exact-match team names only. Some UCL teams (PSG, Bayern,
    # Monaco, Leverkusen, Dortmund) are spelled differently in
    # matches.csv vs the StatsBomb events and will not match. Barcelona
    # is spelled consistently in both sources.
    focus_team = argv[1] if len(argv) > 1 else "Barcelona"
    output_dir = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUTPUT_DIR

    print(f"Corner delivery endpoints (by side) - {focus_team}")
    print("-" * 60)
    print("Collecting corner sequences from StatsBomb events ...")
    sequences = collect_corner_sequences(focus_team)

    if not sequences:
        print(f"  No corners found for '{focus_team}'. Nothing to plot.")
        return 1

    by_side = Counter(seq["corner_side"] for seq in sequences)
    left = by_side.get("bottom", 0)
    right = by_side.get("top", 0)

    print(f"  Corners processed   : {len(sequences)}")
    print(f"    Left-side corners : {left}")
    print(f"    Right-side corners: {right}")

    zone_counts: Counter[str] = Counter(seq["delivery_zone"] for seq in sequences)
    for zone in ZONE_ORDER:
        print(f"    {zone:<18}: {zone_counts.get(zone, 0):>3d}")

    output_path = output_dir / OUTPUT_NAME
    print()
    print(f"Saving plot to {output_dir}/ ...")
    plot_delivery_endpoints_by_side(sequences, output_path, focus_team=focus_team)
    print(f"  saved {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
