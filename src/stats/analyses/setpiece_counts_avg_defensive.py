"""Average defensive set piece stats per team.

Mirrors ``setpiece_counts_avg.py`` but from a defensive perspective:
every metric measures what a team concedes from opponent corner and free-kick
sequences.

Charts produced (per output directory)
---------------------------------------
Corners conceded
  corners_conceded_avg.png
  attempts_conceded_corner_avg.png
  avg_goals_conceded_corner.png
  total_goals_conceded_corner.png
  xg_conceded_corner_avg.png
  total_xg_conceded_corner.png
  goals_xg_conceded_combined_corners.png

Free kicks conceded
  free_kicks_conceded_avg.png
  attempts_conceded_fk_avg.png
  avg_goals_conceded_fk.png
  total_goals_conceded_fk.png
  xg_conceded_fk_avg.png
  total_xg_conceded_fk.png
  goals_xg_conceded_combined_fk.png
"""

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from stats import filters as f
    from stats.data import iter_matches
    from stats.viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig
    from stats.analyses.setpiece_maps import _team_in_match
else:
    from .. import filters as f
    from ..data import iter_matches
    from ..viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig
    from .setpiece_maps import _team_in_match

ASSETS_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "assets"
    / "setpiece_counts_avg_defensive"
)
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"
AVG_LABEL = "League Avg"
AVG_BAR_COLOR = "#f4a261"

OPPONENT_HALF_X = 60.0

TOP_8: frozenset[str] = frozenset({
    "Arsenal", "Bayern München", "Liverpool", "Tottenham Hotspur",
    "Chelsea", "Sporting CP", "Manchester City", "Barcelona",
})

_GOALS_COLOR = "#c94040"
_XG_COLOR = "#4575b4"
_ATTEMPT_RATE_COLOR = "#2ca02c"
_GOAL_RATE_COLOR = "#9467bd"


def _in_offensive_third(e: dict) -> bool:
    loc = e.get("location")
    return bool(loc and loc[0] >= OPPONENT_HALF_X)


def _collect_all_teams_defensive(data_dir: Path) -> dict[str, dict]:
    """Return per-team defensive totals across all matches."""
    records: dict[str, dict] = defaultdict(lambda: {
        "matches": 0,
        "corners_conceded": 0,
        "free_kicks_conceded": 0,
        "shots_conceded_corner": 0,
        "shots_conceded_fk": 0,
        "goals_conceded_corner": 0,
        "goals_conceded_fk": 0,
        "xg_conceded_corner": 0.0,
        "xg_conceded_fk": 0.0,
    })

    for row, events in iter_matches(data_dir):
        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        matchup = [
            (home_csv, away_csv),
            (away_csv, home_csv),
        ]

        for team_csv, opponent_csv in matchup:
            if not team_csv or not opponent_csv:
                continue

            team_sb = _team_in_match(team_csv, row, events)
            opp_sb = _team_in_match(opponent_csv, row, events)
            if team_sb is None or opp_sb is None:
                continue

            rec = records[team_csv]
            rec["matches"] += 1

            for e in events:
                if not f.by_team(e, opp_sb):
                    continue

                if f.is_corner_pass(e):
                    rec["corners_conceded"] += 1

                if (f.is_fk_pass(e) or f.is_fk_shot(e)) and _in_offensive_third(e):
                    rec["free_kicks_conceded"] += 1

                if (
                    f.is_shot(e)
                    and f.play_pattern(e) == "From Corner"
                    and not f.is_penalty_shot(e)
                ):
                    rec["shots_conceded_corner"] += 1
                    rec["xg_conceded_corner"] += f.shot_xg(e)
                    if f.is_goal(e):
                        rec["goals_conceded_corner"] += 1

                if (
                    f.is_shot(e)
                    and f.play_pattern(e) == "From Free Kick"
                    and not f.is_penalty_shot(e)
                ):
                    rec["shots_conceded_fk"] += 1
                    rec["xg_conceded_fk"] += f.shot_xg(e)
                    if f.is_goal(e):
                        rec["goals_conceded_fk"] += 1

    return dict(records)


def _compute_rates(records: dict[str, dict]) -> None:
    """Add defensive ratio metrics in-place."""
    for r in records.values():
        c = r["corners_conceded"]
        fk = r["free_kicks_conceded"]
        r["attempt_rate_corner"] = r["shots_conceded_corner"] / c if c else 0.0
        r["xg_rate_corner"] = r["xg_conceded_corner"] / c if c else 0.0
        r["goal_rate_corner"] = r["goals_conceded_corner"] / c if c else 0.0
        r["attempt_rate_fk"] = r["shots_conceded_fk"] / fk if fk else 0.0
        r["xg_rate_fk"] = r["xg_conceded_fk"] / fk if fk else 0.0
        r["goal_rate_fk"] = r["goals_conceded_fk"] / fk if fk else 0.0


def _series(records: dict[str, dict], metric: str, per_game: bool) -> dict[str, float]:
    out: dict[str, float] = {}
    for team, r in records.items():
        n = r["matches"]
        if n == 0:
            continue
        val = float(r[metric])
        out[team] = val / n if per_game else val
    return out


def _plot_bar(
    data: dict[str, float],
    title: str,
    ylabel: str,
    focus_team: str,
    output_path: Path,
    fmt: str = ".2f",
    tiebreak_data: dict[str, float] | None = None,
) -> None:
    if tiebreak_data:
        items = sorted(
            data.items(),
            key=lambda kv: (kv[1], tiebreak_data.get(kv[0], 0.0)),
            reverse=True,
        )
    else:
        items = sorted(data.items(), key=lambda kv: kv[1], reverse=True)
    teams = [t for t, _ in items]
    vals = [v for _, v in items]

    league_avg = float(np.mean(list(data.values())))

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
        else AVG_COLOR
        for t in teams
    ]

    n = len(teams)
    fig, ax = plt.subplots(figsize=(max(14.0, n * 0.56), 7))
    x = np.arange(n)
    bars = ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.5, width=0.72)

    y_max: float = float(max(vals)) if vals else 1.0
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
    ax.legend(
        handles=[
            Patch(facecolor=FOCUS_COLOR, label=focus_team),
            Patch(facecolor=AVG_BAR_COLOR, label=AVG_LABEL),
            Patch(facecolor=AVG_COLOR, label="Other teams"),
        ],
        loc="upper right", frameon=True, fontsize=9,
    )

    save_fig(fig, output_path)
    print(f"    -> {output_path.name}")


def _plot_combined_sp(
    records: dict[str, dict],
    bar1_key: str,
    bar2_key: str,
    sp_label: str,
    focus_team: str,
    output_path: Path,
    bar1_label: str = "Goals Conceded",
    bar2_label: str = "xG Conceded",
    bar1_color: str = _GOALS_COLOR,
    bar2_color: str = _XG_COLOR,
    bar1_fmt: str = ".0f",
    bar2_fmt: str = ".1f",
    ylabel: str = "Goals / xG",
    bar_mid_key: str | None = None,
    bar_mid_label: str = "",
    bar_mid_color: str = _XG_COLOR,
    bar_mid_fmt: str = ".3f",
) -> None:
    sort_key = (
        (lambda t: (records[t][bar1_key], records[t][bar_mid_key], records[t][bar2_key]))
        if bar_mid_key else
        (lambda t: (records[t][bar1_key], records[t][bar2_key]))
    )
    teams = sorted(records.keys(), key=sort_key, reverse=True)

    vals1 = [float(records[t][bar1_key]) for t in teams]
    vals2 = [float(records[t][bar2_key]) for t in teams]
    valsm = [float(records[t][bar_mid_key]) for t in teams] if bar_mid_key else []

    n_bars = 3 if bar_mid_key else 2
    w = 0.72 / n_bars
    offsets = [-w, 0.0, w] if n_bars == 3 else [-w / 2, w / 2]

    n = len(teams)
    x = np.arange(n)
    fig, ax = plt.subplots(figsize=(max(14.0, n * (0.65 + 0.2 * (n_bars - 2))), 7))

    bars1 = ax.bar(x + offsets[0], vals1, w, color=bar1_color, label=bar1_label, zorder=2)
    barsm = (
        ax.bar(x + offsets[1], valsm, w, color=bar_mid_color,
               label=bar_mid_label, zorder=2, alpha=0.85)
        if bar_mid_key else []
    )
    bars2 = ax.bar(x + offsets[-1], vals2, w, color=bar2_color,
                   label=bar2_label, zorder=2, alpha=0.85)

    if focus_team in teams:
        bi = teams.index(focus_team)
        focus_vals = [vals1[bi]] + ([valsm[bi]] if bar_mid_key else []) + [vals2[bi]]
        for off, val in zip(offsets, focus_vals):
            ax.bar(bi + off, val, w, color="none", edgecolor="black", linewidth=2.0, zorder=3)

    labeled: list[tuple] = (
        [(b, v, bar1_fmt) for b, v in zip(bars1, vals1)] +
        ([(b, v, bar_mid_fmt) for b, v in zip(barsm, valsm)] if bar_mid_key else []) +
        [(b, v, bar2_fmt) for b, v in zip(bars2, vals2)]
    )
    all_vals = vals1 + valsm + vals2
    y_max: float = float(max(all_vals)) if all_vals else 1.0
    for bar, val, fmt in labeled:
        if val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + y_max * 0.015,
                f"{val:{fmt}}", ha="center", va="bottom", fontsize=7.5,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)

    if focus_team in teams:
        lbl = ax.get_xticklabels()[teams.index(focus_team)]
        lbl.set_color(FOCUS_COLOR)
        lbl.set_fontweight("bold")

    mid_title = f", {bar_mid_label}," if bar_mid_key else " and"
    ax.set_ylabel(ylabel)
    ax.set_title(
        f"{bar1_label}{mid_title} and {bar2_label} from {sp_label} Sequences Conceded"
        f" - ordered by {bar1_label}",
        fontsize=14, fontweight="bold",
    )
    ax.set_ylim(0, y_max * 1.18)

    legend_handles = [Patch(facecolor=bar1_color, label=bar1_label)]
    if bar_mid_key:
        legend_handles.append(Patch(facecolor=bar_mid_color, label=bar_mid_label, alpha=0.85))
    legend_handles.append(Patch(facecolor=bar2_color, label=bar2_label, alpha=0.85))
    ax.legend(handles=legend_handles, loc="upper right", frameon=True, fontsize=10)

    save_fig(fig, output_path)
    print(f"    -> {output_path.name}")


_CHARTS: list[tuple[str, str, str, str, bool, str, str | None]] = [
    (
        "corners_conceded",
        "Average Corners Faced per Game",
        "Corners conceded / game",
        "corners_conceded_avg.png",
        True,
        ".2f",
        None,
    ),
    (
        "free_kicks_conceded",
        f"Average Free Kicks Faced in Own Half per Game (x >= {OPPONENT_HALF_X:.0f} for opponent)",
        "Free kicks conceded / game",
        "free_kicks_conceded_avg.png",
        True,
        ".2f",
        None,
    ),
    (
        "shots_conceded_corner",
        "Average Attempts Conceded from Corner Sequences per Game",
        "Attempts conceded / game",
        "attempts_conceded_corner_avg.png",
        True,
        ".2f",
        None,
    ),
    (
        "shots_conceded_fk",
        "Average Attempts Conceded from Free Kick Sequences per Game",
        "Attempts conceded / game",
        "attempts_conceded_fk_avg.png",
        True,
        ".2f",
        None,
    ),
    (
        "goals_conceded_corner",
        "Average Goals Conceded from Corner Sequences per Game",
        "Goals conceded / game",
        "avg_goals_conceded_corner.png",
        True,
        ".3f",
        "xg_conceded_corner",
    ),
    (
        "goals_conceded_fk",
        "Average Goals Conceded from Free Kick Sequences per Game",
        "Goals conceded / game",
        "avg_goals_conceded_fk.png",
        True,
        ".3f",
        "xg_conceded_fk",
    ),
    (
        "goals_conceded_corner",
        "Total Goals Conceded from Corner Sequences",
        "Goals conceded (all games)",
        "total_goals_conceded_corner.png",
        False,
        ".0f",
        "xg_conceded_corner",
    ),
    (
        "goals_conceded_fk",
        "Total Goals Conceded from Free Kick Sequences",
        "Goals conceded (all games)",
        "total_goals_conceded_fk.png",
        False,
        ".0f",
        "xg_conceded_fk",
    ),
    (
        "xg_conceded_corner",
        "Average xG Conceded from Corner Sequences per Game",
        "xG conceded / game",
        "xg_conceded_corner_avg.png",
        True,
        ".3f",
        None,
    ),
    (
        "xg_conceded_fk",
        "Average xG Conceded from Free Kick Sequences per Game",
        "xG conceded / game",
        "xg_conceded_fk_avg.png",
        True,
        ".3f",
        None,
    ),
    (
        "xg_conceded_corner",
        "Total xG Conceded from Corner Sequences",
        "xG conceded (all games)",
        "total_xg_conceded_corner.png",
        False,
        ".1f",
        None,
    ),
    (
        "xg_conceded_fk",
        "Total xG Conceded from Free Kick Sequences",
        "xG conceded (all games)",
        "total_xg_conceded_fk.png",
        False,
        ".1f",
        None,
    ),
    (
        "attempt_rate_corner",
        "Attempts Conceded per Corner Faced",
        "Attempts conceded / corner",
        "attempt_rate_conceded_corner.png",
        False,
        ".3f",
        "goal_rate_corner",
    ),
    (
        "goal_rate_corner",
        "Goals Conceded per Corner Faced",
        "Goals conceded / corner",
        "goal_rate_conceded_corner.png",
        False,
        ".4f",
        "attempt_rate_corner",
    ),
    (
        "attempt_rate_fk",
        "Attempts Conceded per Free Kick Faced",
        "Attempts conceded / FK",
        "attempt_rate_conceded_fk.png",
        False,
        ".3f",
        "goal_rate_fk",
    ),
    (
        "goal_rate_fk",
        "Goals Conceded per Free Kick Faced",
        "Goals conceded / FK",
        "goal_rate_conceded_fk.png",
        False,
        ".4f",
        "attempt_rate_fk",
    ),
]


def _generate_charts(
    records: dict[str, dict],
    focus_team: str,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for metric, title, ylabel, filename, per_game, fmt, tiebreak in _CHARTS:
        data = _series(records, metric, per_game=per_game)
        tb = _series(records, tiebreak, per_game=per_game) if tiebreak else None
        _plot_bar(data, title, ylabel, focus_team, output_dir / filename, fmt=fmt,
                  tiebreak_data=tb)

    _plot_combined_sp(
        records,
        "goals_conceded_corner",
        "xg_conceded_corner",
        "Corner",
        focus_team,
        output_dir / "goals_xg_conceded_combined_corners.png",
    )
    _plot_combined_sp(
        records,
        "goals_conceded_fk",
        "xg_conceded_fk",
        "Free Kick",
        focus_team,
        output_dir / "goals_xg_conceded_combined_fk.png",
    )
    _plot_combined_sp(
        records,
        "goal_rate_corner",
        "attempt_rate_corner",
        "Corner",
        focus_team,
        output_dir / "rates_conceded_combined_corners.png",
        bar1_label="Goals Conceded / Corner",
        bar2_label="Attempts Conceded / Corner",
        bar1_color=_GOAL_RATE_COLOR,
        bar2_color=_ATTEMPT_RATE_COLOR,
        bar1_fmt=".4f",
        bar2_fmt=".3f",
        ylabel="Rate conceded (per corner)",
        bar_mid_key="xg_rate_corner",
        bar_mid_label="xG Conceded / Corner",
        bar_mid_color=_XG_COLOR,
        bar_mid_fmt=".3f",
    )
    _plot_combined_sp(
        records,
        "goal_rate_fk",
        "attempt_rate_fk",
        "Free Kick",
        focus_team,
        output_dir / "rates_conceded_combined_fk.png",
        bar1_label="Goals Conceded / FK",
        bar2_label="Attempts Conceded / FK",
        bar1_color=_GOAL_RATE_COLOR,
        bar2_color=_ATTEMPT_RATE_COLOR,
        bar1_fmt=".4f",
        bar2_fmt=".3f",
        ylabel="Rate conceded (per FK)",
        bar_mid_key="xg_rate_fk",
        bar_mid_label="xG Conceded / FK",
        bar_mid_color=_XG_COLOR,
        bar_mid_fmt=".3f",
    )


def run(
    focus_team: str = TEAM,
    data_dir: Path = DATA,
    output_dir: Path | None = None,
) -> None:
    """Collect defensive set piece data once, then generate charts."""
    if output_dir is None:
        output_dir = ASSETS_ROOT

    apply_theme()

    print("Collecting defensive set piece data for all teams...")
    records = _collect_all_teams_defensive(data_dir)
    _compute_rates(records)
    n_teams = len(records)
    n_matches = sum(r["matches"] for r in records.values()) // 2
    print(f"  {n_teams} teams · {n_matches} matches")

    if focus_team not in records:
        print(f"  Warning: '{focus_team}' not found - check team name.")

    print(f"\nAll teams -> {output_dir}/")
    _generate_charts(records, focus_team, output_dir)

    records_top8 = {t: r for t, r in records.items() if t in TOP_8}
    missing = TOP_8 - records_top8.keys()
    if missing:
        print(f"  Note: top-8 teams not found in data: {missing}")
    print(f"\nTop-8 -> {output_dir / 'top8'}/")
    _generate_charts(records_top8, focus_team, output_dir / "top8")

    n_charts = len(_CHARTS) + 4
    print(f"\nDone - {n_charts} x 2 charts saved to {output_dir}/")


if __name__ == "__main__":
    run()
