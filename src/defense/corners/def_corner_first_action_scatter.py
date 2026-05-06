"""
def_corner_first_action_scatter.py

Scatter plot of first-action locations for all Barcelona defending corners.
The pitch shows the left half only — Barcelona's goal is at x=0 (left).
Each arrow runs from the corner flag to the first-action point.
Dots are coloured by corner outcome and shaped by body part (aerial vs ground).

Left corners  (y < 40) appear at the bottom of the goal end.
Right corners (y ≥ 40) appear at the top of the goal end.

Usage:
    python src/defense/corners/def_corner_first_action_scatter.py
"""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch

from defending_corners import (
    BARCELONA,
    DEF_CORNER_ASSETS_DIR,
    build_pairs,
    classify_corner_outcome,
    corner_side,
    first_touch_action,
    is_aerial,
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

_PITCH_LENGTH = 120  # StatsBomb pitch length in pitch units


# ── Coordinate normalisation ──────────────────────────────────────────────────

def _to_barca_coords(loc: list, event_team: str) -> list:
    """Convert a StatsBomb location to Barcelona's coordinate system (goal at x=0).

    StatsBomb normalises each team's events so that team always attacks
    left-to-right (x: 0→120). The corner kick (by the opponent) and a
    Barcelona clearance therefore live in DIFFERENT coordinate systems even
    though they appear in the same match file. Flip x for opponent events;
    leave Barcelona events unchanged.
    """
    x, y = loc[0], loc[1]
    if BARCELONA.casefold() not in event_team.casefold():
        x = _PITCH_LENGTH - x
    return [x, y]


# ── Data collection ───────────────────────────────────────────────────────────

def collect_scatter_data(pairs: list[tuple]) -> list[dict]:
    """Return one record per defending corner with normalised first-action location."""
    records = []
    for corner, events in pairs:
        action = first_touch_action(corner, events)
        if action is None:
            continue
        corner_loc = corner.get("location")
        action_loc = action.get("location")
        if corner_loc is None or action_loc is None:
            continue

        corner_team = corner.get("team", {}).get("name", "")
        action_team = action.get("team", {}).get("name", "")

        norm_corner = _to_barca_coords(corner_loc, corner_team)
        norm_action = _to_barca_coords(action_loc, action_team)

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
    """Half-pitch scatter of first-action locations, coloured by outcome."""
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#444444",
    )
    fig, ax = pitch.draw(figsize=(10, 8))
    ax.set_xlim(-2, 62)  # left half only — Barcelona's goal at x=0

    MARKERS = {True: "D", False: "o"}  # aerial = diamond, ground = circle
    plotted_outcomes: set[str] = set()

    for record in records:
        outcome = record["outcome"]
        color   = OUTCOME_COLORS.get(outcome, "#ffffff")
        marker  = MARKERS[record["aerial"]]

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

    outcome_legend = ax.legend(
        title="Outcome",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        framealpha=0.7,
        fontsize=9,
        title_fontsize=10,
    )
    ax.add_artist(outcome_legend)

    ax.legend(
        handles=[
            Line2D([0], [0], marker="D", color="w", markerfacecolor="grey",
                   markersize=8, label="Aerial (head)"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="grey",
                   markersize=8, label="Ground (foot)"),
        ],
        title="Body part",
        loc="lower left",
        bbox_to_anchor=(1.01, 0.0),
        framealpha=0.7,
        fontsize=9,
        title_fontsize=10,
    )

    ax.set_title(
        f"First Action Location – Barcelona Defending Corners (N={len(records)})\n"
        "Barcelona's goal on the left  ·  bottom = left corner (y<40), top = right corner (y≥40)",
        color="black",
        fontsize=11,
        pad=12,
    )
    fig.set_facecolor("white")
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
