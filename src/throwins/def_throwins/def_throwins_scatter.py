"""
def_throwins_scatter.py

Three-panel scatter of opponent throw-ins vs Barcelona, coloured by win-back outcome.
Green = Barça won the ball back · Red = opponent kept possession.

Usage:
    python src/throwins/def_throwins/def_throwins_scatter.py
"""

from throwins_defense import (
    ZONE_ORDER,
    collect_data,
    plot_defense_scatter,
    plot_normalized_landing_heatmap,
    plot_combined_defense_heatmap,
    plot_combined_defense_heatmap_single,
    plot_combined_defense_heatmap_zone,
)
from def_throwins_positioning import collect_positions

if __name__ == "__main__":
    barca_df, _ = collect_data()

    n_won = int((barca_df["barca_won"] == True).sum())
    n_tot = len(barca_df)
    print(f"\nOpponent throw-ins vs Barcelona : {n_tot}")
    print(f"Barcelona won ball back         : {n_won}  ({n_won / n_tot * 100:.1f}%)" if n_tot else "")
    print("\nZone breakdown:")
    for zone in ZONE_ORDER:
        zdf = barca_df[barca_df["zone"] == zone]
        zn  = len(zdf)
        zw  = int((zdf["barca_won"] == True).sum())
        print(f"  {zone:<12} {zn:>4} throw-ins  {zw / zn * 100:.1f}% won back" if zn else f"  {zone:<12}    0")

    plot_defense_scatter(barca_df)
    plot_normalized_landing_heatmap(barca_df)

    print("\nCollecting SkillCorner positioning data ...")
    positions = collect_positions()
    plot_combined_defense_heatmap(barca_df, positions)
    plot_combined_defense_heatmap_single(barca_df, positions)
    plot_combined_defense_heatmap_zone(barca_df, positions, zone="Defensive")
