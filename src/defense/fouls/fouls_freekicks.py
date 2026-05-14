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

from fouls import all_barca_fouls, setpiece_sequence, setpiece_after_foul
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats import filters as f

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "fouls"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
_SB_ROOT  = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]

# Binning resolution — roughly 10-yard cells on a 120 × 80 pitch
BINS = (12, 8)

# OBV is summed over the opponent's events in the FK possession, capped
# at this many seconds — same convention as src/freekick_obv_map.py.
SEQUENCE_MAX_SECONDS = 10.0


def _event_seconds(e: dict) -> float:
    ts = e.get("timestamp", "")
    if ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(e.get("minute", 0)) * 60 + float(e.get("second", 0))


def _sequence_obv(events: list[dict], start_idx: int, team_sb: str) -> float:
    """Sum opponent OBV in the FK possession, within SEQUENCE_MAX_SECONDS."""
    start      = events[start_idx]
    possession = start.get("possession")
    period     = start.get("period")
    t0         = _event_seconds(start)
    total      = 0.0
    for e in events[start_idx:]:
        if e.get("period") != period or e.get("possession") != possession:
            break
        if _event_seconds(e) - t0 > SEQUENCE_MAX_SECONDS:
            break
        if e.get("team", {}).get("name", "") == team_sb:
            total += float(e.get("obv_total_net", 0.0) or 0.0)
    return total


def _event_value(e: dict) -> float:
    """OBV/xG value of a single event with the same fallback chain as
    barcelona_fk_defense_analysis.py: statsbomb_obv.value → shot.statsbomb_xg → 0.
    """
    sb_obv = e.get("statsbomb_obv")
    v = sb_obv.get("value") if isinstance(sb_obv, dict) else None
    if v is None:
        v = e.get("shot", {}).get("statsbomb_xg")
    if v is None:
        return 0.0
    return float(v)


def _sequence_value(events: list[dict], start_idx: int, team_sb: str) -> float:
    """Sum opponent OBV/xG (with fallback) over the FK possession, capped at
    SEQUENCE_MAX_SECONDS. Follows the action — every opp event in the
    possession contributes, not just the FK first-touch.
    """
    start      = events[start_idx]
    possession = start.get("possession")
    period     = start.get("period")
    t0         = _event_seconds(start)
    total      = 0.0
    for e in events[start_idx:]:
        if e.get("period") != period or e.get("possession") != possession:
            break
        if _event_seconds(e) - t0 > SEQUENCE_MAX_SECONDS:
            break
        if e.get("team", {}).get("name", "") == team_sb:
            total += _event_value(e)
    return total


# ── Data ──────────────────────────────────────────────────────────────────────

def _load_all_opponent_fks(
    data_dir: Path,
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """Return (xs, ys, xgs, obvs, vals) for every opponent FK against Barcelona.

    Coordinates are reflected into Barcelona's frame: barca_x = 120 − opp_x,
    so Barcelona's goal appears on the LEFT (x ≈ 0).
    Penalties are excluded; only FKs in Barcelona's defending half are kept.

    `xgs`  : sum of `shot.statsbomb_xg` over shots in the FK's possession.
    `obvs` : opponent's summed `obv_total_net` over the FK possession,
             capped at SEQUENCE_MAX_SECONDS.
    `vals` : per-FK summed OBV/xG over the opponent's FK possession
             (capped at SEQUENCE_MAX_SECONDS). Per-event fallback chain
             is `statsbomb_obv.value` → `shot.statsbomb_xg` → 0, matching
             src/defense/barcelona_fk_defense_analysis.py — but here the
             value is followed through the whole sequence, not just the
             first touch.
    """
    xs: list[float] = []
    ys: list[float] = []
    xgs: list[float] = []
    obvs: list[float] = []
    vals: list[float] = []

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            barca_sb = _team_in_match("Barcelona", row, events)
            if barca_sb is None:
                continue

            for idx, ev in enumerate(events):
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

                opp_x, opp_y = float(loc[0]), float(loc[1])
                barca_x = 120.0 - opp_x
                barca_y = 80.0  - opp_y

                if barca_x >= 60.0:
                    continue

                xg = sum(
                    float(e.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
                    for e in setpiece_sequence(ev, events)
                    if e.get("type", {}).get("id") == 16
                )
                obv = _sequence_obv(events, idx, team)
                v   = _sequence_value(events, idx, team)

                xs.append(barca_x)
                ys.append(barca_y)
                xgs.append(xg)
                obvs.append(obv)
                vals.append(v)

    return xs, ys, xgs, obvs, vals


def _all_foul_coords(data_dir: Path) -> tuple[list[float], list[float]]:
    """Barca foul locations in the defending half that led to an opponent FK.

    Penalty restarts and fouls with no detected restart (advantage,
    off-the-ball, end-of-half, etc.) are excluded.
    """
    xs: list[float] = []
    ys: list[float] = []

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            barca_sb = _team_in_match("Barcelona", row, events)
            if barca_sb is None:
                continue
            opp_sb = next(
                (e.get("team", {}).get("name", "") for e in events
                 if e.get("team", {}).get("name") and e["team"]["name"] != barca_sb),
                "",
            )
            if not opp_sb:
                continue

            for ev in events:
                if ev.get("type", {}).get("id") != 22:
                    continue
                if ev.get("team", {}).get("name", "") != barca_sb:
                    continue
                loc = ev.get("location")
                if not loc:
                    continue
                x, y = float(loc[0]), float(loc[1])
                if x >= 60.0:
                    continue

                restart = setpiece_after_foul(ev, events, opp_sb)
                if restart is None:
                    continue
                if not (f.is_fk_pass(restart) or f.is_fk_shot(restart)):
                    continue

                xs.append(x)
                ys.append(y)

    return xs, ys


# ── Shared data loader ────────────────────────────────────────────────────────

def load_data(data_dir: Path = None) -> tuple[
    list[float], list[float],
    list[float], list[float], list[float], list[float], list[float],
]:
    """Load all data once so multiple plot functions can share it."""
    print("Loading foul data …")
    all_xs, all_ys = _all_foul_coords(data_dir)
    print(f"  Total Barcelona fouls: {len(all_xs)}")

    print("Loading all opponent FK data …")
    fk_xs, fk_ys, xgs, obvs, vals = _load_all_opponent_fks(data_dir)
    print(f"  Opponent FKs (non-penalty): {len(fk_xs)}")
    print(f"  Total xG from opponent FKs:  {sum(xgs):.3f}")
    print(f"  Total OBV from opponent FKs: {sum(obvs):+.3f}")
    if vals:
        print(f"  Mean per-FK OBV/xG: {sum(vals) / len(vals):.4f}")

    return all_xs, all_ys, fk_xs, fk_ys, xgs, obvs, vals


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot_foul_xg_heatmaps(
    all_xs: list[float], all_ys: list[float],
    fk_xs:  list[float], fk_ys:  list[float],
    xgs: list[float], obvs: list[float], fk_vals: list[float],
    output_dir: Path,
) -> Path:
    """Three-panel side-by-side heatmap.

    Left  : mean per-FK OBV/xG by FK origin (OBV with xG fallback,
            same convention as barcelona_fk_defense_analysis.py)
    Centre: opponent OBV summed over FK possession (diverging)
    Right : Barca fouls (count) that gave away a FK
    """

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#bbbbbb",
        linewidth=1.2,
    )

    fig, axes = plt.subplots(1, 3, figsize=(20, 9))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(top=0.82, bottom=0.06, wspace=0.12, left=0.04, right=0.96)

    for ax in axes:
        pitch.draw(ax=ax)
        ax.set_xlim(-1, 61)

    # ── Left panel: foul count (green) ────────────────────────────────────────
    ax_left = axes[2]

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
        f"Fouls leading to opponent FK  (n = {len(all_xs)})",
        fontsize=12, fontweight="bold", pad=10, color="#111111",
    )

    # ── Left panel: per-FK mean xG by FK origin (red) ─────────────────────────
    ax_right = axes[0]  # variable kept for the rest of the function

    val_stats = pitch.bin_statistic(
        fk_xs, fk_ys,
        values=xgs,
        statistic="mean",
        bins=BINS,
    )
    val_grid   = val_stats["statistic"].copy().astype(float)
    val_counts = pitch.bin_statistic(
        fk_xs, fk_ys, statistic="count", bins=BINS,
    )["statistic"]
    val_grid = np.where(val_counts > 0, val_grid, np.nan)

    cmap_red = plt.get_cmap("Reds").copy()
    cmap_red.set_bad(color="white", alpha=0)

    pcm_right = pitch.heatmap(
        {**val_stats, "statistic": val_grid},
        ax=ax_right,
        cmap=cmap_red,
        edgecolors="none",
        alpha=0.85,
    )

    # Overlay each FK at its origin, sized by per-FK xG
    if fk_xs:
        max_v     = max((abs(v) for v in xgs), default=1.0) or 1.0
        dot_sizes = [max(15, abs(v) / max_v * 180) for v in xgs]
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
    cb_right.set_label("Mean xG per FK", fontsize=9)
    cb_right.ax.tick_params(labelsize=8)

    mean_xg = sum(xgs) / len(xgs) if xgs else 0.0
    ax_right.set_title(
        f"Opp FKs — mean xG by origin  (n = {len(fk_xs)} FKs, mean xG = {mean_xg:.3f})",
        fontsize=11, fontweight="bold", pad=10, color="#111111",
    )

    # ── Third panel: opponent OBV from FK possession (diverging) ──────────────
    ax_obv = axes[1]

    obv_stats = pitch.bin_statistic(
        fk_xs, fk_ys,
        values=obvs,
        statistic="sum",
        bins=BINS,
    )
    obv_grid = obv_stats["statistic"].copy().astype(float)
    # Blank truly empty cells (no FKs at all) but keep negative sums coloured
    obv_counts = pitch.bin_statistic(
        fk_xs, fk_ys, statistic="count", bins=BINS,
    )["statistic"]
    obv_grid = np.where(obv_counts > 0, obv_grid, np.nan)

    finite_obv = obv_grid[~np.isnan(obv_grid)]
    vmax_obv   = float(np.max(np.abs(finite_obv))) if finite_obv.size else 0.05
    vmax_obv   = max(vmax_obv, 0.01)

    cmap_obv = plt.get_cmap("RdYlGn_r").copy()
    cmap_obv.set_bad(color="white", alpha=0)
    norm_obv = mcolors.TwoSlopeNorm(vmin=-vmax_obv, vcenter=0, vmax=vmax_obv)

    pcm_obv = pitch.heatmap(
        {**obv_stats, "statistic": obv_grid},
        ax=ax_obv,
        cmap=cmap_obv,
        norm=norm_obv,
        edgecolors="none",
        alpha=0.85,
    )

    # Overlay individual FK dots, sized by |OBV|, coloured by sign
    if fk_xs:
        max_abs_obv = max((abs(o) for o in obvs), default=1.0) or 1.0
        dot_sizes   = [max(15, abs(o) / max_abs_obv * 180) for o in obvs]
        dot_colors  = ["#a10000" if o >= 0 else "#1a7a1a" for o in obvs]
        pitch.scatter(
            fk_xs, fk_ys,
            ax=ax_obv,
            s=dot_sizes,
            c=dot_colors,
            edgecolors="white",
            linewidths=0.4,
            alpha=0.55,
            zorder=4,
        )

    cb_obv = fig.colorbar(
        pcm_obv, ax=ax_obv,
        orientation="vertical",
        fraction=0.025, pad=0.02,
        shrink=0.75,
    )
    cb_obv.set_label("Opponent OBV (sum, red = gained / green = lost)", fontsize=9)
    cb_obv.ax.tick_params(labelsize=8)

    total_obv = sum(obvs)
    ax_obv.set_title(
        f"Opponent FKs — OBV by origin  (n = {len(fk_xs)}, total OBV = {total_obv:+.2f})",
        fontsize=12, fontweight="bold", pad=10, color="#111111",
    )

    # ── Shared labels ─────────────────────────────────────────────────────────
    fig.text(
        0.5, 0.96,
        "Barcelona fouls vs opponent free-kick xG & OBV",
        ha="center", va="top",
        fontsize=17, fontweight="bold", color="#111111",
    )
    fig.text(
        0.5, 0.91,
        "Defending half only (Barcelona goal on LEFT)  ·  left: mean xG per opponent FK (by origin)  ·  centre: opponent FK-possession OBV  ·  right: Barca fouls that gave away a FK  ·  penalties excluded",
        ha="center", va="top",
        fontsize=9.5, color="#555555",
    )

    out_path = output_dir / "foul_freekick_xg_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")
    plt.show()
    return out_path


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    all_xs, all_ys, fk_xs, fk_ys, xgs, obvs, fk_vals = load_data()
    plot_foul_xg_heatmaps(
        all_xs, all_ys, fk_xs, fk_ys, xgs, obvs, fk_vals, ASSETS_DIR,
    )
