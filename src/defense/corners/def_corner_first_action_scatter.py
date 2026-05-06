"""
def_corner_first_action_scatter.py

Scatter plot of first-action locations for all Barcelona defending corners,
shown on a half-pitch. Dots are coloured by corner outcome; left/right corners
are separated naturally by their y-coordinate.

Usage:
    python src/def_corner_first_action_scatter.py
"""

import matplotlib.pyplot as plt
from mplsoccer import Pitch

from defending_corners import (
    BARCELONA,
    DEF_CORNER_ASSETS_DIR,
    build_pairs,
    classify_corner_outcome,
    corner_side,
    first_sequence_action,
    is_aerial,
    normalize_to_right,
)

OUTCOME_COLORS = {
    "Goal":         "#e63946",
    "Shot":         "#f4a261",
    "Goalkeeper":   "#9b5de5",
    "Clearance":    "#4895ef",
    "Interception": "#2dc653",
    "Block":        "#00b4d8",
    "Foul":         "#f9c74f",
    "Short Corner": "#adb5bd",
    "Out of Play":  "#6c757d",
    "Other":        "#dee2e6",
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def collect_scatter_data(pairs: list[tuple]) -> list[dict]:
    """Return one record per defending corner with normalised first-action location,
    outcome, and corner side."""
    records = []
    for corner, events in pairs:
        action = first_sequence_action(corner, events)
        if action is None:
            continue
        corner_loc = corner.get("location")
        action_loc = action.get("location")
        if corner_loc is None or action_loc is None:
            continue
        norm_action = normalize_to_right(action_loc, corner_loc)
        norm_corner = normalize_to_right(corner_loc, corner_loc)
        records.append({
            "x":        norm_action[0],
            "y":        norm_action[1],
            "corner_x": norm_corner[0],
            "corner_y": norm_corner[1],
            "outcome":  classify_corner_outcome(corner, events),
            "side":     corner_side(corner),
            "aerial":   is_aerial(action),
        })
    return records


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_scatter(records: list[dict], save: bool = True) -> None:
    """Half-pitch scatter of first-action locations, coloured by outcome,
    with thin arrows from the corner flag to each first-action point."""
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="#1a1a2e",
        line_color="#aaaaaa",
    )
    fig, ax = pitch.draw(figsize=(14, 8))

    MARKERS = {True: "D", False: "o"}   # aerial = diamond, ground = circle

    plotted_outcomes = set()
    for record in records:
        outcome = record["outcome"]
        color = OUTCOME_COLORS.get(outcome, "#ffffff")
        marker = MARKERS[record["aerial"]]

        # Arrow from corner flag to first action
        ax.annotate(
            "",
            xy=(record["x"], record["y"]),
            xytext=(record["corner_x"], record["corner_y"]),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=0.8,
                alpha=0.5,
                mutation_scale=8,
            ),
            zorder=2,
        )

        label = outcome if outcome not in plotted_outcomes else "_nolegend_"
        plotted_outcomes.add(outcome)
        pitch.scatter(
            record["x"], record["y"],
            ax=ax,
            color=color,
            edgecolors="white",
            linewidths=0.5,
            s=70,
            marker=marker,
            label=label,
            zorder=3,
        )

    # Outcome legend (colour)
    outcome_legend = ax.legend(
        title="Outcome",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        framealpha=0.7,
        fontsize=9,
        title_fontsize=10,
    )
    ax.add_artist(outcome_legend)

    # Aerial legend (marker shape)
    from matplotlib.lines import Line2D
    aerial_handles = [
        Line2D([0], [0], marker="D", color="w", markerfacecolor="grey", markersize=8, label="Aerial (head)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="grey", markersize=8, label="Ground (foot)"),
    ]
    ax.legend(
        handles=aerial_handles,
        title="Body part",
        loc="lower left",
        bbox_to_anchor=(1.01, 0.0),
        framealpha=0.7,
        fontsize=9,
        title_fontsize=10,
    )
    ax.set_title(
        f"First Action Location – Barcelona Defending Corners (N={len(records)})\n"
        "Left side of pitch = Barcelona's goal end   ·   top/bottom split = corner side",
        color="white",
        fontsize=11,
        pad=12,
    )
    fig.set_facecolor("#1a1a2e")
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "def_corner_first_action_scatter.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pairs = build_pairs(BARCELONA)
    records = collect_scatter_data(pairs)
    print(f"\nBarcelona defending corners: {len(pairs)}")
    print(f"Corners with first-action location: {len(records)}")
    plot_scatter(records)
