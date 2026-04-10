"""Shared plotting helpers used by every script in this snippet.

Two chart styles cover all the plots embedded in the wiki's *Stats* section:

* :func:`ranked_bar_chart` — landscape vertical bar chart, one bar per
  team, ordered descending, with the focus team highlighted in red and
  the league average drawn as an extra bar in orange. Used for every
  league-comparison plot (of01–04, oc01–04, df01–04, dc01–05).

* :func:`per_match_bar_chart` — grouped bar chart of a per-match metric
  for the focus team versus each of its opponents. Used for the four
  ``matches01–04`` plots in the wiki.

* :func:`combined_per_team_chart` — grouped bar chart of two metrics
  per team (e.g. goals + xG) ordered by the first metric. Used for the
  ``dc042_goals_xg_conceded_combined_corners`` plot.

The styling matches ``src/stats/viz/style.py`` so the snippet output is
visually consistent with the rest of the project, but the helper has no
dependency on that module — copy ``_plotting.py`` and ``_loader.py``
together with the analysis scripts and the snippet runs anywhere with
``matplotlib`` and ``numpy`` installed.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

# ── Palette ──────────────────────────────────────────────────────────

FOCUS_COLOR = "#a50026"     # Barcelona red
AVG_BAR_COLOR = "#f4a261"   # League average bar (orange)
OTHER_COLOR = "#4575b4"     # Other teams (blue)
GOALS_COLOR = "#c94040"
XG_COLOR = "#4575b4"

AVG_LABEL = "League Avg"


# ── Ranked league-comparison bar chart ───────────────────────────────


def ranked_bar_chart(
    data: dict[str, float],
    *,
    title: str,
    ylabel: str,
    focus_team: str,
    output_path: Path,
    fmt: str = ".2f",
) -> None:
    """Save a ranked vertical bar chart of *data* to *output_path*.

    Bars are ordered descending by value, with the league mean inserted
    at its sorted position. The focus team is drawn in red, the average
    bar in orange, all other teams in blue.
    """
    items = sorted(data.items(), key=lambda kv: kv[1], reverse=True)
    teams = [t for t, _ in items]
    vals = [v for _, v in items]

    league_avg = float(np.mean(vals))

    inserted = False
    for i, v in enumerate(vals):
        if league_avg >= v:
            teams.insert(i, AVG_LABEL)
            vals.insert(i, league_avg)
            inserted = True
            break
    if not inserted:
        teams.append(AVG_LABEL)
        vals.append(league_avg)

    colors = [
        AVG_BAR_COLOR if t == AVG_LABEL
        else FOCUS_COLOR if t == focus_team
        else OTHER_COLOR
        for t in teams
    ]

    n = len(teams)
    fig, ax = plt.subplots(figsize=(max(14.0, n * 0.56), 7))
    x = np.arange(n)
    bars = ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.5, width=0.72)

    y_max = float(max(vals)) if vals else 1.0
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + y_max * 0.015,
            f"{val:{fmt}}",
            ha="center", va="bottom", fontsize=7.5,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylim(0, y_max * 1.18)
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Patch(facecolor=FOCUS_COLOR, label=focus_team),
            Patch(facecolor=AVG_BAR_COLOR, label=AVG_LABEL),
            Patch(facecolor=OTHER_COLOR, label="Other teams"),
        ],
        loc="upper right", frameon=True, fontsize=9,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  saved {output_path}")


# ── Combined two-metric chart (per team, grouped bars) ───────────────


def combined_per_team_chart(
    teams_data: dict[str, tuple[float, float]],
    *,
    title: str,
    ylabel: str,
    bar1_label: str,
    bar2_label: str,
    focus_team: str,
    output_path: Path,
    bar1_fmt: str = ".0f",
    bar2_fmt: str = ".1f",
    bar1_color: str = GOALS_COLOR,
    bar2_color: str = XG_COLOR,
) -> None:
    """Grouped bar chart of (metric1, metric2) per team, ordered by metric1."""
    items = sorted(
        teams_data.items(),
        key=lambda kv: (kv[1][0], kv[1][1]),
        reverse=True,
    )
    teams = [t for t, _ in items]
    vals1 = [v[0] for _, v in items]
    vals2 = [v[1] for _, v in items]

    n = len(teams)
    x = np.arange(n)
    w = 0.36

    fig, ax = plt.subplots(figsize=(max(14.0, n * 0.65), 7))
    bars1 = ax.bar(x - w / 2, vals1, w, color=bar1_color, label=bar1_label, zorder=2)
    bars2 = ax.bar(x + w / 2, vals2, w, color=bar2_color, label=bar2_label, alpha=0.85, zorder=2)

    if focus_team in teams:
        bi = teams.index(focus_team)
        for off, val in ((-w / 2, vals1[bi]), (w / 2, vals2[bi])):
            ax.bar(bi + off, val, w, color="none", edgecolor="black", linewidth=2.0, zorder=3)

    y_max = float(max(vals1 + vals2)) if (vals1 or vals2) else 1.0
    for bar, val in zip(bars1, vals1):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + y_max * 0.015,
                f"{val:{bar1_fmt}}",
                ha="center", va="bottom", fontsize=7.5,
            )
    for bar, val in zip(bars2, vals2):
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + y_max * 0.015,
                f"{val:{bar2_fmt}}",
                ha="center", va="bottom", fontsize=7.5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    if focus_team in teams:
        lbl = ax.get_xticklabels()[teams.index(focus_team)]
        lbl.set_color(FOCUS_COLOR)
        lbl.set_fontweight("bold")

    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_ylim(0, y_max * 1.18)
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", frameon=True, fontsize=10)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  saved {output_path}")


# ── Per-match grouped bar chart (focus team vs opponent) ─────────────


def per_match_bar_chart(
    matches: list[dict],
    *,
    title: str,
    ylabel: str,
    focus_team: str,
    team_key: str,
    opp_key: str,
    output_path: Path,
    fmt: str = ".0f",
    fixed_y_max: float | None = None,
    team_goals_key: str | None = None,
    opp_goals_key: str | None = None,
) -> None:
    """Grouped bars of one metric per match (focus team vs opponent).

    *matches* is a list of dicts with at least ``label``, *team_key*
    and *opp_key*. When *team_goals_key*/*opp_goals_key* are given,
    actual goal counts are written inside each bar — used by the xG
    plots so the reader can see how many of those xG turned into goals.
    """
    labels = [m["label"] for m in matches]
    team_vals = [m[team_key] for m in matches]
    opp_vals = [m[opp_key] for m in matches]
    team_goals = [m[team_goals_key] for m in matches] if team_goals_key else None
    opp_goals = [m[opp_goals_key] for m in matches] if opp_goals_key else None

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.3), 6))
    ax.bar(x - width / 2, team_vals, width, label=focus_team, color=FOCUS_COLOR)
    ax.bar(x + width / 2, opp_vals, width, label="Opponent", color=OTHER_COLOR, alpha=0.7)

    data_max = max(max(team_vals, default=0.0), max(opp_vals, default=0.0), 0.01)
    y_ceil = fixed_y_max if fixed_y_max is not None else data_max * 1.18
    label_ref = fixed_y_max if fixed_y_max is not None else data_max

    for xi, (tv, ov) in enumerate(zip(team_vals, opp_vals)):
        if tv > 0:
            ax.text(xi - width / 2, tv + label_ref * 0.02, f"{tv:{fmt}}",
                    ha="center", va="bottom", fontsize=9)
        if ov > 0:
            ax.text(xi + width / 2, ov + label_ref * 0.02, f"{ov:{fmt}}",
                    ha="center", va="bottom", fontsize=9)

        if team_goals is not None:
            g = team_goals[xi]
            if g > 0:
                lab = f"{g} G"
                if tv > label_ref * 0.08:
                    ax.text(xi - width / 2, tv / 2, lab,
                            ha="center", va="center", fontsize=9,
                            fontweight="bold", color="white")
                else:
                    ax.text(xi - width / 2, tv + label_ref * 0.10, lab,
                            ha="center", va="bottom", fontsize=8,
                            fontweight="bold", color=FOCUS_COLOR)
        if opp_goals is not None:
            g = opp_goals[xi]
            if g > 0:
                lab = f"{g} G"
                if ov > label_ref * 0.08:
                    ax.text(xi + width / 2, ov / 2, lab,
                            ha="center", va="center", fontsize=9,
                            fontweight="bold", color="white")
                else:
                    ax.text(xi + width / 2, ov + label_ref * 0.10, lab,
                            ha="center", va="bottom", fontsize=8,
                            fontweight="bold", color=OTHER_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, y_ceil)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  saved {output_path}")
