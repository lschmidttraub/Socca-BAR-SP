"""First-touch map after Barcelona's offensive corners.

Renders ``corner_first_touch_map.png`` — a 2-panel dark-themed
half-pitch figure. Each dot marks the first team touch after a corner
(Shot / Pass / Carry) and, when a tracked follow-up action exists, an
arrow shows where that touch ended up. The left panel shows left-side
corners (taken from the bottom of the pitch) and the right panel
right-side corners.

The first touch is the first post-corner event with a tracked type
(Ball Receipt*, Carry, Dribble, Duel, Pass, Shot, …) and a location.
Its "kind" is the kind of the first *actionable* event (Pass / Shot /
Carry) from that touch onwards.

Run from the repo root:

    uv run python snippets/corner_spatial_maps/first_touch_map.py
    uv run python snippets/corner_spatial_maps/first_touch_map.py Barcelona ./my_out
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    DARK_FIG_COLOR,
    DARK_LINE_COLOR,
    DARK_PITCH_COLOR,
    FIRST_TOUCH_COLORS,
    collect_corner_sequences,
    display_point,
    iter_side_subsets,
    side_title,
)

DEFAULT_OUTPUT_DIR = Path("corner_spatial_plots")
OUTPUT_NAME = "corner_first_touch_map.png"


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
        line_color=DARK_LINE_COLOR,  # ivory white pitch lines
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


def plot_first_touch_map(
    sequences: list[dict[str, Any]],
    output_path: Path,
    focus_team: str = "Barcelona",
) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        f"{focus_team} corners - first touch after the corner",
        "Dot = first touch location   Arrow = what the team did next with that first touch",
    )

    for ax, (side, subset) in zip(axes, iter_side_subsets(sequences)):
        _draw_corner_marker(pitch, ax, side)
        action_counter: Counter[str] = Counter()
        for seq in subset:
            kind = seq["first_touch_kind"]
            start = display_point((seq["first_touch_x"], seq["first_touch_y"]), side)
            end = display_point(
                (seq["first_touch_end_x"], seq["first_touch_end_y"]),
                side,
            )
            if kind not in FIRST_TOUCH_COLORS or start is None:
                continue
            action_counter[kind] += 1
            color = FIRST_TOUCH_COLORS[kind]
            pitch.scatter(
                [start[0]], [start[1]], ax=ax, s=64,
                color=color, edgecolors="white", linewidth=0.65, zorder=4,
            )
            if end is not None:
                pitch.arrows(
                    start[0], start[1], end[0], end[1], ax=ax,
                    color=color, width=1.7, headwidth=4.5, headlength=4.5,
                    alpha=0.82, zorder=3,
                )
        ax.set_title(
            f"{side_title(side)}  -  n = {len(subset)}",
            color="white",
            fontsize=13,
            pad=12,
        )
        summary = "   ".join(
            f"{label.lower()}s: {action_counter.get(label, 0)}"
            for label in ("Shot", "Pass", "Carry")
        )
        ax.text(
            62, 1.2, summary, color="white", fontsize=9,
            bbox={
                "facecolor": "#1d1d1d",
                "edgecolor": "none",
                "alpha": 0.6,
                "pad": 3,
            },
        )

    _add_dark_legend(
        fig,
        [
            Line2D(
                [0], [0], marker="o", color="w",
                markerfacecolor=FIRST_TOUCH_COLORS[label],
                markeredgecolor="white", markersize=8, lw=0, label=label,
            )
            for label in ("Shot", "Pass", "Carry")
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

    print(f"Corner first-touch map - {focus_team}")
    print("-" * 60)
    print("Collecting corner sequences from StatsBomb events ...")
    sequences = collect_corner_sequences(focus_team)

    if not sequences:
        print(f"  No corners found for '{focus_team}'. Nothing to plot.")
        return 1

    kinds = Counter(seq["first_touch_kind"] for seq in sequences)
    tracked = sum(kinds.get(k, 0) for k in ("Shot", "Pass", "Carry"))
    untracked = sum(v for k, v in kinds.items() if k not in ("Shot", "Pass", "Carry"))

    print(f"  Corners processed        : {len(sequences)}")
    print(f"  First touches (tracked)  : {tracked}")
    for label in ("Shot", "Pass", "Carry"):
        print(f"    {label:<6}: {kinds.get(label, 0):>3d}")
    print(f"  No tracked first touch   : {untracked}")

    output_path = output_dir / OUTPUT_NAME
    print()
    print(f"Saving plot to {output_dir}/ ...")
    plot_first_touch_map(sequences, output_path, focus_team=focus_team)
    print(f"  saved {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
