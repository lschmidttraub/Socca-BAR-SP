"""
throwins_scatter.py

Full-pitch arrow scatter of Barcelona throw-ins, coloured by zone.
Dots and arrows are green (possession won) or red (possession lost).

Barcelona attacks left → right (x: 0 → 120):
    Defensive zone  x ≤ 40   (own half, near goal)
    Middle zone     40 < x ≤ 80
    Attacking zone  x > 80   (opponent's half)

Each arrow runs from the throw-in location to where the ball landed.

Usage:
    python src/throwins/throwins_scatter.py
"""

import matplotlib.pyplot as plt
import pandas as pd
from mplsoccer import Pitch

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    build_records,
)

POSSESSION_COLORS = {
    True:  "#2dc653",   # green  — won
    False: "#e63946",   # red    — lost
    None:  "#adb5bd",   # grey   — indeterminate
}

ZONE_ORDER = ["Defensive", "Middle", "Attacking"]


def plot_zone_scatter(df: pd.DataFrame, save: bool = True) -> None:
    """Full-pitch arrow scatter of Barcelona throw-ins by zone, coloured by possession outcome."""
    df = df.dropna(subset=["x", "y", "end_x", "end_y"])

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#444444",
    )

    fig, axes = pitch.draw(nrows=1, ncols=3, figsize=(20, 7))

    for ax, zone in zip(axes, ZONE_ORDER):
        zone_df = df[df["zone"] == zone]

        for _, row in zone_df.iterrows():
            color = POSSESSION_COLORS.get(row["possession_won"], "#adb5bd")
            ax.annotate(
                "",
                xy=(row["end_x"], row["end_y"]),
                xytext=(row["x"], row["y"]),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=color,
                    lw=0.8,
                    alpha=0.6,
                    mutation_scale=8,
                ),
                zorder=2,
            )

        for won, label in [(True, "Won"), (False, "Lost"), (None, "Unclear")]:
            sub = zone_df[zone_df["possession_won"] == won] if won is not None \
                  else zone_df[zone_df["possession_won"].isna()]
            if sub.empty:
                continue
            pitch.scatter(
                sub["end_x"], sub["end_y"],
                ax=ax,
                color=POSSESSION_COLORS[won],
                edgecolors="white",
                linewidths=0.5,
                s=40,
                label=label,
                zorder=3,
            )

        n_won  = int((zone_df["possession_won"] == True).sum())
        n_lost = int((zone_df["possession_won"] == False).sum())
        n_tot  = len(zone_df)
        pct    = f"{n_won / n_tot * 100:.0f}%" if n_tot else "—"

        ax.set_title(
            f"{zone} zone  (N={n_tot})\n"
            f"Won {n_won} · Lost {n_lost} · {pct} retention",
            fontsize=10,
            pad=8,
            color="black",
        )
        ax.legend(loc="upper left", bbox_to_anchor=(0, 1), fontsize=8, framealpha=0.7)

    fig.suptitle(
        "Barcelona Throw-ins — Possession Outcome by Zone\n"
        "Green = won · Red = lost  ·  arrow tip = ball landing spot",
        fontsize=12,
        y=1.02,
        color="black",
    )
    fig.set_facecolor("white")
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = THROWINS_ASSETS_DIR / "throwins_zone_scatter.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


if __name__ == "__main__":
    df = build_records(BARCELONA)

    print(f"\nBarcelona throw-ins with location data: "
          f"{len(df.dropna(subset=['x', 'y', 'end_x', 'end_y']))}")
    print("\nZone breakdown:")
    print(df["zone"].value_counts().to_string())
    print("\nPossession outcome breakdown:")
    print(df["possession_won"].value_counts(dropna=False).to_string())

    plot_zone_scatter(df)
