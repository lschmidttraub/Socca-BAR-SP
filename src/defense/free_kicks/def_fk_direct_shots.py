"""
def_fk_direct_shots.py

Direct free-kick shots conceded by Barcelona.  Single half-pitch with:

  - shot origin scattered by xG (size) and outcome (colour)
  - distance and xG annotated next to each marker
  - a side-bar table summarising the shots

Output:
  def_fk_direct_shots.png

Usage:
    python src/defense/free_kicks/def_fk_direct_shots.py
"""

import math

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch

from defending_free_kicks import (
    BARCELONA,
    DEF_FK_ASSETS_DIR,
    GOAL_X,
    GOAL_Y,
    build_pairs,
    is_fk_shot,
    normalize_to_right,
)


SHOT_OUTCOME_COLOR = {
    "Goal":      "#b30000",
    "Saved":     "#4895ef",
    "Off T":     "#f4a261",
    "Wayward":   "#f4a261",
    "Blocked":   "#9b5de5",
    "Post":      "#e9c46a",
    "Saved Off Target": "#4895ef",
    "Saved To Post":    "#e9c46a",
}


# ── Data shaping ─────────────────────────────────────────────────────────────

def collect_direct_shots(pairs: list[tuple]) -> list[dict]:
    """One record per direct FK shot conceded."""
    out: list[dict] = []
    for fk, _events in pairs:
        if not is_fk_shot(fk):
            continue
        loc = fk.get("location")
        if not loc:
            continue
        norm = normalize_to_right(loc, loc)
        shot = fk.get("shot", {})
        outcome = shot.get("outcome", {}).get("name", "Unknown")
        xg = float(shot.get("statsbomb_xg", 0.0) or 0.0)
        dist = math.hypot(GOAL_X - norm[0], GOAL_Y - norm[1])
        out.append({
            "x": norm[0],
            "y": norm[1],
            "xg": xg,
            "outcome": outcome,
            "distance": dist,
            "team":    fk.get("team", {}).get("name", ""),
            "player":  fk.get("player", {}).get("name", ""),
        })
    return out


# ── Plot ─────────────────────────────────────────────────────────────────────

def _marker_size(xg: float) -> float:
    """Scale dot size with xG (clipped so very low-xG shots stay visible)."""
    return 60.0 + 1500.0 * max(xg, 0.005)


def plot_direct_shots(records: list[dict], save: bool = True) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="#1a1a2e",
        line_color="#aaaaaa",
    )
    fig, ax = pitch.draw(figsize=(13, 8))

    if not records:
        ax.set_title(
            "No direct FK shots conceded — nothing to plot",
            color="white", fontsize=12, pad=10,
        )
        fig.set_facecolor("#1a1a2e")
        if save:
            DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(
                DEF_FK_ASSETS_DIR / "def_fk_direct_shots.png",
                dpi=150, bbox_inches="tight",
            )
        plt.show()
        return

    plotted_outcomes: set[str] = set()
    for r in records:
        color = SHOT_OUTCOME_COLOR.get(r["outcome"], "#dee2e6")
        label = r["outcome"] if r["outcome"] not in plotted_outcomes else "_nolegend_"
        plotted_outcomes.add(r["outcome"])
        pitch.scatter(
            r["x"], r["y"], ax=ax,
            s=_marker_size(r["xg"]),
            color=color, edgecolors="white", linewidths=0.6,
            alpha=0.85, zorder=3, label=label,
        )
        # Annotate with distance and xG
        ax.annotate(
            f"{r['distance']:.0f}y\nxG {r['xg']:.2f}",
            xy=(r["x"], r["y"]),
            xytext=(6, 6), textcoords="offset points",
            fontsize=7, color="white", alpha=0.85,
            zorder=4,
        )

    n = len(records)
    n_goals = sum(1 for r in records if r["outcome"] == "Goal")
    total_xg = sum(r["xg"] for r in records)
    avg_xg = total_xg / n if n else 0.0

    outcome_legend = ax.legend(
        title="Shot outcome",
        loc="upper left", bbox_to_anchor=(1.01, 1.0),
        framealpha=0.7, fontsize=9, title_fontsize=10,
    )
    ax.add_artist(outcome_legend)

    # xG-size legend (separate artist so it doesn't replace the outcome one)
    size_handles = [
        Line2D([0], [0], marker="o", color="w",
               markerfacecolor="grey", markersize=math.sqrt(_marker_size(xg)) / 2,
               label=f"xG = {xg:.2f}")
        for xg in (0.02, 0.05, 0.10)
    ]
    ax.legend(
        handles=size_handles, title="Marker size",
        loc="lower left", bbox_to_anchor=(1.01, 0.0),
        framealpha=0.7, fontsize=8, title_fontsize=9,
    )

    ax.set_title(
        f"Direct Free Kicks Conceded – Barcelona\n"
        f"N={n}  ·  Goals={n_goals}  ·  Total xG={total_xg:.2f}  ·  Avg xG={avg_xg:.3f}",
        color="white", fontsize=11, pad=12,
    )
    fig.set_facecolor("#1a1a2e")
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_direct_shots.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")
    plt.show()


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    pairs = build_pairs(BARCELONA)
    records = collect_direct_shots(pairs)
    print(f"Defending FKs: {len(pairs)}  ·  direct shots conceded: {len(records)}")
    for r in records:
        print(
            f"  {r['team']:<25} {r['player']:<22}"
            f"  d={r['distance']:.1f}y  xG={r['xg']:.3f}  outcome={r['outcome']}"
        )
    plot_direct_shots(records)


if __name__ == "__main__":
    run()
