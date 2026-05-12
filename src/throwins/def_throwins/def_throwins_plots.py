"""
def_throwins_plots.py

Two bar charts for Barcelona's defensive throw-in analysis:
  1. Win-back rate by zone (Defensive / Middle / Attacking).
  2. All teams ranked by defensive win-back rate — Barcelona highlighted.

Usage:
    python src/throwins/def_throwins/def_throwins_plots.py
"""

from throwins_defense import (
    collect_data,
    plot_zone_stats,
    plot_team_comparison,
    plot_opponent_throw_direction,
    collect_side_change_stats,
    plot_side_change_rate,
)

if __name__ == "__main__":
    barca_df, team_stats = collect_data()
    plot_zone_stats(barca_df)
    plot_team_comparison(team_stats)
    plot_opponent_throw_direction(team_stats)

    print("Collecting side-change data ...")
    side_stats = collect_side_change_stats()
    plot_side_change_rate(side_stats)
