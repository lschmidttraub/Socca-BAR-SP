"""Spatial profile of Barcelona's offensive corners.

Renders ``spatial_profile.png`` — a 3-panel half-pitch figure showing,
for every Barcelona corner in the UCL 2025-26 campaign:

1. Arrows of every first-meaningful-delivery route, colour-coded by
   routine type (Direct inswing / outswing / other / Short corner).
2. Scatter of the delivery endpoints, colour-coded by target zone,
   with the six dashed zone-boundary boxes overlaid as a guide.
3. First-shot locations with marker size proportional to StatsBomb xG.

All three panels use a half-pitch view with a light background.
Corners taken from the top of the pitch are y-flipped in
``_loader.collect_corner_sequences`` so every corner appears on the
same side of the figure.

Run from the repo root:

    uv run python snippets/corner_spatial_maps/spatial_profile.py
    uv run python snippets/corner_spatial_maps/spatial_profile.py Barcelona ./my_out
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from mplsoccer import Pitch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    FOCUS_COLOR,
    ROUTINE_COLORS,
    ROUTINE_ORDER,
    ZONE_COLORS,
    ZONE_ORDER,
    collect_corner_sequences,
)

DEFAULT_OUTPUT_DIR = Path("corner_spatial_plots")
OUTPUT_NAME = "spatial_profile.png"


def _apply_light_header(
    fig: plt.Figure,
    title: str,
    subtitle: str | None = None,
    *,
    title_y: float = 0.975,
    subtitle_y: float = 0.935,
    title_size: int = 16,
    subtitle_size: float = 11.0,
) -> None:
    fig.text(
        0.5, title_y, title,
        ha="center", va="top",
        color="#111111", fontsize=title_size, fontweight="bold",
    )
    if subtitle:
        fig.text(
            0.5, subtitle_y, subtitle,
            ha="center", va="top",
            color="#333333", fontsize=subtitle_size,
        )


def _draw_zone_boxes(ax: plt.Axes, *, line_color: str = "#777777") -> None:
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


def plot_spatial_profile(
    sequences: list[dict[str, Any]],
    output_path: Path,
    focus_team: str = "Barcelona",
) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#c7d5cc",
        half=True,
    )
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.subplots_adjust(top=0.82, bottom=0.08, wspace=0.22)

    for ax in axes:
        pitch.draw(ax=ax)

    # Panel 1 — delivery routes coloured by routine type
    for seq in sequences:
        sx = seq["delivery_start_x"]
        sy = seq["delivery_start_y"]
        ex = seq["delivery_end_x"]
        ey = seq["delivery_end_y"]
        if None not in (sx, sy, ex, ey):
            pitch.arrows(
                sx, sy, ex, ey, ax=axes[0],
                color=ROUTINE_COLORS[seq["routine_type"]],
                width=1.5, headwidth=4, headlength=4, alpha=0.55,
            )
    axes[0].set_title("First meaningful delivery routes")
    axes[0].legend(
        handles=[
            Line2D([0], [0], color=ROUTINE_COLORS[label], lw=2, label=label)
            for label in ROUTINE_ORDER
            if any(s["routine_type"] == label for s in sequences)
        ],
        loc="lower left",
        fontsize=8,
    )

    # Panel 2 — delivery endpoints coloured by target zone
    _draw_zone_boxes(axes[1])
    for zone in ZONE_ORDER:
        pts = [
            (s["delivery_end_x"], s["delivery_end_y"])
            for s in sequences
            if s["delivery_zone"] == zone
            and s["delivery_end_x"] is not None
            and s["delivery_end_y"] is not None
        ]
        if not pts:
            continue
        xs, ys = zip(*pts)
        pitch.scatter(
            xs, ys, ax=axes[1], s=55, color=ZONE_COLORS[zone],
            edgecolors="white", linewidth=0.5, alpha=0.85, label=zone,
        )
    axes[1].set_title("Delivery endpoints and target zones")
    axes[1].legend(loc="lower left", fontsize=8)

    # Panel 3 — first shot locations sized by xG
    shots = [
        s for s in sequences
        if s["first_shot_x"] is not None and s["first_shot_y"] is not None
    ]
    if shots:
        xs = [s["first_shot_x"] for s in shots]
        ys = [s["first_shot_y"] for s in shots]
        sizes = [max(s["first_shot_xg"] * 1200, 40) for s in shots]
        pitch.scatter(
            xs, ys, ax=axes[2], s=sizes, color=FOCUS_COLOR,
            edgecolors="white", linewidth=0.7, alpha=0.8,
        )
    axes[2].set_title("First-shot locations (size = xG)")

    _apply_light_header(
        fig,
        f"{focus_team} offensive corners - spatial profile",
        "Delivery routes, endpoints and first-shot locations",
        title_y=0.975,
        subtitle_y=0.935,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str]) -> int:
    # Positional CLI args: [team] [output_dir]. No argparse.
    # NOTE: exact-match team names only. Some UCL teams (PSG, Bayern,
    # Monaco, Leverkusen, Dortmund) are spelled differently in
    # matches.csv vs the StatsBomb events and will not match. Barcelona
    # is spelled consistently in both sources.
    focus_team = argv[1] if len(argv) > 1 else "Barcelona"
    output_dir = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUTPUT_DIR

    print(f"Corner spatial profile - {focus_team}")
    print("-" * 60)
    print("Collecting corner sequences from StatsBomb events ...")
    sequences = collect_corner_sequences(focus_team)

    if not sequences:
        print(f"  No corners found for '{focus_team}'. Nothing to plot.")
        return 1

    routine_counts: dict[str, int] = {label: 0 for label in ROUTINE_ORDER}
    for seq in sequences:
        routine_counts[seq["routine_type"]] = routine_counts.get(
            seq["routine_type"], 0
        ) + 1

    shots = sum(1 for s in sequences if s["first_shot_x"] is not None)
    print(f"  Corners processed          : {len(sequences)}")
    print(f"  First-shot attempts        : {shots}")
    for label in ROUTINE_ORDER:
        print(f"    {label:<18}: {routine_counts.get(label, 0):>3d}")

    output_path = output_dir / OUTPUT_NAME
    print()
    print(f"Saving plot to {output_dir}/ ...")
    plot_spatial_profile(sequences, output_path, focus_team=focus_team)
    print(f"  saved {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
