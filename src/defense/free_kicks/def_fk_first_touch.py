"""
def_fk_first_touch.py

Half-pitch scatter of the FIRST sequence action after a defensive free
kick — the moment the FK delivery is first contacted (defender clears,
attacker controls, GK claims, …).

Markers are coloured by outcome and shaped by body part (aerial vs
ground), mirroring def_corner_first_action_scatter.py.

Output:
  def_fk_first_touch.png

Usage:
    python src/defense/free_kicks/def_fk_first_touch.py
"""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch

from defending_free_kicks import (
    BARCELONA,
    DEF_FK_ASSETS_DIR,
    OUTCOME_COLORS,
    SHORT_FK_LENGTH,
    build_pairs,
    classify_fk_outcome,
    first_sequence_action,
    fk_side,
    is_aerial,
    is_fk_pass,
    normalize_to_right,
)


# ── Data shaping ─────────────────────────────────────────────────────────────

def collect_records(pairs: list[tuple]) -> list[dict]:
    """One record per defensive FK whose first sequence action has a
    location.  Short FKs are excluded — their first action is a normal
    pass exchange, not a contested first contact."""
    records: list[dict] = []
    for fk, events in pairs:
        # Skip short FKs (no contested first contact)
        if is_fk_pass(fk):
            length = fk.get("pass", {}).get("length", float("inf"))
            if length < SHORT_FK_LENGTH:
                continue

        action = first_sequence_action(fk, events)
        if action is None:
            continue

        fk_loc = fk.get("location")
        act_loc = action.get("location")
        if fk_loc is None or act_loc is None:
            continue

        n_act = normalize_to_right(act_loc, fk_loc)
        n_fk = normalize_to_right(fk_loc, fk_loc)
        records.append({
            "x":      n_act[0],
            "y":      n_act[1],
            "fk_x":   n_fk[0],
            "fk_y":   n_fk[1],
            "outcome": classify_fk_outcome(fk, events),
            "side":    fk_side(fk),
            "aerial":  is_aerial(action),
        })
    return records


# ── Plot ─────────────────────────────────────────────────────────────────────

def plot_first_touch(records: list[dict], save: bool = True) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="#1a1a2e",
        line_color="#aaaaaa",
    )
    fig, ax = pitch.draw(figsize=(14, 8))

    MARKERS = {True: "D", False: "o"}
    plotted_outcomes: set[str] = set()

    for r in records:
        color = OUTCOME_COLORS.get(r["outcome"], "#ffffff")
        marker = MARKERS[r["aerial"]]

        # Faint connector from FK origin to first contact
        ax.annotate(
            "",
            xy=(r["x"], r["y"]),
            xytext=(r["fk_x"], r["fk_y"]),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=0.7,
                alpha=0.45,
                mutation_scale=8,
            ),
            zorder=2,
        )

        label = r["outcome"] if r["outcome"] not in plotted_outcomes else "_nolegend_"
        plotted_outcomes.add(r["outcome"])
        pitch.scatter(
            r["x"], r["y"], ax=ax,
            color=color, edgecolors="white", linewidths=0.5,
            s=70, marker=marker, label=label, zorder=3,
        )

    outcome_legend = ax.legend(
        title="Outcome",
        loc="upper left", bbox_to_anchor=(1.01, 1.0),
        framealpha=0.7, fontsize=9, title_fontsize=10,
    )
    ax.add_artist(outcome_legend)

    body_handles = [
        Line2D([0], [0], marker="D", color="w", markerfacecolor="grey",
               markersize=8, label="Aerial (head)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="grey",
               markersize=8, label="Ground (foot/other)"),
    ]
    ax.legend(
        handles=body_handles, title="Body part",
        loc="lower left", bbox_to_anchor=(1.01, 0.0),
        framealpha=0.7, fontsize=9, title_fontsize=10,
    )

    ax.set_title(
        f"First Touch After Delivery – Barcelona Defending FKs (N={len(records)})\n"
        "Marker = first sequence action · arrows from FK origin",
        color="white", fontsize=11, pad=12,
    )
    fig.set_facecolor("#1a1a2e")
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_first_touch.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")
    plt.show()


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    pairs = build_pairs(BARCELONA)
    records = collect_records(pairs)
    print(f"Defending FKs: {len(pairs)}  ·  with first-action location: {len(records)}")
    plot_first_touch(records)


if __name__ == "__main__":
    run()
