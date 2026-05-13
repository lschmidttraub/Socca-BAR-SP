"""
throw_in_success_probability.py

Plot Barcelona throw-ins across all available StatsBomb matches, coloured by
StatsBomb's ``pass_success_probability`` and normalised so Barcelona always
attacks from left to right.

Unlike the earlier side-change script, this normalisation flips only ``x``.
That keeps the touchline side in ``y`` unchanged while still aligning the
attacking direction.

Usage:
    python src/throw_in_success_probability.py
"""

from __future__ import annotations

import io
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib import patches

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.stats import filters as f
from src.stats.analyses.setpiece_maps import _team_in_match
from src.stats.data import iter_matches
from src.stats.viz.style import apply_theme


ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "statsbomb"
OUTPUT_PATH = ROOT / "assets" / "throw_ins" / "barcelona_throw_ins_success_probability.png"
TEAM = "Barcelona"


def build_attack_dirs(events: list[dict]) -> dict[tuple[int, str], str]:
    """Infer attacking direction per (period, team)."""
    gk_xs: dict[tuple[int, str], list[float]] = defaultdict(list)
    pass_dxs: dict[tuple[int, str], list[float]] = defaultdict(list)

    for ev in events:
        period = ev.get("period")
        team = ev.get("team", {}).get("name", "")
        if period is None or not team:
            continue
        key = (period, team)

        if f.is_goal_kick(ev):
            loc = ev.get("location")
            if loc:
                gk_xs[key].append(loc[0])

        if f.is_pass(ev):
            loc = ev.get("location")
            end = ev.get("pass", {}).get("end_location")
            if loc and end:
                pass_dxs[key].append(end[0] - loc[0])

    directions: dict[tuple[int, str], str] = {}
    for key in set(gk_xs) | set(pass_dxs):
        if gk_xs[key]:
            med = sorted(gk_xs[key])[len(gk_xs[key]) // 2]
            directions[key] = "right" if med < 60 else "left"
        elif pass_dxs[key]:
            med = sorted(pass_dxs[key])[len(pass_dxs[key]) // 2]
            directions[key] = "right" if med > 0 else "left"

    return directions


def normalize_left_to_right(x: float, y: float, attack_dir: str) -> tuple[float, float]:
    """Mirror x when needed so the focus team always attacks toward x=120."""
    if attack_dir == "left":
        return 120 - x, y
    return x, y


def collect_barcelona_throw_ins(data_dir: Path) -> tuple[list[dict], int]:
    """Collect normalised Barcelona throw-ins from all matches."""
    throws: list[dict] = []
    match_count = 0

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(TEAM, row, events)
        if sb_name is None:
            continue

        match_count += 1
        attack_dirs = build_attack_dirs(events)

        for ev in events:
            if not f.is_throw_in(ev) or not f.by_team(ev, sb_name):
                continue

            period = ev.get("period")
            loc = ev.get("location")
            end = ev.get("pass", {}).get("end_location")
            if period is None or not loc or not end:
                continue

            attack_dir = attack_dirs.get((period, sb_name))
            if attack_dir is None:
                continue

            sx, sy = normalize_left_to_right(loc[0], loc[1], attack_dir)
            ex, ey = normalize_left_to_right(end[0], end[1], attack_dir)
            success_prob = ev.get("pass", {}).get("pass_success_probability")

            throws.append(
                {
                    "sx": sx,
                    "sy": sy,
                    "ex": ex,
                    "ey": ey,
                    "prob": success_prob,
                    "completed": ev.get("pass", {}).get("outcome") is None,
                }
            )

    return throws, match_count


def draw_pitch(ax: plt.Axes) -> None:
    """Draw a full StatsBomb pitch using the same visual grammar as the reference."""
    line_color = "#222222"
    lw_main = 1.6
    lw_minor = 1.0

    ax.plot([0, 120, 120, 0, 0], [0, 0, 80, 80, 0], color=line_color, lw=lw_main)
    ax.plot([60, 60], [0, 80], color=line_color, lw=lw_minor)

    ax.add_patch(plt.Circle((60, 40), 0.35, color=line_color, fill=True))
    ax.add_patch(plt.Circle((60, 40), 10, color=line_color, fill=False, lw=lw_minor))

    ax.plot([0, 18, 18, 0], [18, 18, 62, 62], color=line_color, lw=lw_minor)
    ax.plot([120, 102, 102, 120], [18, 18, 62, 62], color=line_color, lw=lw_minor)
    ax.plot([0, 6, 6, 0], [30, 30, 50, 50], color=line_color, lw=lw_minor)
    ax.plot([120, 114, 114, 120], [30, 30, 50, 50], color=line_color, lw=lw_minor)

    ax.add_patch(plt.Circle((12, 40), 0.3, color=line_color, fill=True))
    ax.add_patch(plt.Circle((108, 40), 0.3, color=line_color, fill=True))

    ax.add_patch(patches.Arc((12, 40), width=20, height=20, theta1=-53.1, theta2=53.1, color=line_color, lw=lw_minor))
    ax.add_patch(patches.Arc((108, 40), width=20, height=20, theta1=126.9, theta2=233.1, color=line_color, lw=lw_minor))

    ax.add_patch(patches.Arc((0, 0), width=2, height=2, theta1=0, theta2=90, color=line_color, lw=lw_minor))
    ax.add_patch(patches.Arc((0, 80), width=2, height=2, theta1=270, theta2=360, color=line_color, lw=lw_minor))
    ax.add_patch(patches.Arc((120, 0), width=2, height=2, theta1=90, theta2=180, color=line_color, lw=lw_minor))
    ax.add_patch(patches.Arc((120, 80), width=2, height=2, theta1=180, theta2=270, color=line_color, lw=lw_minor))


def main() -> None:
    apply_theme()

    throw_ins, match_count = collect_barcelona_throw_ins(DATA_DIR)
    if not throw_ins:
        raise RuntimeError("No Barcelona throw-ins found. Check the data path.")

    probs = [t["prob"] for t in throw_ins if t["prob"] is not None]
    completed = sum(1 for t in throw_ins if t["completed"])

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.grid(False)
    draw_pitch(ax)

    custom_colors = ["#8b0000", "#ff5a5f", "#d9d9d9", "#2f7ed8"]
    cmap = mcolors.LinearSegmentedColormap.from_list("throw_prob", custom_colors)
    norm = mcolors.Normalize(vmin=0, vmax=1)

    for throw in throw_ins:
        prob = throw["prob"]
        color = cmap(norm(prob)) if prob is not None else "#9e9e9e"
        ax.arrow(
            throw["sx"],
            throw["sy"],
            throw["ex"] - throw["sx"],
            throw["ey"] - throw["sy"],
            width=0.22,
            head_width=0.95,
            head_length=1.35,
            length_includes_head=True,
            color=color,
            alpha=0.8,
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.04)
    cbar.set_label("Pass Success Probability", fontsize=12)

    subtitle = (
        f"{len(throw_ins)} throw-ins across {match_count} matches"
        f"  |  completion rate: {completed / len(throw_ins) * 100:.1f}%"
    )
    if probs:
        subtitle += f"  |  avg model probability: {sum(probs) / len(probs):.2f}"

    fig.suptitle(f"{TEAM} Throw-ins by Success Probability", fontsize=20, fontweight="bold", y=0.98)
    fig.text(
        0.5,
        0.935,
        f"Play direction normalised left to right  |  {subtitle}",
        ha="center",
        va="center",
        fontsize=11,
        color="#444444",
    )
    fig.subplots_adjust(top=0.88)
    ax.set_xlim(-5, 125)
    ax.set_ylim(85, -5)
    ax.axis("off")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
