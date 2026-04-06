"""
def_corner_first_action_dist.py

Analyses the distance from the corner flag to the first action in each
Barcelona defending corner sequence and plots the results.

Usage:
    python src/def_corner_first_action_dist.py
"""

import matplotlib.pyplot as plt
import numpy as np

from defending_corners import (
    BARCELONA,
    DEF_CORNER_ASSETS_DIR,
    build_pairs,
    corner_side,
    corner_to_first_action_distance,
)


# ── Data helpers ──────────────────────────────────────────────────────────────

def collect_distances(pairs: list[tuple]) -> list[float]:
    """Return a list of corner-flag-to-first-action distances for all pairs."""
    return [
        d for corner, events in pairs
        if (d := corner_to_first_action_distance(corner, events)) is not None
    ]


def collect_distances_by_side(pairs: list[tuple]) -> dict[str, list[float]]:
    """Return distances split by corner side (Left / Right)."""
    result: dict[str, list[float]] = {"Left": [], "Right": []}
    for corner, events in pairs:
        d = corner_to_first_action_distance(corner, events)
        if d is not None:
            side = corner_side(corner)
            if side in result:
                result[side].append(d)
    return result


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_distance_histogram(distances: list[float], save: bool = True) -> None:
    """Histogram of distances from corner flag to first action."""
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(distances, bins=20, color="steelblue", edgecolor="white")
    ax.axvline(np.mean(distances), color="darkorange", linestyle="--",
               label=f"Mean: {np.mean(distances):.1f} m")
    ax.axvline(np.median(distances), color="gold", linestyle="--",
               label=f"Median: {np.median(distances):.1f} m")
    ax.set_xlabel("Distance from corner flag to first action (m)")
    ax.set_ylabel("Count")
    ax.set_title("Distance to First Action – Barcelona Defending Corners")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "def_corner_first_action_dist.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


def plot_distance_by_side(distances_by_side: dict[str, list[float]], save: bool = True) -> None:
    """Overlapping histograms of distances split by corner side."""
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = {"Left": "steelblue", "Right": "darkorange"}
    bins = np.linspace(0, max(max(v) for v in distances_by_side.values() if v), 21)

    for side, dists in distances_by_side.items():
        if not dists:
            continue
        ax.hist(dists, bins=bins, alpha=0.6, label=f"{side} (N={len(dists)}, mean={np.mean(dists):.1f} m)",
                color=colors[side], edgecolor="white")

    ax.set_xlabel("Distance from corner flag to first action (m)")
    ax.set_ylabel("Count")
    ax.set_title("Distance to First Action by Corner Side – Barcelona Defending Corners")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "def_corner_first_action_dist_by_side.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pairs = build_pairs(BARCELONA)
    distances = collect_distances(pairs)
    distances_by_side = collect_distances_by_side(pairs)

    print(f"\nBarcelona defending corners: {len(pairs)}")
    print(f"Corners with measurable first action: {len(distances)}")
    print(f"Mean distance:   {np.mean(distances):.1f} m")
    print(f"Median distance: {np.median(distances):.1f} m")
    for side, dists in distances_by_side.items():
        print(f"  {side}: N={len(dists)}, mean={np.mean(dists):.1f} m, median={np.median(dists):.1f} m")

    plot_distance_histogram(distances)
    plot_distance_by_side(distances_by_side)
