"""Barcelona offensive corner run-path analysis from SkillCorner tracking.

Generates per-corner three-panel figures (start positions → movement
paths → end positions) for every Barcelona attacking corner that has
SkillCorner tracking data.  Each figure captures a ±2.5 s window around
the corner kick and shows the movement of Barcelona's outfield attackers
in the opponent half.

Uses ``_loader.py`` for data access (StatsBomb event ZIPs + SkillCorner
tracking ZIPs) and track processing.  All paths are CWD-relative: run
from the project root (the directory that contains ``data/``).

Usage
-----

    python corner_runs.py [team] [output_dir]

Both arguments are optional.  ``team`` defaults to ``Barcelona``;
``output_dir`` defaults to ``corner_run_maps/`` in the current working
directory.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mplsoccer import Pitch

from _loader import (
    DEFAULT_TEAM,
    FOCUS_COLOR,
    NEUTRAL_COLOR,
    POST_SECONDS,
    PRE_SECONDS,
    CornerWindow,
    PlayerInfo,
    attempt_player_ids,
    collect_corner_windows,
    format_match_clock,
    player_paths_for_window,
    side_label,
    side_slug,
)

DEFAULT_OUTPUT_DIR = Path("corner_run_maps")


# ── Style ────────────────────────────────────────────────────────────


def _apply_theme() -> None:
    mpl.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": NEUTRAL_COLOR,
        "axes.grid": True,
        "grid.color": "#e0e0e0",
        "grid.linewidth": 0.5,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "xtick.color": NEUTRAL_COLOR,
        "ytick.color": NEUTRAL_COLOR,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "figure.dpi": 150,
    })


def _save_fig(fig: plt.Figure, path: Path, *, tight: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if tight:
        fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


# ── Plotting ─────────────────────────────────────────────────────────


def _corner_marker(ax: plt.Axes, side: str) -> None:
    y = 79.2 if side == "top" else 0.8
    ax.scatter(
        [119.5], [y], s=240, marker=">",
        color="#ffcc00", edgecolors="#444444", linewidth=0.8, zorder=6,
    )


def _apply_header(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.995)
    fig.text(0.5, 0.926, subtitle, ha="center", fontsize=10.4, color="#333333")


def _draw_corner_panel(
    ax: plt.Axes,
    pitch: Pitch,
    window: CornerWindow,
    players: dict[int, PlayerInfo],
    *,
    variant: str,
) -> None:
    """Draw one panel of the three-panel corner figure."""
    pitch.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])

    paths = player_paths_for_window(window, players)
    attempt_ids = attempt_player_ids(window, players)

    for path in paths:
        arr = path["path"]
        mask = ~np.isnan(arr[:, 0]) & ~np.isnan(arr[:, 1])
        if mask.sum() < 2:
            continue
        xs = arr[mask, 0]
        ys = arr[mask, 1]
        color = "#2ca02c" if window.result == "Goal" else FOCUS_COLOR
        is_attempt_player = path["player_id"] in attempt_ids

        if variant == "paths":
            pitch.lines(
                xs[:-1], ys[:-1], xs[1:], ys[1:], ax=ax,
                color=color, comet=False, transparent=True,
                alpha_start=0.28, alpha_end=0.9, lw=2.3, zorder=2,
            )
            ax.annotate(
                "",
                xy=(xs[-1], ys[-1]),
                xytext=(xs[-2], ys[-2]),
                arrowprops={
                    "arrowstyle": "-|>", "color": color,
                    "lw": 2.0, "alpha": 0.95,
                },
                zorder=5,
            )

        if variant in {"starts", "paths"}:
            ax.scatter(
                [xs[0]], [ys[0]], s=54, color="white",
                edgecolors=color, linewidth=1.25, zorder=4,
            )

        if variant == "ends":
            ax.scatter(
                [xs[-1]], [ys[-1]], s=46, color=color,
                edgecolors="white", linewidth=0.8, zorder=5,
            )

        if is_attempt_player and variant in {"starts", "paths", "ends"}:
            attempt_x, attempt_y = (
                (xs[-1], ys[-1]) if variant != "starts" else (xs[0], ys[0])
            )
            ax.scatter(
                [attempt_x], [attempt_y], s=180, marker="*",
                color="#ffd166", edgecolors="#7a4c00", linewidth=0.9, zorder=7,
            )

    _corner_marker(ax, window.side)
    ax.set_title(
        {
            "starts": f"01 Starts  |  t-{PRE_SECONDS:.1f}s",
            "paths": f"02 Paths  |  t-{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s",
            "ends": f"03 Ends  |  t+{POST_SECONDS:.1f}s",
        }[variant],
        fontsize=11.5, fontweight="bold", pad=10,
    )


def _plot_corner_three_panel(
    window: CornerWindow,
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    """Create one three-panel figure for a single corner."""
    pitch = Pitch(
        pitch_type="statsbomb", half=True,
        pitch_color="white", line_color="#c7d5cc", linewidth=1.6,
    )
    fig, axes = plt.subplots(1, 3, figsize=(18.5, 7.2))
    fig.subplots_adjust(top=0.76, bottom=0.13, wspace=0.08)

    for ax, variant in zip(axes, ("starts", "paths", "ends")):
        _draw_corner_panel(ax, pitch, window, players, variant=variant)

    paths = player_paths_for_window(window, players)
    _apply_header(
        fig,
        "Barcelona attacking corner run map",
        (
            f"{window.opponent}  |  corner {window.corner_index}  |  "
            f"{side_label(window.side)}  |  "
            f"{format_match_clock(window.corner_time)}  |  {window.result}  |  "
            f"{len(paths)} tracked attackers  |  "
            f"window: t-{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s"
        ),
    )

    handles = [
        Line2D(
            [0], [0], marker="o", color="white",
            markeredgecolor=FOCUS_COLOR, markeredgewidth=1.2,
            markersize=7, lw=0, label=f"Start (t-{PRE_SECONDS:.1f}s)",
        ),
        Line2D([0], [0], color=FOCUS_COLOR, lw=2.5, label="Attacker run"),
        Line2D(
            [0], [0], marker="o", color=FOCUS_COLOR,
            markeredgecolor="white", markeredgewidth=0.8,
            markersize=7, lw=0, label="End point",
        ),
    ]
    if window.shot_generated:
        handles.append(Line2D(
            [0], [0], marker="*", color="#ffd166",
            markeredgecolor="#7a4c00", markeredgewidth=0.9,
            markersize=10, lw=0, label="Attempt player",
        ))
    handles.append(Line2D(
        [0], [0], marker=">", color="w",
        markerfacecolor="#ffcc00", markeredgecolor="#444444",
        markersize=9, lw=0, label="Corner kick",
    ))
    fig.legend(
        handles=handles, loc="lower center",
        ncol=min(len(handles), 5), fontsize=9,
        frameon=True, fancybox=True, framealpha=0.92,
    )
    _save_fig(fig, output_path, tight=False)


# ── CSV summary ──────────────────────────────────────────────────────


def _write_run_table(
    windows: list[CornerWindow],
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    fieldnames = [
        "skillcorner_match_id", "statsbomb_match_id", "opponent",
        "corner_index", "corner_time_sec", "corner_side", "result",
        "player_id", "player_name", "role",
        "start_x", "start_y", "end_x", "end_y", "delta_x", "delta_y",
    ]
    rows: list[dict[str, Any]] = []
    for window in windows:
        for path in player_paths_for_window(window, players):
            start_x, start_y = path["start"]
            end_x, end_y = path["end"]
            rows.append({
                "skillcorner_match_id": window.skillcorner_match_id,
                "statsbomb_match_id": window.statsbomb_match_id,
                "opponent": window.opponent,
                "corner_index": window.corner_index,
                "corner_time_sec": round(window.corner_time, 2),
                "corner_side": window.side,
                "result": window.result,
                "player_id": path["player_id"],
                "player_name": path["name"],
                "role": path["role"],
                "start_x": round(start_x, 2),
                "start_y": round(start_y, 2),
                "end_x": round(end_x, 2),
                "end_y": round(end_y, 2),
                "delta_x": round(end_x - start_x, 2),
                "delta_y": round(end_y - start_y, 2),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Entry point ──────────────────────────────────────────────────────


def main(focus_team: str, output_dir: Path) -> None:
    _apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Collecting {focus_team} corner tracking windows from SkillCorner...")
    windows, players = collect_corner_windows(focus_team)
    if not windows:
        print(f"No {focus_team} corners with SkillCorner tracking found.")
        return

    side_counts = Counter(w.side for w in windows)
    shot_count = sum(1 for w in windows if w.shot_generated)
    goal_count = sum(1 for w in windows if w.result == "Goal")
    print(f"  Tracked corners : {len(windows)}")
    print(f"    top (right)   : {side_counts.get('top', 0)}")
    print(f"    bottom (left) : {side_counts.get('bottom', 0)}")
    print(f"    Shots         : {shot_count}")
    print(f"    Goals         : {goal_count}")

    # Individual corner maps
    maps_dir = output_dir / "corner_run_maps"
    maps_dir.mkdir(parents=True, exist_ok=True)

    for window in windows:
        clock = format_match_clock(window.corner_time).replace(":", "")
        base = (
            f"corner_{window.skillcorner_match_id}_{window.corner_index:02d}_"
            f"{side_slug(window.side)}_{clock}_{window.result.lower().replace(' ', '_')}"
        )
        _plot_corner_three_panel(window, players, maps_dir / f"{base}.png")

    # Summary CSV
    csv_path = output_dir / "corner_run_summary.csv"
    _write_run_table(windows, players, csv_path)

    print(f"\nOutputs saved to {output_dir}/")
    print(f"  {len(windows)} corner maps  → {maps_dir}/")
    print(f"  summary CSV     → {csv_path}")


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    main(team, out)
