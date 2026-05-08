"""
fouls_freekicks.py

Two-panel heatmap of Barcelona fouls and the xG conceded from ALL
opponent free kicks (not just those that follow a Barcelona foul).

Left panel  — green heatmap: where Barcelona commits fouls (count per cell)
Right panel — red heatmap:   total xG from every opponent FK against
                              Barcelona, plotted at the FK origin

Both panels show the full pitch with Barcelona's own goal on the LEFT.

Coordinate note
---------------
Foul locations (left panel) are already in Barcelona's attacking frame
from `fouls.py` — own goal at x = 0, no transform needed.

Opponent FK locations (right panel) are in the OPPONENT's attacking
frame (they attack toward x = 120).  To put them in Barcelona's frame
(goal on left) the x-axis is reflected: barca_x = 120 − opp_x.

Usage
-----
    python src/defense/fouls/fouls_freekicks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from mplsoccer import Pitch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT     = PROJECT_ROOT / "src"
FOULS_DIR    = Path(__file__).parent

for _p in (str(SRC_ROOT), str(FOULS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fouls import all_barca_fouls, setpiece_sequence
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats import filters as f

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "fouls"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Binning resolution — roughly 5-yard cells on a 120 × 80 pitch
BINS = (24, 16)


# ── Data ──────────────────────────────────────────────────────────────────────

def _load_all_opponent_fks(
    data_dir: Path,
) -> tuple[list[float], list[float], list[float]]:
    """Return (xs, ys, xgs) for every opponent FK against Barcelona.

    Coordinates are reflected into Barcelona's frame: barca_x = 120 − opp_x,
    so Barcelona's goal appears on the LEFT (x ≈ 0).
    Penalties are excluded.
    """
    xs: list[float] = []
    ys: list[float] = []
    xgs: list[float] = []

    for row, events in iter_matches(data_dir):
        barca_sb = _team_in_match("Barcelona", row, events)
        if barca_sb is None:
            continue

        for ev in events:
            team = ev.get("team", {}).get("name", "")
            if team == barca_sb:
                continue
            if not (f.is_fk_pass(ev) or f.is_fk_shot(ev)):
                continue
            if f.is_penalty_shot(ev):
                continue
            loc = ev.get("location")
            if not loc:
                continue

            # Reflect x into Barcelona's attacking frame (own goal at x = 0)
            opp_x, opp_y = float(loc[0]), float(loc[1])
            barca_x = 120.0 - opp_x

            xg = sum(
                float(e.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                for e in setpiece_sequence(ev, events)
                if e.get("type", {}).get("id") == 16
            )

            xs.append(barca_x)
            ys.append(opp_y)
            xgs.append(xg)

    return xs, ys, xgs


def _all_foul_coords(data_dir: Path) -> tuple[list[float], list[float]]:
    """All Barcelona foul locations (including non-FK and penalty fouls)."""
    records = all_barca_fouls(data_dir)
    xs = [r["x"] for r in records if r["x"] is not None]
    ys = [r["y"] for r in records if r["y"] is not None]
    return xs, ys


# ── Shared data loader ────────────────────────────────────────────────────────

def load_data(data_dir: Path) -> tuple[
    list[float], list[float],          # all foul xs, ys
    list[float], list[float], list[float],  # fk xs, ys, xgs
]:
    """Load all data once so multiple plot functions can share it."""
    print("Loading foul data …")
    all_xs, all_ys = _all_foul_coords(data_dir)
    print(f"  Total Barcelona fouls: {len(all_xs)}")

    print("Loading all opponent FK data …")
    fk_xs, fk_ys, xgs = _load_all_opponent_fks(data_dir)
    print(f"  Opponent FKs (non-penalty): {len(fk_xs)}")
    print(f"  Total xG from opponent FKs: {sum(xgs):.3f}")

    return all_xs, all_ys, fk_xs, fk_ys, xgs


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot_foul_xg_heatmaps(
    all_xs: list[float], all_ys: list[float],
    fk_xs:  list[float], fk_ys:  list[float], xgs: list[float],
    output_dir: Path,
) -> Path:
    """Two-panel side-by-side heatmap (green fouls | red xG)."""

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#bbbbbb",
        linewidth=1.2,
    )

    fig, axes = plt.subplots(1, 2, figsize=(20, 7))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(top=0.84, bottom=0.08, wspace=0.06, left=0.04, right=0.94)

    for ax in axes:
        pitch.draw(ax=ax)

    # ── Left panel: foul count (green) ────────────────────────────────────────
    ax_left = axes[0]

    count_stats = pitch.bin_statistic(
        all_xs, all_ys,
        statistic="count",
        bins=BINS,
    )

    # Mask empty cells so they stay white
    count_grid = count_stats["statistic"].copy().astype(float)
    count_grid[count_grid == 0] = np.nan

    cmap_green = plt.get_cmap("Greens").copy()
    cmap_green.set_bad(color="white", alpha=0)

    pcm_left = pitch.heatmap(
        {**count_stats, "statistic": count_grid},
        ax=ax_left,
        cmap=cmap_green,
        edgecolors="none",
        alpha=0.85,
    )

    # Overlay individual foul dots
    pitch.scatter(
        all_xs, all_ys,
        ax=ax_left,
        s=12,
        color="#1a7a1a",
        edgecolors="white",
        linewidths=0.3,
        alpha=0.35,
        zorder=4,
    )

    cb_left = fig.colorbar(
        pcm_left, ax=ax_left,
        orientation="vertical",
        fraction=0.025, pad=0.02,
        shrink=0.75,
    )
    cb_left.set_label("Fouls (count)", fontsize=9)
    cb_left.ax.tick_params(labelsize=8)

    ax_left.set_title(
        f"Foul locations  (n = {len(all_xs)})",
        fontsize=13, fontweight="bold", pad=10, color="#111111",
    )

    # ── Right panel: xG from FK (red) ─────────────────────────────────────────
    ax_right = axes[1]

    xg_stats = pitch.bin_statistic(
        fk_xs, fk_ys,
        values=xgs,
        statistic="sum",
        bins=BINS,
    )

    xg_grid = xg_stats["statistic"].copy().astype(float)
    xg_grid[xg_grid == 0] = np.nan

    cmap_red = plt.get_cmap("Reds").copy()
    cmap_red.set_bad(color="white", alpha=0)

    pcm_right = pitch.heatmap(
        {**xg_stats, "statistic": xg_grid},
        ax=ax_right,
        cmap=cmap_red,
        edgecolors="none",
        alpha=0.85,
    )

    # Overlay individual FK foul dots, sized by xG
    if fk_xs:
        max_xg   = max(xgs) if max(xgs) > 0 else 1.0
        dot_sizes = [max(15, (xg / max_xg) * 180) for xg in xgs]
        pitch.scatter(
            fk_xs, fk_ys,
            ax=ax_right,
            s=dot_sizes,
            color="#a10000",
            edgecolors="white",
            linewidths=0.4,
            alpha=0.55,
            zorder=4,
        )

    cb_right = fig.colorbar(
        pcm_right, ax=ax_right,
        orientation="vertical",
        fraction=0.025, pad=0.02,
        shrink=0.75,
    )
    cb_right.set_label("Total xG conceded", fontsize=9)
    cb_right.ax.tick_params(labelsize=8)

    total_xg = sum(xgs)
    ax_right.set_title(
        f"All opponent FKs — xG by origin  (n = {len(fk_xs)}, total xG = {total_xg:.2f})",
        fontsize=13, fontweight="bold", pad=10, color="#111111",
    )

    # ── Shared labels ─────────────────────────────────────────────────────────
    fig.text(
        0.5, 0.93,
        "Barcelona fouls vs opponent free-kick xG",
        ha="center", va="top",
        fontsize=17, fontweight="bold", color="#111111",
    )
    fig.text(
        0.5, 0.875,
        "Barcelona goal on LEFT  ·  left: all Barca fouls  ·  right: ALL opponent FKs (dot size ∝ xG)  ·  penalties excluded",
        ha="center", va="top",
        fontsize=10, color="#555555",
    )

    out_path = output_dir / "foul_freekick_xg_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Saved → {out_path}")
    plt.show()
    return out_path


def plot_combined(
    all_xs: list[float], all_ys: list[float],
    fk_xs:  list[float], fk_ys:  list[float], xgs: list[float],
    output_dir: Path,
) -> Path:
    """Single pitch with green foul heatmap and red FK-xG heatmap overlaid.

    Cells that are both foul-dense and high-xG appear orange/brown, making
    the most dangerous areas immediately visible.
    """
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#bbbbbb",
        linewidth=1.2,
    )

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(top=0.84, bottom=0.06, left=0.10, right=0.90)
    pitch.draw(ax=ax)

    # ── Green layer: foul count ────────────────────────────────────────────────
    count_stats = pitch.bin_statistic(all_xs, all_ys, statistic="count", bins=BINS)
    count_grid  = count_stats["statistic"].copy().astype(float)
    count_grid[count_grid == 0] = np.nan

    cmap_green = plt.get_cmap("Greens").copy()
    cmap_green.set_bad(color="white", alpha=0)

    pcm_green = pitch.heatmap(
        {**count_stats, "statistic": count_grid},
        ax=ax, cmap=cmap_green, edgecolors="none", alpha=0.65,
    )

    # ── Red layer: opponent FK xG sum ─────────────────────────────────────────
    xg_stats = pitch.bin_statistic(fk_xs, fk_ys, values=xgs, statistic="sum", bins=BINS)
    xg_grid  = xg_stats["statistic"].copy().astype(float)
    xg_grid[xg_grid == 0] = np.nan

    cmap_red = plt.get_cmap("Reds").copy()
    cmap_red.set_bad(color="white", alpha=0)

    pcm_red = pitch.heatmap(
        {**xg_stats, "statistic": xg_grid},
        ax=ax, cmap=cmap_red, edgecolors="none", alpha=0.65,
    )

    # ── Scatter dots ──────────────────────────────────────────────────────────
    pitch.scatter(
        all_xs, all_ys,
        ax=ax,
        s=12,
        color="#1a7a1a",
        edgecolors="white",
        linewidths=0.3,
        alpha=0.35,
        zorder=4,
    )

    if fk_xs:
        max_xg    = max(xgs) if max(xgs) > 0 else 1.0
        dot_sizes = [max(15, (xg / max_xg) * 180) for xg in xgs]
        pitch.scatter(
            fk_xs, fk_ys,
            ax=ax,
            s=dot_sizes,
            color="#a10000",
            edgecolors="white",
            linewidths=0.4,
            alpha=0.55,
            zorder=5,
        )

    # ── Colorbars ─────────────────────────────────────────────────────────────
    cb_green = fig.colorbar(
        pcm_green, ax=ax,
        orientation="vertical", fraction=0.022, pad=0.10, shrink=0.7,
        location="left",
    )
    cb_green.set_label("Fouls (count)", fontsize=9, color="#1a7a1a")
    cb_green.ax.tick_params(labelsize=8)

    cb_red = fig.colorbar(
        pcm_red, ax=ax,
        orientation="vertical", fraction=0.022, pad=0.02, shrink=0.7,
    )
    cb_red.set_label("xG conceded (sum)", fontsize=9, color="#a10000")
    cb_red.ax.tick_params(labelsize=8)

    # ── Labels ────────────────────────────────────────────────────────────────
    fig.text(
        0.5, 0.94,
        "Barcelona fouls & opponent free-kick xG — combined",
        ha="center", va="top",
        fontsize=16, fontweight="bold", color="#111111",
    )
    fig.text(
        0.5, 0.885,
        "Green = foul density  ·  Red = opponent FK xG  ·  "
        "Orange/brown = overlap (many fouls AND high xG)  ·  Barcelona goal on LEFT",
        ha="center", va="top",
        fontsize=9.5, color="#555555",
    )

    out_path = output_dir / "foul_freekick_combined.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Saved → {out_path}")
    plt.show()
    return out_path


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    DATA = PROJECT_ROOT / "data" / "statsbomb"
    all_xs, all_ys, fk_xs, fk_ys, xgs = load_data(DATA)
    plot_foul_xg_heatmaps(all_xs, all_ys, fk_xs, fk_ys, xgs, ASSETS_DIR)
    plot_combined(all_xs, all_ys, fk_xs, fk_ys, xgs, ASSETS_DIR)
