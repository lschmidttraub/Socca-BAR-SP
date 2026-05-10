"""
def_fk_delivery_map.py

Half-pitch maps of Barcelona's defending free kicks.  Origin → endpoint
arrows, plus a kde heatmap of endpoints, restricted to non-short FKs
(SHORT_FK_LENGTH+) so we focus on designed deliveries.

Outputs:
  def_fk_delivery_arrows.png    Origin→endpoint arrows, coloured by side
  def_fk_endpoint_heatmap.png   KDE heatmap of endpoint y/x coordinates

Usage:
    python src/defense/free_kicks/def_fk_delivery_map.py
"""

import matplotlib.pyplot as plt
import numpy as np
from mplsoccer import Pitch

from defending_free_kicks import (
    BARCELONA,
    DEF_FK_ASSETS_DIR,
    SHORT_FK_LENGTH,
    build_pairs,
    fk_side,
    is_fk_pass,
    normalize_to_right,
)


SIDE_COLORS = {
    "Left":    "#2a9d8f",
    "Central": "#e9c46a",
    "Right":   "#e76f51",
    "Unknown": "#888888",
}


# ── Data shaping ─────────────────────────────────────────────────────────────

def collect_deliveries(pairs: list[tuple]) -> list[dict]:
    """Return one record per delivered (non-short) FK pass, normalised
    to the right half so Barcelona's goal sits at x=120."""
    records: list[dict] = []
    for fk, _events in pairs:
        if not is_fk_pass(fk):
            continue
        length = fk.get("pass", {}).get("length", float("inf"))
        if length < SHORT_FK_LENGTH:
            continue
        loc = fk.get("location")
        end = fk.get("pass", {}).get("end_location")
        if not loc or not end:
            continue
        n_loc = normalize_to_right(loc, loc)
        n_end = normalize_to_right(end, loc)
        records.append({
            "x":     n_loc[0],
            "y":     n_loc[1],
            "end_x": n_end[0],
            "end_y": n_end[1],
            "side":  fk_side(fk),
            "completed": fk.get("pass", {}).get("outcome") is None,
        })
    return records


# ── Plot 1: arrow map ────────────────────────────────────────────────────────

def plot_arrow_map(records: list[dict], save: bool = True) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="#1a1a2e",
        line_color="#aaaaaa",
    )
    fig, ax = pitch.draw(figsize=(13, 8))

    sides_drawn: set[str] = set()
    for r in records:
        color = SIDE_COLORS.get(r["side"], "#888888")
        alpha = 0.75 if r["completed"] else 0.30
        label = r["side"] if r["side"] not in sides_drawn else "_nolegend_"
        sides_drawn.add(r["side"])
        pitch.arrows(
            r["x"], r["y"], r["end_x"], r["end_y"],
            ax=ax, color=color, width=1.5, headwidth=5, headlength=4,
            alpha=alpha, zorder=2, label=label,
        )

    ax.set_title(
        f"Barcelona Defending FK Deliveries – Origin → Endpoint (N={len(records)})",
        color="white", fontsize=12, pad=10,
    )
    ax.legend(
        title="FK side",
        loc="upper left", bbox_to_anchor=(1.01, 1.0),
        fontsize=9, framealpha=0.7, title_fontsize=10,
    )
    fig.set_facecolor("#1a1a2e")
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_delivery_arrows.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")
    plt.show()


# ── Plot 2: endpoint heatmap ─────────────────────────────────────────────────

def plot_endpoint_heatmap(records: list[dict], save: bool = True) -> None:
    if not records:
        print("No delivered FKs — skipping heatmap.")
        return

    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="white",
        line_color="#444444",
    )
    fig, ax = pitch.draw(figsize=(13, 8))

    xs = np.array([r["end_x"] for r in records])
    ys = np.array([r["end_y"] for r in records])

    # mplsoccer kdeplot takes x,y arrays directly
    pitch.kdeplot(
        xs, ys, ax=ax, fill=True, levels=80,
        cmap="Reds", thresh=0.05, alpha=0.7,
    )
    pitch.scatter(
        xs, ys, ax=ax, s=22, color="#222222", alpha=0.55, zorder=3,
    )

    ax.set_title(
        f"Barcelona Defending FK – Delivery Endpoints (N={len(records)})\n"
        "Where opponents are aiming the ball when they deliver",
        fontsize=12, pad=10,
    )
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_endpoint_heatmap.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")
    plt.show()


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    pairs = build_pairs(BARCELONA)
    records = collect_deliveries(pairs)
    print(f"Defending FKs: {len(pairs)}  ·  delivered (non-short) passes: {len(records)}")
    plot_arrow_map(records)
    plot_endpoint_heatmap(records)


if __name__ == "__main__":
    run()
