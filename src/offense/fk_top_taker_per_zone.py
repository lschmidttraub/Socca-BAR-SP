"""Barcelona offensive FKs — dominant taker per pitch third, mapped on pitch.

For each of the three pitch thirds (own / middle / opponents) identifies the
Barcelona player with the most FK takes, then plots all of their free kicks
from *that specific third* as origin→delivery arrows on a full-pitch subplot.

Thirds (StatsBomb normalised, Barcelona always attacks toward x=120):
  Own third        x  0–40
  Middle third     x 40–80
  Opponents third  x 80–120

Output: assets/offensive_freekicks/fk_top_taker_per_zone.png
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mplsoccer import Pitch


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
from stats.viz.style import apply_theme, save_fig, FOCUS_COLOR, AVG_COLOR, NEUTRAL_COLOR

ASSETS_ROOT = PROJECT_ROOT / "assets" / "offensive_freekicks"
DATA = PROJECT_ROOT / "data" / "statsbomb"
TEAM = "Barcelona"
SHORT_FK_MAX_LEN = 12.0

THIRDS = ["Own third", "Middle third", "Opponents third"]

THIRD_COLORS = {
    "Own third":        "#4575b4",
    "Middle third":     "#f28e2b",
    "Opponents third":  FOCUS_COLOR,
}

THIRD_X_RANGE = {
    "Own third":        (0, 40),
    "Middle third":     (40, 80),
    "Opponents third":  (80, 120),
}

ROUTINE_COLORS = {
    "Direct shot":     "#d62728",
    "Short FK":        "#ff7f0e",
    "Cross into box":  "#1f77b4",
    "Other indirect":  "#878787",
}

OUTCOME_COLORS = {
    "Goal":   "#2ca02c",
    "Saved":  "#ff7f0e",
    "Other":  "#878787",
}


# ── helpers ──────────────────────────────────────────────────────────


def _pitch_third(x: float) -> str:
    if x < 40:
        return "Own third"
    if x < 80:
        return "Middle third"
    return "Opponents third"


def _fk_routine(event: dict) -> str:
    if f.is_fk_shot(event):
        return "Direct shot"
    length = float(event.get("pass", {}).get("length", 0.0) or 0.0)
    if length <= SHORT_FK_MAX_LEN:
        return "Short FK"
    end = event.get("pass", {}).get("end_location")
    if end and end[0] >= 102 and 18 <= end[1] <= 62:
        return "Cross into box"
    return "Other indirect"


def _pass_end(event: dict) -> tuple[float, float] | None:
    if f.is_fk_pass(event):
        end = event.get("pass", {}).get("end_location")
    elif f.is_fk_shot(event):
        end = event.get("shot", {}).get("end_location")
        if end and len(end) >= 2:
            return float(end[0]), float(end[1])
        return None
    else:
        return None
    if end and len(end) >= 2:
        return float(end[0]), float(end[1])
    return None


def _shot_outcome(event: dict) -> str:
    if f.is_goal(event):
        return "Goal"
    outcome = event.get("shot", {}).get("outcome", {}).get("name", "")
    return "Saved" if "Saved" in outcome else "Other"


# ── data collection ──────────────────────────────────────────────────


def _collect(data_dir: Path) -> list[dict]:
    """Return one dict per Barcelona FK event with location and delivery info."""
    records: list[dict] = []
    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(TEAM, row, events)
        if sb_name is None:
            continue
        for event in events:
            if not (f.is_fk_pass(event) or f.is_fk_shot(event)):
                continue
            if not f.by_team(event, sb_name):
                continue
            loc = event.get("location")
            if not loc or len(loc) < 2:
                continue
            x, y = float(loc[0]), float(loc[1])
            end = _pass_end(event)
            routine = _fk_routine(event)
            outcome = _shot_outcome(event) if f.is_fk_shot(event) else None
            records.append({
                "taker":   f.event_player(event) or "Unknown",
                "third":   _pitch_third(x),
                "x":       x,
                "y":       y,
                "end_x":   end[0] if end else None,
                "end_y":   end[1] if end else None,
                "routine": routine,
                "outcome": outcome,
                "is_shot": f.is_fk_shot(event),
                "is_goal": f.is_goal(event),
            })
    return records


# ── plotting ─────────────────────────────────────────────────────────


def _draw_third_band(ax: plt.Axes, third: str) -> None:
    """Shade the relevant pitch third as a subtle background band."""
    x0, x1 = THIRD_X_RANGE[third]
    color = THIRD_COLORS[third]
    ax.axvspan(x0, x1, alpha=0.06, color=color, zorder=0)
    ax.axvline(x0, color=color, lw=0.8, ls="--", alpha=0.4, zorder=1)
    ax.axvline(x1, color=color, lw=0.8, ls="--", alpha=0.4, zorder=1)


def _plot(records: list[dict], output_path: Path) -> None:
    # Build per-third taker counters and identify top taker per third
    by_third: dict[str, list[dict]] = {t: [] for t in THIRDS}
    for r in records:
        if r["taker"] != "Unknown":
            by_third[r["third"]].append(r)

    top_takers: dict[str, tuple[str, int]] = {}
    for third in THIRDS:
        counter = Counter(r["taker"] for r in by_third[third])
        if counter:
            name, count = counter.most_common(1)[0]
            top_takers[third] = (name, count)

    pitch = Pitch(
        pitch_type="statsbomb", half=False,
        pitch_color="white", line_color="#c7d5cc", linewidth=1.5,
    )
    fig, axes = plt.subplots(1, 3, figsize=(22, 7.2))
    fig.subplots_adjust(top=0.78, bottom=0.12, wspace=0.06)

    for ax, third in zip(axes, THIRDS):
        pitch.draw(ax=ax)
        ax.set_xticks([])
        ax.set_yticks([])
        _draw_third_band(ax, third)

        if third not in top_takers:
            ax.set_title(f"{third}\n(no data)", fontsize=11)
            continue

        player, count = top_takers[third]
        player_fks = [r for r in by_third[third] if r["taker"] == player]

        # Group by routine for arrow color
        for r in player_fks:
            x0, y0 = r["x"], r["y"]
            x1, y1 = r.get("end_x"), r.get("end_y")

            # Draw start marker
            color = ROUTINE_COLORS[r["routine"]]
            ax.scatter([x0], [y0], s=55, color=color, edgecolors="white",
                       linewidth=0.7, zorder=5, alpha=0.9)

            # Draw arrow if end location available
            if x1 is not None and y1 is not None:
                dx, dy = x1 - x0, y1 - y0
                length = float(np.hypot(dx, dy))
                if length > 0.5:
                    ax.annotate(
                        "",
                        xy=(x1, y1), xytext=(x0, y0),
                        arrowprops={
                            "arrowstyle": "-|>",
                            "color": color,
                            "lw": 1.4,
                            "alpha": 0.72,
                            "mutation_scale": 9,
                        },
                        zorder=4,
                    )

            # Extra star for goals
            if r["is_goal"] and x1 is not None and y1 is not None:
                ax.scatter([x1], [y1], s=160, marker="*",
                           color="#ffd166", edgecolors="#7a4c00",
                           linewidth=0.9, zorder=7)

        # Short name for title (last two tokens to handle compound surnames)
        short = " ".join(player.split()[-2:]) if len(player.split()) > 2 else player
        total_in_third = len(by_third[third])
        ax.set_title(
            f"{third}\n{short}  ({count} of {total_in_third} FKs)",
            fontsize=11, fontweight="bold", pad=10, color=THIRD_COLORS[third],
        )

    # Title + subtitle
    fig.suptitle(
        "Barcelona offensive free kicks — dominant taker per pitch third",
        fontsize=16, fontweight="bold", y=0.995,
    )
    fig.text(
        0.5, 0.925,
        "Top FK taker in each zone  |  arrows show origin → delivery  "
        "|  colour = routine type  |  star = goal",
        ha="center", fontsize=10, color="#333333",
    )

    # Routine legend
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
               markeredgecolor="white", markersize=8, lw=0, label=label)
        for label, c in ROUTINE_COLORS.items()
    ] + [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#ffd166",
               markeredgecolor="#7a4c00", markersize=11, lw=0, label="Goal"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=5,
               fontsize=9, frameon=True, fancybox=True, framealpha=0.9,
               bbox_to_anchor=(0.5, 0.01))

    save_fig(fig, output_path, tight=False)
    print(f"Saved: {output_path}")


# ── entry point ──────────────────────────────────────────────────────


def run(data_dir: Path = DATA, output_dir: Path = ASSETS_ROOT) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting Barcelona FK events ...")
    records = _collect(data_dir)
    print(f"  {len(records)} total FK events")
    for third in THIRDS:
        n = sum(1 for r in records if r["third"] == third)
        counter = Counter(r["taker"] for r in records if r["third"] == third and r["taker"] != "Unknown")
        top = counter.most_common(1)
        leader = f"{top[0][0]} ({top[0][1]})" if top else "—"
        print(f"    {third}: {n} FKs  |  top taker: {leader}")

    out = output_dir / "fk_top_taker_per_zone.png"
    _plot(records, out)
    print("Done.")


if __name__ == "__main__":
    run()
