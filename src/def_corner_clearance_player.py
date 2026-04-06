"""
def_corner_clearance_player.py

Counts which Barcelona players made clearances during defending corner sequences
and plots the results as a bar chart.

Usage:
    python src/def_corner_clearance_player.py
"""

import matplotlib.pyplot as plt

import numpy as np

from defending_corners import (
    BARCELONA,
    ASSETS_DIR,
    TYPE_CLEARANCE,
    build_pairs,
    corner_sequence,
    corner_side,
)


# ── Data helpers ──────────────────────────────────────────────────────────────

def get_clearance_players(corner_ev: dict, events: list) -> list[str]:
    """Return names of all Barcelona players who made a clearance in this corner sequence."""
    players = []
    for ev in corner_sequence(corner_ev, events):
        if (
            ev.get("type", {}).get("id") == TYPE_CLEARANCE
            and BARCELONA.casefold() in ev.get("team", {}).get("name", "").casefold()
        ):
            players.append(ev.get("player", {}).get("name", "Unknown"))
    return players


def count_clearances(pairs: list[tuple]) -> dict[str, int]:
    """Count clearances per player across all (corner, events) pairs."""
    counts: dict[str, int] = {}
    for corner, events in pairs:
        for player in get_clearance_players(corner, events):
            counts[player] = counts.get(player, 0) + 1
    return counts


def count_clearances_by_side(pairs: list[tuple]) -> dict[str, dict[str, int]]:
    """Count clearances per player split by corner side (from Barcelona's perspective).
    Returns {player: {"Left": n, "Right": n}}."""
    counts: dict[str, dict[str, int]] = {}
    for corner, events in pairs:
        side = corner_side(corner)
        for player in get_clearance_players(corner, events):
            if player not in counts:
                counts[player] = {"Left": 0, "Right": 0}
            counts[player][side] = counts[player].get(side, 0) + 1
    return counts


# ── Plotting ──────────────────────────────────────────────────────────────────


def plot_clearances_by_player_and_side(counts_by_side: dict[str, dict[str, int]], save: bool = True) -> None:
    """Stacked bar chart of clearances per player split by left/right corner side."""
    labels = sorted(counts_by_side, key=lambda p: sum(counts_by_side[p].values()), reverse=True)
    left_vals  = [counts_by_side[p].get("Left",  0) for p in labels]
    right_vals = [counts_by_side[p].get("Right", 0) for p in labels]

    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x, left_vals,  label="Left",  color="steelblue",  edgecolor="white")
    ax.bar(x, right_vals, label="Right", color="darkorange", edgecolor="white",
           bottom=left_vals)

    for i, (l, r) in enumerate(zip(left_vals, right_vals)):
        total = l + r
        if l > 0:
            ax.text(i, l / 2, str(l), ha="center", va="center", fontsize=8, color="white")
        if r > 0:
            ax.text(i, l + r / 2, str(r), ha="center", va="center", fontsize=8, color="white")
        ax.text(i, total + 0.1, str(total), ha="center", va="bottom", fontsize=9)

    ax.set_ylabel("Clearances")
    ax.set_title("Clearances by Player and Corner Side – Barcelona (Left/Right from Barcelona's perspective)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=40, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = ASSETS_DIR / "def_corner_clearance_player.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pairs = build_pairs(BARCELONA)
    counts_by_side = count_clearances_by_side(pairs)

    total = sum(sum(s.values()) for s in counts_by_side.values())
    print(f"\nBarcelona defending corners: {len(pairs)}")
    print(f"Total clearances: {total}")
    print("\nClearances per player:")
    for player, sides in sorted(counts_by_side.items(), key=lambda x: sum(x[1].values()), reverse=True):
        print(f"  {player:<35} L={sides.get('Left', 0)}  R={sides.get('Right', 0)}")

    plot_clearances_by_player_and_side(counts_by_side)
