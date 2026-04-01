"""Per-match set piece counts: focus team vs opponent.

For each set piece type, produces a grouped bar chart showing the
number of set pieces per match for the focus team and the opponent.

Saves all figures to ``assets/setpiece_counts/{team}/``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .. import filters as f
from ..data import iter_matches, get_team_names
from ..viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig
from .setpiece_maps import SET_PIECE_TYPES, _team_in_match

ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "setpiece_counts"
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"


def _collect_counts(
    team: str, data_dir: Path,
) -> dict[str, list[dict]]:
    """Return per-match counts for each set piece type.

    Result: ``{sp_name: [{"label": "vs X", "team": n, "opponent": m}, ...]}``
    """
    result: dict[str, list[dict]] = {name: [] for name, _ in SET_PIECE_TYPES}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue

        home, away = row.get("home", ""), row.get("away", "")
        opponent_csv = away if team in home else home
        match_label = f"vs {opponent_csv}"

        for sp_name, predicate in SET_PIECE_TYPES:
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

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Count")
    ax.legend()

    sp_label = sp_name.replace("_", " ").title()
    total_team = sum(team_vals)
    total_opp = sum(opp_vals)
    ax.set_title(
        f"{team} {sp_label} per match ({total_team} total vs {total_opp} opponent)",
        fontsize=14, fontweight="bold",
    )
    return fig


def run(team: str = TEAM, data_dir: Path = DATA, output_dir: Path | None = None) -> None:
    """Generate and save per-match set piece count charts for *team*."""
    if output_dir is None:
        output_dir = ASSETS_ROOT / team

    apply_theme()
    counts = _collect_counts(team, data_dir)

    for sp_name, _ in SET_PIECE_TYPES:
        matches = counts[sp_name]
        if not matches:
            print(f"  {sp_name}: no matches found for {team}")
            continue

        fig = _plot_counts(team, sp_name, matches)
        save_fig(fig, output_dir / f"{sp_name}.png")
        total_t = sum(m["team"] for m in matches)
        total_o = sum(m["opponent"] for m in matches)
        print(f"  {sp_name}: {total_t} {team}, {total_o} opponent across {len(matches)} matches → {output_dir / sp_name}.png")

    print(f"Done — saved to {output_dir}/")


if __name__ == "__main__":
    run()
