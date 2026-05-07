"""Goal-face location maps for penalties and direct free kicks.

Figure 1 — Penalties:
  Left:  Barcelona penalty shot locations (circle=Goal, X=Saved/missed)
  Right: All CL teams — KDE density heatmap of penalty locations

Figure 2 — Direct free kicks:
  Left:  Barcelona direct FK shot locations on goal (circle=Goal, X=Saved)
  Right: All CL teams — KDE density heatmap of direct FK on-goal locations

Outputs:
  assets/penalty_goal_map.png
  assets/freekick_goal_map.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D

def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import NEUTRAL_COLOR, POSITIVE_COLOR, apply_theme, save_fig

ASSETS_ROOT = PROJECT_ROOT / "assets"
DATA = PROJECT_ROOT / "data" / "statsbomb"
TEAM = "Barcelona"

# Goal dimensions (StatsBomb shot end_location coordinates)
GOAL_Y_MIN = 36.0   # left post (yards)
GOAL_Y_MAX = 44.0   # right post (yards)
GOAL_HEIGHT = 2.67  # crossbar height (yards ≈ 8 ft)
GOAL_CENTRE = (GOAL_Y_MIN + GOAL_Y_MAX) / 2  # = 40.0

GOAL_COLOR = POSITIVE_COLOR   # green — goal
SAVED_COLOR = "#e6821e"        # orange — saved
MISSED_COLOR = NEUTRAL_COLOR   # gray — off target / blocked


# ── data ─────────────────────────────────────────────────────────────

def _outcome(event: dict) -> str:
    if f.is_goal(event):
        return "Goal"
    if "Saved" in f.shot_outcome(event):
        return "Saved"
    return "Other"


def _has_3d_end(event: dict) -> bool:
    end = event.get("shot", {}).get("end_location")
    return bool(end and len(end) >= 3)


def _on_goal_frame(event: dict) -> bool:
    """True when the shot endpoint lands inside the goal rectangle."""
    end = event["shot"]["end_location"]
    y, z = float(end[1]), float(end[2])
    return GOAL_Y_MIN <= y <= GOAL_Y_MAX and 0.0 <= z <= GOAL_HEIGHT


def _collect(data_dir: Path, predicate) -> tuple[list[dict], list[dict]]:
    """Return (barcelona_shots_3d, all_on_frame_shots).

    barcelona_shots_3d: every Barca shot that has a 3D end_location
        (used for the scatter; off-target shots appear outside the frame).
    all_on_frame_shots: CL shots where the endpoint is INSIDE the goal
        rectangle — goals + saves on frame — used for the KDE heatmap.
    """
    barca: list[dict] = []
    all_on_frame: list[dict] = []

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(TEAM, row, events)

        for e in events:
            if not predicate(e) or not _has_3d_end(e):
                continue
            if _on_goal_frame(e):
                all_on_frame.append(e)
            if sb_name and f.by_team(e, sb_name):
                barca.append(e)

    return barca, all_on_frame


# ── goal frame ────────────────────────────────────────────────────────

def _draw_goal_frame(ax: plt.Axes) -> None:
    # Net fill
    ax.fill_between([GOAL_Y_MIN, GOAL_Y_MAX], 0, GOAL_HEIGHT,
                    color="#ececec", zorder=0)
    # Grass strip below goal line
    ax.fill_between([GOAL_Y_MIN - 1.2, GOAL_Y_MAX + 1.2], -0.40, 0,
                    color="#9ecf82", zorder=0, alpha=0.8)
    # Dashed thirds gridlines
    for frac in (1/3, 2/3):
        xv = GOAL_Y_MIN + frac * (GOAL_Y_MAX - GOAL_Y_MIN)
        ax.plot([xv, xv], [0, GOAL_HEIGHT], color="#cccccc",
                lw=0.6, ls="--", zorder=1)
    # Dashed mid-height gridline
    ax.plot([GOAL_Y_MIN, GOAL_Y_MAX], [GOAL_HEIGHT / 2, GOAL_HEIGHT / 2],
            color="#cccccc", lw=0.6, ls="--", zorder=1)
    # Posts and crossbar
    ax.plot(
        [GOAL_Y_MIN, GOAL_Y_MIN, GOAL_Y_MAX, GOAL_Y_MAX],
        [0, GOAL_HEIGHT, GOAL_HEIGHT, 0],
        color="#222222", lw=3.5, zorder=3, solid_capstyle="round",
    )

    ax.set_xlim(GOAL_Y_MIN - 1.2, GOAL_Y_MAX + 1.2)
    ax.set_ylim(-0.40, GOAL_HEIGHT + 0.55)
    ax.set_aspect("equal")
    ax.set_xlabel("Goal width", fontsize=9)
    ax.set_ylabel("Height (yds)", fontsize=9)
    ax.tick_params(labelsize=8)

    # Label posts and centre on x-axis
    ax.set_xticks([GOAL_Y_MIN, GOAL_CENTRE, GOAL_Y_MAX])
    ax.set_xticklabels(["L post", "Centre", "R post"], fontsize=8)
    ax.set_yticks([0, GOAL_HEIGHT / 2, GOAL_HEIGHT])
    ax.set_yticklabels(["0", f"{GOAL_HEIGHT/2:.1f}", f"{GOAL_HEIGHT:.2f}"], fontsize=8)


# ── scatter ───────────────────────────────────────────────────────────

def _scatter_shots(ax: plt.Axes, events: list[dict]) -> None:
    for e in events:
        end = e.get("shot", {}).get("end_location")
        if not end or len(end) < 3:
            continue
        y, z = float(end[1]), float(end[2])
        outcome = _outcome(e)
        color  = GOAL_COLOR if outcome == "Goal" else (SAVED_COLOR if outcome == "Saved" else MISSED_COLOR)
        marker = "o" if outcome == "Goal" else "X"
        size   = 160 if outcome == "Goal" else 120

        ax.scatter(y, z, s=size, marker=marker, color=color,
                   edgecolors="white" if outcome == "Goal" else color,
                   linewidth=0.9, zorder=4, alpha=0.93)


# ── KDE heatmap ───────────────────────────────────────────────────────

def _heatmap_shots(ax: plt.Axes, events: list[dict]) -> None:
    ys = [float(e["shot"]["end_location"][1]) for e in events]
    zs = [float(e["shot"]["end_location"][2]) for e in events]

    if len(ys) < 3:
        ax.text(GOAL_CENTRE, GOAL_HEIGHT / 2, "Too few data points",
                ha="center", va="center", fontsize=9, color="#777777")
        return

    # Clip KDE to goal rectangle
    sns.kdeplot(
        x=ys, y=zs, ax=ax,
        fill=True, cmap="Reds", levels=14, alpha=0.88,
        bw_adjust=0.55,
        clip=((GOAL_Y_MIN, GOAL_Y_MAX), (0.0, GOAL_HEIGHT)),
        zorder=1,
    )
    sns.kdeplot(
        x=ys, y=zs, ax=ax,
        fill=False, color="white", levels=6, linewidths=0.5,
        alpha=0.5, bw_adjust=0.55,
        clip=((GOAL_Y_MIN, GOAL_Y_MAX), (0.0, GOAL_HEIGHT)),
        zorder=2,
    )


# ── figure builder ────────────────────────────────────────────────────

def _build_figure(
    barca: list[dict],
    all_shots: list[dict],
    title: str,
    subtitle: str,
) -> plt.Figure:
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(14, 5.2))
    fig.subplots_adjust(top=0.80, bottom=0.18, wspace=0.34)

    # — Left: Barcelona scatter —
    _draw_goal_frame(ax_l)
    _scatter_shots(ax_l, barca)

    n_g = sum(1 for e in barca if _outcome(e) == "Goal")
    n_s = sum(1 for e in barca if _outcome(e) == "Saved")
    n_o = len(barca) - n_g - n_s
    ax_l.set_title(
        f"Barcelona  ·  n={len(barca)}  ({n_g} goal / {n_s} saved / {n_o} other)",
        fontsize=11, fontweight="bold", pad=8,
    )

    outcome_legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=GOAL_COLOR,
               markersize=9, label="Goal"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=SAVED_COLOR,
               markeredgecolor=SAVED_COLOR, markersize=9, label="Saved"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=MISSED_COLOR,
               markeredgecolor=MISSED_COLOR, markersize=9, label="Off target / blocked"),
    ]
    ax_l.legend(handles=outcome_legend, loc="lower center",
                bbox_to_anchor=(0.5, -0.32), ncol=3, fontsize=8.5,
                frameon=True, framealpha=0.85)

    # — Right: all-team KDE heatmap —
    _draw_goal_frame(ax_r)
    _heatmap_shots(ax_r, all_shots)
    # Re-draw goal frame on top of the KDE fill
    ax_r.plot(
        [GOAL_Y_MIN, GOAL_Y_MIN, GOAL_Y_MAX, GOAL_Y_MAX],
        [0, GOAL_HEIGHT, GOAL_HEIGHT, 0],
        color="#222222", lw=3.5, zorder=5, solid_capstyle="round",
    )
    ax_r.set_title(
        f"All CL teams — density  (n={len(all_shots)} shots on frame)",
        fontsize=11, fontweight="bold", pad=8,
    )

    fig.text(0.5, 0.96, title, ha="center", va="top",
             fontsize=15, fontweight="bold", color="#111111")
    fig.text(0.5, 0.91, subtitle, ha="center", va="top",
             fontsize=9.5, color="#444444")
    return fig


# ── entry point ───────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_ROOT) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting penalty data ...")
    barca_pen, all_pen = _collect(data_dir, f.is_penalty_shot)
    print(f"  Barcelona: {len(barca_pen)}   All CL: {len(all_pen)}")

    print("Collecting direct free-kick data ...")
    barca_fk, all_fk = _collect(data_dir, f.is_fk_shot)
    print(f"  Barcelona: {len(barca_fk)}   All CL: {len(all_fk)}")

    print("Building penalty figure ...")
    fig1 = _build_figure(
        barca_pen, all_pen,
        title="Penalties — goal-face locations",
        subtitle=(
            "Left: Barcelona  ·  circle = goal, X = saved/off target  "
            "·  Right: all CL teams, kernel-density heatmap (on-target shots only)"
        ),
    )
    save_fig(fig1, output_dir / "penalty_goal_map.png", tight=False)
    print("  Saved: assets/penalty_goal_map.png")

    print("Building direct free-kick figure ...")
    fig2 = _build_figure(
        barca_fk, all_fk,
        title="Direct free kicks -- goal-face locations",
        subtitle=(
            "Left: Barcelona  -  circle = goal, X = saved/off target  "
            "-  Right: all CL teams, kernel-density heatmap (on-target shots only)"
        ),
    )
    save_fig(fig2, output_dir / "freekick_goal_map.png", tight=False)
    print("  Saved: assets/freekick_goal_map.png")

    print("\nDone.")


if __name__ == "__main__":
    run()
