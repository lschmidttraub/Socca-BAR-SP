"""Free-kick OBV pitch maps — full pitch, attack normalised left→right.

StatsBomb already orients every event so the team in possession attacks
toward x=120. The only extra normalisation applied here is lateral (y):
flip around y=40 so the team always plays on the bottom half of the pitch.

Figure (2 subplots):
  Left:  Barcelona FK origins coloured by OBV delta (green=positive,
         red=negative), sized by magnitude. Full pitch, both halves.
  Right: 10x10-yard grid of mean OBV delta for all CL teams, diverging
         colour (green=positive, red=negative); cells with n<2 left blank.

Output: assets/freekick_obv_map.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from mplsoccer import Pitch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT     = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import POSITIVE_COLOR, NEGATIVE_COLOR, apply_theme, save_fig

ASSETS_ROOT = PROJECT_ROOT / "assets"
DATA        = PROJECT_ROOT / "data" / "statsbomb"
TEAM        = "Barcelona"

GOAL_COLOR = POSITIVE_COLOR   # green — OBV gained
MISS_COLOR = NEGATIVE_COLOR   # red   — OBV lost

SEQUENCE_MAX_SECONDS = 20.0

# Full-pitch grid (StatsBomb 120 × 80 yards, 10-yard bins)
X_BINS = np.arange(0, 121, 10)   # 12 columns × 8 rows = 96 cells
Y_BINS = np.arange(0,  81, 10)
MIN_N  = 2                        # min FKs per cell to show colour


# ── normalisation ─────────────────────────────────────────────────────
# StatsBomb already orients every event so the team in possession attacks
# toward x=120. No y-flip needed — show raw positions so FKs appear on
# both sides of the pitch as they actually occurred.

def _normalise(loc: list) -> tuple[float, float]:
    return float(loc[0]), float(loc[1])


# ── OBV helpers ───────────────────────────────────────────────────────

def _event_seconds(e: dict) -> float:
    ts = e.get("timestamp", "")
    if ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(e.get("minute", 0)) * 60 + float(e.get("second", 0))


def _sequence_obv(events: list[dict], start_idx: int, team_sb: str) -> float:
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
        if f.by_team(e, team_sb):
            total += float(e.get("obv_total_net", 0.0) or 0.0)
    return total


def _is_fk_event(e: dict) -> bool:
    return f.is_fk_pass(e) or f.is_fk_shot(e)


# ── data collection ───────────────────────────────────────────────────

def _collect_barca(data_dir: Path) -> list[dict]:
    results: list[dict] = []
    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(TEAM, row, events)
        if sb_name is None:
            continue
        for idx, event in enumerate(events):
            if not (_is_fk_event(event) and f.by_team(event, sb_name)):
                continue
            loc = event.get("location")
            if not loc:
                continue
            nx, ny = _normalise(loc)
            results.append({
                "fk_x":      nx,
                "fk_y":      ny,
                "total_obv": _sequence_obv(events, idx, sb_name),
            })
    return results


def _collect_all(data_dir: Path) -> list[dict]:
    results: list[dict] = []
    for row, events in iter_matches(data_dir):
        team_names = {e.get("team", {}).get("name", "")
                      for e in events if e.get("team", {}).get("name")}
        for sb_name in team_names:
            for idx, event in enumerate(events):
                if not (_is_fk_event(event) and f.by_team(event, sb_name)):
                    continue
                loc = event.get("location")
                if not loc:
                    continue
                nx, ny = _normalise(loc)
                results.append({
                    "fk_x":      nx,
                    "fk_y":      ny,
                    "total_obv": _sequence_obv(events, idx, sb_name),
                    "team":      sb_name,
                })
    return results


# ── scatter ───────────────────────────────────────────────────────────

def _scatter_obv(ax: plt.Axes, pitch: Pitch, sequences: list[dict]) -> None:
    vals  = [abs(s["total_obv"]) for s in sequences]
    scale = max(vals) if vals else 1.0
    for s in sequences:
        x, y, obv = s["fk_x"], s["fk_y"], s["total_obv"]
        color = GOAL_COLOR if obv >= 0 else MISS_COLOR
        size  = max(30, abs(obv) / scale * 320)
        pitch.scatter(x, y, ax=ax, s=size, color=color,
                      edgecolors="white", linewidth=0.6, alpha=0.85, zorder=4)


# ── grid heatmap ──────────────────────────────────────────────────────

def _build_grid(sequences: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    n_x, n_y = len(X_BINS) - 1, len(Y_BINS) - 1
    totals = np.zeros((n_y, n_x))
    counts = np.zeros((n_y, n_x), dtype=int)
    for s in sequences:
        x, y = s["fk_x"], s["fk_y"]
        xi = int(np.clip(x // 10, 0, n_x - 1))
        yi = int(np.clip(y // 10, 0, n_y - 1))
        totals[yi, xi] += s["total_obv"]
        counts[yi, xi] += 1
    means = np.where(counts >= MIN_N, totals / np.maximum(counts, 1), np.nan)
    return means, counts


def _draw_grid(ax: plt.Axes, means: np.ndarray, counts: np.ndarray) -> None:
    finite = means[~np.isnan(means)]
    vmax   = float(np.max(np.abs(finite))) if finite.size else 0.05
    vmax   = max(vmax, 0.01)
    cmap   = plt.get_cmap("RdYlGn")
    norm   = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    n_y, n_x = means.shape
    for yi in range(n_y):
        for xi in range(n_x):
            if np.isnan(means[yi, xi]):
                continue
            x0, x1 = X_BINS[xi], X_BINS[xi + 1]
            y0, y1 = Y_BINS[yi], Y_BINS[yi + 1]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

            rgba = cmap(norm(means[yi, xi]))
            ax.fill_between([x0, x1], y0, y1, color=rgba, alpha=0.75, zorder=2)
            ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0],
                    color="white", lw=0.4, alpha=0.45, zorder=3)

            n, m = counts[yi, xi], means[yi, xi]
            sign = "+" if m >= 0 else ""
            text_color = "white" if abs(norm(m) - 0.5) > 0.22 else "#222222"
            ax.text(cx, cy + 1.8,  f"n={n}",          ha="center", va="center",
                    fontsize=5.5, color=text_color, zorder=5)
            ax.text(cx, cy - 2.2,  f"{sign}{m:.3f}",  ha="center", va="center",
                    fontsize=5.5, color=text_color, fontweight="bold", zorder=5)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cb = plt.colorbar(sm, ax=ax, orientation="vertical", fraction=0.022, pad=0.02)
    cb.set_label("Mean OBV delta", fontsize=8)
    cb.ax.tick_params(labelsize=7)


# ── figure ────────────────────────────────────────────────────────────

def _build_figure(barca: list[dict], all_seqs: list[dict]) -> plt.Figure:
    pitch = Pitch(pitch_type="statsbomb", half=False,
                  pitch_color="white", line_color="#c7d5cc", linewidth=1.4)
    fig, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(20, 7))
    fig.subplots_adjust(top=0.82, bottom=0.08, wspace=0.10)
    for ax in (ax_l, ax_r):
        pitch.draw(ax=ax)

    # — Left: Barcelona scatter —
    _scatter_obv(ax_l, pitch, barca)
    n_pos = sum(1 for s in barca if s["total_obv"] >= 0)
    n_neg = sum(1 for s in barca if s["total_obv"] < 0)
    ax_l.set_title(
        f"Barcelona  n={len(barca)}  ({n_pos} positive / {n_neg} negative OBV)",
        fontsize=11, fontweight="bold", pad=8,
    )
    ax_l.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor=GOAL_COLOR,
               markersize=9,  label="OBV gained"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=MISS_COLOR,
               markersize=9,  label="OBV lost"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#999999",
               markersize=5,  label="small magnitude"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#999999",
               markersize=12, label="large magnitude"),
    ], loc="lower left", fontsize=8, frameon=True, framealpha=0.88, ncol=2)

    # — Right: grid heatmap (all CL teams, normalised) —
    means, counts = _build_grid(all_seqs)
    _draw_grid(ax_r, means, counts)
    n_cells = int(np.sum(~np.isnan(means)))
    ax_r.set_title(
        f"All CL teams — mean OBV per 10x10 yd zone  "
        f"(n={len(all_seqs)} FK events, {n_cells} cells with n>={MIN_N})",
        fontsize=10, fontweight="bold", pad=8,
    )
    ax_r.legend(handles=[
        Patch(color=plt.get_cmap("RdYlGn")(0.85), label="Positive avg OBV"),
        Patch(color=plt.get_cmap("RdYlGn")(0.15), label="Negative avg OBV"),
        Patch(color="#cccccc", alpha=0.5,           label=f"Blank = n < {MIN_N}"),
    ], loc="lower left", fontsize=8, frameon=True, framealpha=0.88)

    fig.text(0.5, 0.96,
             "Free-kick OBV delta — full pitch  (attack left to right)",
             ha="center", va="top", fontsize=15, fontweight="bold", color="#111111")
    fig.text(0.5, 0.91,
             "StatsBomb normalises each event so the team always attacks right  "
             "|  OBV summed over FK possession sequence (up to 20 s)",
             ha="center", va="top", fontsize=9, color="#555555")
    return fig


# ── entry point ───────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_ROOT) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting Barcelona FK sequences ...")
    barca = _collect_barca(data_dir)
    print(f"  {len(barca)} FK events")

    print("Collecting all-team FK sequences ...")
    all_seqs = _collect_all(data_dir)
    print(f"  {len(all_seqs)} FK events")

    print("Building figure ...")
    fig = _build_figure(barca, all_seqs)
    out = output_dir / "freekick_obv_map.png"
    save_fig(fig, out, tight=False)
    print(f"  Saved: {out}")
    print("Done.")


if __name__ == "__main__":
    run()