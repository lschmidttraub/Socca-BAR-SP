"""Corner far-post share vs opponent top-6 height — single scatter plot.

For every Barcelona match in ``data/matches.csv`` this script computes

* Barcelona's top-6 outfield-player mean height,
* the opponent's top-6 outfield-player mean height,
* the share of Barcelona's corners in that match whose meaningful
  delivery landed in the "Far post" zone (StatsBomb coordinates
  ``x ≥ 114`` and ``y > 47`` on the 120×80 pitch),

and plots *far-post share* against *opponent height − Barcelona
height* as a scatter. A simple linear fit line is drawn through the
points and every match gets an abbreviated label (e.g. ``"NU"`` for
Newcastle United, ``"AM"`` for Atletico Madrid).

The plot mirrors the ``matchup_far_post_share_single.png`` figure in
the BAR-SP wiki's *Offense* chapter: Barcelona uses far-post deliveries
almost exclusively when the opponent is either unusually tall
(Newcastle, Slavia) or unusually short (København).

Usage
-----

    python matchup_far_post_share.py [team] [output.png]

Both arguments are optional: ``team`` defaults to ``Barcelona`` and
``output.png`` defaults to ``matchup_far_post_share.png`` in the
current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Make the sibling ``_loader`` module importable regardless of whether
# the script is invoked from the repo root or from this folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import abbr, collect_match_rows  # noqa: E402

DEFAULT_TEAM = "Barcelona"
DEFAULT_OUTPUT = Path("matchup_far_post_share.png")

# Repo-wide palette (matches src/stats/viz/style.py)
FOCUS_COLOR = "#a50026"    # Barcelona red — scatter points
FIT_COLOR = "#4575b4"      # blue — linear regression line
NEUTRAL_COLOR = "#878787"  # grey — x = 0 guide


def _plot(rows: list[dict], focus_team: str, output_path: Path) -> None:
    if not rows:
        raise SystemExit(f"No matches with lineup data found for {focus_team!r}.")

    fig, ax = plt.subplots(figsize=(8.4, 6.2))

    x = np.array([r["height_gap"] for r in rows], dtype=float)
    y = np.array([r["far_post_share"] for r in rows], dtype=float)

    ax.scatter(x, y, color=FOCUS_COLOR, s=68, alpha=0.85, zorder=3)

    slope = intercept = None
    if len(rows) >= 2 and np.ptp(x) > 0:
        slope, intercept = np.polyfit(x, y, deg=1)
        xs = np.linspace(float(np.min(x)), float(np.max(x)), 50)
        ax.plot(xs, slope * xs + intercept, color=FIT_COLOR, lw=2, zorder=2)

    ax.axvline(0.0, color=NEUTRAL_COLOR, lw=1.0, ls="--", zorder=1)

    for r in rows:
        ax.text(
            r["height_gap"] + 0.03,
            r["far_post_share"] + 0.003,
            abbr(r["label"]),
            fontsize=8.5,
        )

    ax.set_title(
        f"{focus_team} — Far-post share vs opponent height",
        fontsize=15, fontweight="bold", pad=10,
    )
    ax.set_xlabel("Opponent top-6 height minus Barcelona top-6 height (cm)")
    ax.set_ylabel("Far-post share")
    ax.grid(alpha=0.25, zorder=0)
    ax.set_axisbelow(True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if slope is not None:
        print(f"Linear fit: far_post_share = {slope:+.5f} * height_gap + {intercept:+.4f}")
    print(f"Plot saved to {output_path}")


def main(focus_team: str = DEFAULT_TEAM, output_path: Path = DEFAULT_OUTPUT) -> None:
    rows = collect_match_rows(focus_team)
    print(f"{focus_team} matches with lineup + corner data: {len(rows)}")
    print()
    print(
        f"  {'Opponent':22s} {'n_corn':>6s} {'far_post':>8s} "
        f"{'share':>7s} {'focus_h':>8s} {'opp_h':>7s} {'Δh':>7s}"
    )
    print("  " + "-" * 70)
    for r in rows:
        print(
            f"  {r['opponent'][:22]:22s} {r['n_corners']:6d} {r['far_post']:8d} "
            f"{r['far_post_share']:7.3f} {r['focus_top6']:8.1f} "
            f"{r['opp_top6']:7.1f} {r['height_gap']:+7.1f}"
        )
    print()
    _plot(rows, focus_team, output_path)


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    main(team, out)
