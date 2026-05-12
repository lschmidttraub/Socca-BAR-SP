"""
def_throwins_corridor.py

Middle-corridor analysis of opponent throw-ins against Barcelona.

Chart 1 — Barcelona's win-back rate when the throw lands in the middle corridor vs wide.
Chart 2 — All teams ranked by their win-back rate specifically on middle-corridor throws
           (Barcelona highlighted in red).

Usage:
    python src/throwins/def_throwins/def_throwins_corridor.py
"""

from throwins_defense import (
    _CORRIDOR_Y_MIN,
    _CORRIDOR_Y_MAX,
    collect_data,
    plot_corridor_winback,
    plot_corridor_team_comparison,
)

if __name__ == "__main__":
    barca_df, team_stats = collect_data()

    df = barca_df.dropna(subset=["end_y"])
    n_corr = int(df["end_y"].between(_CORRIDOR_Y_MIN, _CORRIDOR_Y_MAX).sum())
    n_tot  = len(df)
    print(f"\nOpponent throw-ins vs Barcelona (with end location): {n_tot}")
    print(f"Into middle corridor: {n_corr}  ({n_corr / n_tot * 100:.1f}%)" if n_tot else "")

    plot_corridor_winback(barca_df, team_stats=team_stats)
    plot_corridor_team_comparison(team_stats)
