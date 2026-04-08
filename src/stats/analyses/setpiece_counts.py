"""Per-match set piece counts: focus team vs opponent.

For each set piece type, produces a grouped bar chart showing the
number of set pieces per match for the focus team and the opponent.

Free kicks are restricted to the attacking half (x >= 60).

Additional charts produced for corners and free kicks:
  *_attempts.png  – shots from set piece sequences (team vs opponent)
  *_xg.png        – cumulative xG from set piece sequences

Saves all figures to ``assets/setpiece_counts/{team}/``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .. import filters as f
from ..data import iter_matches
from ..viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig
from .setpiece_maps import _team_in_match

ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "setpiece_counts"
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"

ATTACKING_HALF_X = 60.0  # x >= 60 → attacking half (FK filter)

# Local set piece types — free kicks restricted to the attacking half
_SP_TYPES = [
    ("corners",    lambda e: f.is_corner_pass(e)),
    ("free_kicks", lambda e: (f.is_fk_pass(e) or f.is_fk_shot(e))
                             and bool(e.get("location") and e["location"][0] >= ATTACKING_HALF_X)),
    ("throw_ins",  lambda e: f.is_throw_in(e)),
    ("goal_kicks", lambda e: f.is_goal_kick(e)),
]

# Set piece types that have sequence-level shot / xG stats
_SEQUENCE_SP = [
    ("corners",    "From Corner"),
    ("free_kicks", "From Free Kick"),
]


def _collect_counts(
    team: str, data_dir: Path,
) -> dict[str, list[dict]]:
    """Return per-match counts for each set piece type.

    Result: ``{sp_name: [{"label": "vs X", "team": n, "opponent": m}, ...]}``
    Free kicks are restricted to the attacking half (x >= ATTACKING_HALF_X).
    """
    result: dict[str, list[dict]] = {name: [] for name, _ in _SP_TYPES}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue

        home, away = row.get("home", ""), row.get("away", "")
        opponent_csv = away if team in home else home
        match_label = f"vs {opponent_csv}"

        for sp_name, predicate in _SP_TYPES:
            team_count = 0
            opp_count = 0
            for e in events:
                if not predicate(e):
                    continue
                if f.by_team(e, sb_name):
                    team_count += 1
                else:
                    opp_count += 1
            result[sp_name].append({
                "label": match_label,
                "team": team_count,
                "opponent": opp_count,
            })

    return result


def _collect_sequences(
    team: str, data_dir: Path,
) -> dict[str, list[dict]]:
    """Per-match shots, xG, and goals from corner / FK sequences.

    Result: ``{sp_name: [{"label", "team_shots", "opp_shots",
                          "team_xg", "opp_xg", "team_goals", "opp_goals"}, ...]}``
    """
    result: dict[str, list[dict]] = {name: [] for name, _ in _SEQUENCE_SP}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue

        home, away = row.get("home", ""), row.get("away", "")
        opponent_csv = away if team in home else home
        match_label = f"vs {opponent_csv}"

        for sp_name, pattern in _SEQUENCE_SP:
            t_shots = 0
            o_shots = 0
            t_xg = 0.0
            o_xg = 0.0
            t_goals = 0
            o_goals = 0

            for e in events:
                if not f.is_shot(e) or f.is_penalty_shot(e):
                    continue
                if f.play_pattern(e) != pattern:
                    continue
                xg = f.shot_xg(e)
                goal = 1 if f.is_goal(e) else 0
                if f.by_team(e, sb_name):
                    t_shots += 1
                    t_xg += xg
                    t_goals += goal
                else:
                    o_shots += 1
                    o_xg += xg
                    o_goals += goal

            result[sp_name].append({
                "label": match_label,
                "team_shots": t_shots, "opp_shots": o_shots,
                "team_xg": t_xg, "opp_xg": o_xg,
                "team_goals": t_goals, "opp_goals": o_goals,
            })

    return result


def _plot_counts(
    team: str,
    sp_name: str,
    matches: list[dict],
) -> plt.Figure:
    """Grouped bar chart of per-match counts."""
    labels = [m["label"] for m in matches]
    team_vals = [m["team"] for m in matches]
    opp_vals = [m["opponent"] for m in matches]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.3), 6))
    ax.bar(x - width / 2, team_vals, width, label=team, color=FOCUS_COLOR)
    ax.bar(x + width / 2, opp_vals, width, label="Opponent", color=AVG_COLOR, alpha=0.7)

    y_max = max(max(team_vals, default=0), max(opp_vals, default=0), 1)
    for xi, (tv, ov) in enumerate(zip(team_vals, opp_vals)):
        ax.text(xi - width / 2, tv + y_max * 0.02, str(tv),
                ha="center", va="bottom", fontsize=9)
        ax.text(xi + width / 2, ov + y_max * 0.02, str(ov),
                ha="center", va="bottom", fontsize=9)
    ax.set_ylim(0, y_max * 1.18)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Count")
    ax.legend()

    sp_label = sp_name.replace("_", " ").title()
    total_team = sum(team_vals)
    total_opp = sum(opp_vals)
    fk_note = "  (attacking half only)" if sp_name == "free_kicks" else ""
    ax.set_title(
        f"{team} {sp_label} per match{fk_note} ({total_team} total vs {total_opp} opponent)",
        fontsize=14, fontweight="bold",
    )
    return fig


XG_Y_MAX = 2.0  # fixed upper limit for xG plots


def _plot_metric(
    team: str,
    sp_name: str,
    matches: list[dict],
    team_key: str,
    opp_key: str,
    ylabel: str,
    title_suffix: str,
    fmt: str = ".1f",
    fixed_y_max: float | None = None,
    team_goals_key: str | None = None,
    opp_goals_key: str | None = None,
) -> plt.Figure:
    """Grouped bar chart of a per-match numeric metric (shots, xG, goals, ...).

    When *fixed_y_max* is given the y-axis is clamped to [0, fixed_y_max].
    When *team_goals_key* / *opp_goals_key* are given, actual goal counts are
    shown inside each bar as a bold annotation, e.g. "1 G".
    """
    labels = [m["label"] for m in matches]
    team_vals = [m[team_key] for m in matches]
    opp_vals = [m[opp_key] for m in matches]
    team_goals = [m[team_goals_key] for m in matches] if team_goals_key else None
    opp_goals  = [m[opp_goals_key]  for m in matches] if opp_goals_key  else None

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.3), 6))
    ax.bar(x - width / 2, team_vals, width, label=team, color=FOCUS_COLOR)
    ax.bar(x + width / 2, opp_vals, width, label="Opponent", color=AVG_COLOR, alpha=0.7)

    data_max = max(max(team_vals, default=0), max(opp_vals, default=0), 0.01)
    y_ceil = fixed_y_max if fixed_y_max is not None else data_max * 1.18
    label_ref = fixed_y_max if fixed_y_max is not None else data_max

    for xi, (tv, ov) in enumerate(zip(team_vals, opp_vals)):
        # xG value above bar
        if tv > 0:
            ax.text(xi - width / 2, tv + label_ref * 0.02, f"{tv:{fmt}}",
                    ha="center", va="bottom", fontsize=9)
        if ov > 0:
            ax.text(xi + width / 2, ov + label_ref * 0.02, f"{ov:{fmt}}",
                    ha="center", va="bottom", fontsize=9)

        # Goal count inside the bar (bold, white)
        if team_goals is not None:
            g = team_goals[xi]
            label = f"{g} G" if g != 1 else "1 G"
            bar_mid = tv / 2 if tv > 0 else -1
            if tv > label_ref * 0.08:   # bar tall enough to fit text
                ax.text(xi - width / 2, bar_mid, label,
                        ha="center", va="center", fontsize=9,
                        fontweight="bold", color="white")
            elif g > 0:                  # bar too short — place just above bar
                ax.text(xi - width / 2, tv + label_ref * 0.10, label,
                        ha="center", va="bottom", fontsize=8,
                        fontweight="bold", color=FOCUS_COLOR)
        if opp_goals is not None:
            g = opp_goals[xi]
            label = f"{g} G" if g != 1 else "1 G"
            bar_mid = ov / 2 if ov > 0 else -1
            if ov > label_ref * 0.08:
                ax.text(xi + width / 2, bar_mid, label,
                        ha="center", va="center", fontsize=9,
                        fontweight="bold", color="white")
            elif g > 0:
                ax.text(xi + width / 2, ov + label_ref * 0.10, label,
                        ha="center", va="bottom", fontsize=8,
                        fontweight="bold", color=AVG_COLOR)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, y_ceil)
    ax.legend()

    sp_label = sp_name.replace("_", " ").title()
    ax.set_title(
        f"{team} — {sp_label} {title_suffix}",
        fontsize=14, fontweight="bold",
    )
    return fig


def run(team: str = TEAM, data_dir: Path = DATA, output_dir: Path | None = None) -> None:
    """Generate and save per-match set piece charts for *team*."""
    if output_dir is None:
        output_dir = ASSETS_ROOT / team

    apply_theme()
    counts = _collect_counts(team, data_dir)
    sequences = _collect_sequences(team, data_dir)

    # ── Count charts (all four set piece types) ───────────────────────
    for sp_name, _ in _SP_TYPES:
        matches = counts[sp_name]
        if not matches:
            print(f"  {sp_name}: no matches found for {team}")
            continue

        fig = _plot_counts(team, sp_name, matches)
        save_fig(fig, output_dir / f"{sp_name}.png")
        total_t = sum(m["team"] for m in matches)
        total_o = sum(m["opponent"] for m in matches)
        print(f"  {sp_name}: {total_t} {team}, {total_o} opponent across {len(matches)} matches")

    # ── Sequence charts (corners and free kicks) ──────────────────────
    for sp_name, _ in _SEQUENCE_SP:
        seq = sequences[sp_name]
        if not seq:
            print(f"  {sp_name} sequences: no data for {team}")
            continue

        sp_label = sp_name.replace("_", " ").title()

        fig = _plot_metric(
            team, sp_name, seq,
            "team_shots", "opp_shots",
            "Attempts", f"Attempts from {sp_label} Sequences",
            fmt=".0f",
        )
        save_fig(fig, output_dir / f"{sp_name}_attempts.png")
        print(f"  {sp_name}_attempts: saved")

        fig = _plot_metric(
            team, sp_name, seq,
            "team_xg", "opp_xg",
            "xG", f"xG from {sp_label} Sequences",
            fmt=".2f",
            fixed_y_max=XG_Y_MAX,
            team_goals_key="team_goals",
            opp_goals_key="opp_goals",
        )
        save_fig(fig, output_dir / f"{sp_name}_xg.png")
        print(f"  {sp_name}_xg: saved")

    print(f"Done — saved to {output_dir}/")


if __name__ == "__main__":
    run()