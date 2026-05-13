"""Goal-face location map for penalties conceded by Barcelona.

Figure — Penalties faced:
  Left:  Opponent penalty shot locations against Barcelona (circle=Goal, X=Saved/missed)
  Right: All CL teams — KDE density heatmap of penalty shot locations (reference)

Output:
  assets/defense/penalties/def_penalty_goal_map.png

Coordinate note
---------------
StatsBomb shot end_location[1] = y across the goal width (36–44 yds),
end_location[2] = height (0–2.67 yds).  These coordinates are the same
regardless of which team is shooting, so no reflection is needed.

Usage
-----
    python src/defense/penalties/def_penalty_goal_map.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
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
from stats.viz.style import FOCUS_COLOR, AVG_COLOR, NEUTRAL_COLOR, POSITIVE_COLOR, apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "penalties"
_SB_ROOT   = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS  = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
DATA       = _SB_ROOT
TEAM = "Barcelona"

# Goal dimensions (StatsBomb shot end_location coordinates)
GOAL_Y_MIN = 36.0
GOAL_Y_MAX = 44.0
GOAL_HEIGHT = 2.67
GOAL_CENTRE = (GOAL_Y_MIN + GOAL_Y_MAX) / 2  # = 40.0

GOAL_COLOR   = "#c0392b"   # red   — goal conceded
SAVED_COLOR  = "#27ae60"   # green — saved by Barcelona GK
MISSED_COLOR = NEUTRAL_COLOR  # gray  — off target / blocked


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
    end = event["shot"]["end_location"]
    y, z = float(end[1]), float(end[2])
    return GOAL_Y_MIN <= y <= GOAL_Y_MAX and 0.0 <= z <= GOAL_HEIGHT


def _collect(data_dir: Path = DATA) -> tuple[list[dict], list[dict]]:
    """Return (barcelona_faced_3d, all_on_frame)."""
    barca_faced: list[dict] = []
    all_on_frame: list[dict] = []

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            sb_name = _team_in_match(TEAM, row, events)

            for e in events:
                if not f.is_penalty_shot(e) or not _has_3d_end(e):
                    continue
                if _on_goal_frame(e):
                    all_on_frame.append(e)
                if sb_name and not f.by_team(e, sb_name):
                    barca_faced.append(e)

    return barca_faced, all_on_frame


# ── per-team penalty concession stats ────────────────────────────────

def _collect_per_team(data_dir: Path = DATA) -> dict[str, dict]:
    """Return per-team {matches, goals_conceded, saved, other} across all CL matches."""
    records: dict[str, dict] = defaultdict(lambda: {
        "matches": 0,
        "goals_conceded": 0,
        "saved": 0,
        "other": 0,
    })

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            home_csv = row.get("home", "").strip()
            away_csv = row.get("away", "").strip()
            if not home_csv or not away_csv:
                continue

            home_ev = _team_in_match(home_csv, row, events) or home_csv
            away_ev = _team_in_match(away_csv, row, events) or away_csv

            records[home_csv]["matches"] += 1
            records[away_csv]["matches"] += 1

            for e in events:
                if not f.is_penalty_shot(e):
                    continue
                shooter_ev = f.event_team(e)
                outcome = _outcome(e)
                key = "goals_conceded" if outcome == "Goal" else ("saved" if outcome == "Saved" else "other")

                if shooter_ev == home_ev:
                    records[away_csv][key] += 1
                elif shooter_ev == away_ev:
                    records[home_csv][key] += 1

    return dict(records)


def plot_penalties_per_game(
    per_team: dict[str, dict],
    output_dir: Path,
) -> Path:
    """Stacked bar chart of penalties conceded per game, split by outcome.

    Barcelona bars are red shades; all other teams are blue shades.
    Dark = goals conceded, light = saved / off target.
    """
    from matplotlib.patches import Patch

    rows = sorted(
        [(team, d) for team, d in per_team.items()],
        key=lambda x: (x[1]["goals_conceded"] + x[1]["saved"] + x[1]["other"]) / max(x[1]["matches"], 1),
        reverse=True,
    )
    teams = [r[0] for r in rows]
    n = len(teams)

    # Color scheme: Barcelona = red family, others = blue family
    # Darker shade = goals conceded, lighter = saved/missed
    BARCA_GOAL  = "#c0392b"
    BARCA_REST  = "#f1948a"
    OTHER_GOAL  = "#1a5276"
    OTHER_REST  = "#85c1e9"

    fig, ax = plt.subplots(figsize=(14, 6))

    for i, (team, d) in enumerate(rows):
        m = max(d["matches"], 1)
        g = d["goals_conceded"] / m
        s = d["saved"] / m
        o = d["other"] / m
        total = g + s + o

        is_barca = (team == TEAM)
        c_goal = BARCA_GOAL if is_barca else OTHER_GOAL
        c_rest = BARCA_REST if is_barca else OTHER_REST

        ax.bar(i, g,       color=c_goal, edgecolor="white", linewidth=0.4)
        ax.bar(i, s + o,   bottom=g, color=c_rest, edgecolor="white", linewidth=0.4)

        if total > 0:
            ax.text(i, total + 0.003, f"{total:.2f}",
                    ha="center", va="bottom", fontsize=7.5, color="#333333")

    ax.set_xticks(range(n))
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Penalties conceded / game", fontsize=11)
    ax.set_title("Penalties conceded per game — all CL teams", fontsize=14, fontweight="bold")

    legend_handles = [
        Patch(facecolor=BARCA_GOAL,  label="Barcelona — goals conceded"),
        Patch(facecolor=BARCA_REST,  label="Barcelona — saved / missed"),
        Patch(facecolor=OTHER_GOAL,  label="Other teams — goals conceded"),
        Patch(facecolor=OTHER_REST,  label="Other teams — saved / missed"),
    ]
    ax.legend(handles=legend_handles, fontsize=8.5, ncol=2, loc="upper right")

    fig.tight_layout()

    out_path = output_dir / "def_penalties_per_game.png"
    plt.show()
    save_fig(fig, out_path, tight=False)
    print(f"  Saved: {out_path.relative_to(output_dir.parent.parent.parent)}")
    return out_path


# ── goal frame ────────────────────────────────────────────────────────

def _draw_goal_frame(ax: plt.Axes) -> None:
    ax.fill_between([GOAL_Y_MIN, GOAL_Y_MAX], 0, GOAL_HEIGHT,
                    color="#ececec", zorder=0)
    ax.fill_between([GOAL_Y_MIN - 1.2, GOAL_Y_MAX + 1.2], -0.40, 0,
                    color="#9ecf82", zorder=0, alpha=0.8)
    for frac in (1/3, 2/3):
        xv = GOAL_Y_MIN + frac * (GOAL_Y_MAX - GOAL_Y_MIN)
        ax.plot([xv, xv], [0, GOAL_HEIGHT], color="#cccccc",
                lw=0.6, ls="--", zorder=1)
    ax.plot([GOAL_Y_MIN, GOAL_Y_MAX], [GOAL_HEIGHT / 2, GOAL_HEIGHT / 2],
            color="#cccccc", lw=0.6, ls="--", zorder=1)
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
    barca_faced: list[dict],
    all_shots: list[dict],
) -> plt.Figure:
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(14, 5.2))
    fig.subplots_adjust(top=0.80, bottom=0.18, wspace=0.34)

    # — Left: scatter of opponent penalties against Barcelona —
    _draw_goal_frame(ax_l)
    _scatter_shots(ax_l, barca_faced)

    n_g = sum(1 for e in barca_faced if _outcome(e) == "Goal")
    n_s = sum(1 for e in barca_faced if _outcome(e) == "Saved")
    n_o = len(barca_faced) - n_g - n_s
    ax_l.set_title(
        f"Barcelona (conceded)  ·  n={len(barca_faced)}  ({n_g} goal / {n_s} saved / {n_o} other)",
        fontsize=11, fontweight="bold", pad=8,
    )

    outcome_legend = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=GOAL_COLOR,
               markersize=9, label="Goal conceded"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=SAVED_COLOR,
               markeredgecolor=SAVED_COLOR, markersize=9, label="Saved by GK"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=MISSED_COLOR,
               markeredgecolor=MISSED_COLOR, markersize=9, label="Off target / blocked"),
    ]
    ax_l.legend(handles=outcome_legend, loc="lower center",
                bbox_to_anchor=(0.5, -0.32), ncol=3, fontsize=8.5,
                frameon=True, framealpha=0.85)

    # — Right: all-team KDE reference heatmap —
    _draw_goal_frame(ax_r)
    _heatmap_shots(ax_r, all_shots)
    ax_r.plot(
        [GOAL_Y_MIN, GOAL_Y_MIN, GOAL_Y_MAX, GOAL_Y_MAX],
        [0, GOAL_HEIGHT, GOAL_HEIGHT, 0],
        color="#222222", lw=3.5, zorder=5, solid_capstyle="round",
    )
    ax_r.set_title(
        f"All CL teams — density  (n={len(all_shots)} shots on frame)",
        fontsize=11, fontweight="bold", pad=8,
    )

    fig.text(0.5, 0.96, "Penalties conceded — goal-face locations",
             ha="center", va="top", fontsize=15, fontweight="bold", color="#111111")
    fig.text(
        0.5, 0.91,
        "Left: opponent penalties against Barcelona  ·  circle = goal conceded, X = saved/off target  "
        "·  Right: all CL teams, kernel-density heatmap (on-target shots only)",
        ha="center", va="top", fontsize=9.5, color="#444444",
    )
    return fig


# ── entry point ───────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_DIR) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting opponent penalty data ...")
    barca_faced, all_pen = _collect(data_dir)
    print(f"  Penalties faced by Barcelona: {len(barca_faced)}")
    print(f"    Goals conceded: {sum(1 for e in barca_faced if _outcome(e) == 'Goal')}")
    print(f"    Saved by GK:    {sum(1 for e in barca_faced if _outcome(e) == 'Saved')}")
    print(f"  All CL on-frame:  {len(all_pen)}")

    print("Building goal-face figure ...")
    fig = _build_figure(barca_faced, all_pen)
    plt.show()
    save_fig(fig, output_dir / "def_penalty_goal_map.png", tight=False)
    print("  Saved: assets/defense/penalties/def_penalty_goal_map.png")

    print("Collecting per-team penalty concession data ...")
    per_team = _collect_per_team(data_dir)
    for team, d in sorted(per_team.items()):
        total = d["goals_conceded"] + d["saved"] + d["other"]
        rate = total / d["matches"] if d["matches"] else 0.0
        print(f"  {team}: {total} ({d['goals_conceded']}G/{d['saved']}S/{d['other']}O) in {d['matches']} games ({rate:.3f}/game)")

    print("Building penalties-per-game chart ...")
    plot_penalties_per_game(per_team, output_dir)

    print("\nDone.")


if __name__ == "__main__":
    run()
