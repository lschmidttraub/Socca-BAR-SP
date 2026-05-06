"""
def_corners_aerial.py

Analyse how Barcelona defends aerial corners.

An "aerial corner" is a corner kick delivered into the box (not short)
where at least one headed or aerial-duel action occurs in the sequence.

StatsBomb aerial-relevant event types:
    type.id == 21  Duel       – duel.type.name == "Aerial Lost"
    type.id == 9   Clearance  – clearance.head == true
    type.id == 16  Shot       – shot.body_part.name == "Head"
    type.id == 30  Pass       – pass.body_part.name == "Head"
    type.id == 23  Goalkeeper – any goalkeeper action

Usage:
    python src/defense/corners/def_corners_aerial.py
"""

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
from mplsoccer import Pitch

from defending_corners import (
    BARCELONA,
    DEF_CORNER_ASSETS_DIR,
    SHORT_CORNER_LENGTH,
    barca_defend_corners,
    barca_games,
    barca_opponent,
    classify_corner_outcome,
    corner_sequence,
    corner_side,
    playing_teams,
    read_statsbomb,
)

# StatsBomb type IDs
TYPE_DUEL       = 21
TYPE_CLEARANCE  = 9
TYPE_SHOT       = 16
TYPE_PASS       = 30
TYPE_GOALKEEPER = 23

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

_PITCH_LENGTH = 120


# ── Aerial event helpers ──────────────────────────────────────────────────────

def is_aerial_duel(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == TYPE_DUEL
        and ev.get("duel", {}).get("type", {}).get("name") == "Aerial Lost"
    )


def is_headed_clearance(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == TYPE_CLEARANCE
        and ev.get("clearance", {}).get("head") is True
    )


def is_headed_shot(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == TYPE_SHOT
        and ev.get("shot", {}).get("body_part", {}).get("name") == "Head"
    )


def is_headed_pass(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == TYPE_PASS
        and ev.get("pass", {}).get("body_part", {}).get("name") == "Head"
    )


def is_aerial_event(ev: dict) -> bool:
    return (
        is_aerial_duel(ev)
        or is_headed_clearance(ev)
        or is_headed_shot(ev)
        or is_headed_pass(ev)
    )


# ── Coordinate normalisation ──────────────────────────────────────────────────

def _to_barca_coords(loc: list, event_team: str) -> list:
    """Convert a StatsBomb location to Barcelona's coordinate system (goal at x=0).

    StatsBomb normalises each team's events so that team always attacks
    left-to-right (x: 0→120). Opponent events are mirrored relative to
    Barcelona's, so flip x for any non-Barcelona event.
    """
    x, y = loc[0], loc[1]
    if BARCELONA.casefold() not in event_team.casefold():
        x = _PITCH_LENGTH - x
    return [x, y]


# ── Data collection ───────────────────────────────────────────────────────────

def collect_data() -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Return (corners_df, aerials_df, scatter_records) for Barcelona defending aerial corners."""
    corner_records: list[dict] = []
    aerial_records: list[dict] = []
    scatter_records: list[dict] = []

    for game_id in barca_games():
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue

        opponent = barca_opponent(playing_teams(game_id))

        for corner_ev in barca_defend_corners(events):
            if corner_ev.get("pass", {}).get("length", float("inf")) < SHORT_CORNER_LENGTH:
                continue

            seq = corner_sequence(corner_ev, events)
            aerial_evs = [ev for ev in seq if is_aerial_event(ev)]
            if not aerial_evs:
                continue

            # First-duel winner
            barca_won_first_duel = None
            first_aerial = aerial_evs[0]
            if is_aerial_duel(first_aerial):
                duel_outcome = first_aerial.get("duel", {}).get("outcome", {}).get("name", "")
                acting_team  = first_aerial.get("team", {}).get("name", "")
                if duel_outcome in ("Won", "Won Out"):
                    barca_won_first_duel = (acting_team == BARCELONA)
                elif duel_outcome in ("Lost", "Lost In Play", "Lost Out"):
                    barca_won_first_duel = (acting_team != BARCELONA)

            corner_records.append({
                "game_id":              game_id,
                "opponent":             opponent,
                "period":               corner_ev.get("period"),
                "minute":               corner_ev.get("minute"),
                "aerial_events":        len(aerial_evs),
                "barca_won_first_duel": barca_won_first_duel,
                # classify_corner_outcome correctly prioritises Goal > Shot > Goalkeeper > Clearance
                "final_outcome":        classify_corner_outcome(corner_ev, events),
            })

            for ev in aerial_evs:
                type_id    = ev.get("type", {}).get("id")
                team       = ev.get("team", {}).get("name", "Unknown")
                player     = ev.get("player", {}).get("name", "Unknown")
                loc        = ev.get("location")

                if type_id == TYPE_DUEL:
                    ev_label   = "Aerial Duel"
                    ev_outcome = ev.get("duel", {}).get("outcome", {}).get("name", "")
                elif type_id == TYPE_CLEARANCE:
                    ev_label   = "Headed Clearance"
                    ev_outcome = "Success"
                elif type_id == TYPE_SHOT:
                    ev_label   = "Headed Shot"
                    ev_outcome = ev.get("shot", {}).get("outcome", {}).get("name", "")
                elif type_id == TYPE_PASS:
                    ev_label   = "Headed Pass"
                    ev_outcome = ev.get("pass", {}).get("outcome", {}).get("name", "Complete")
                else:
                    ev_label   = "Other"
                    ev_outcome = ""

                aerial_records.append({
                    "game_id":    game_id,
                    "opponent":   opponent,
                    "corner_idx": corner_ev.get("index"),
                    "team":       team,
                    "player":     player,
                    "is_barca":   BARCELONA.casefold() in team.casefold(),
                    "event_type": ev_label,
                    "outcome":    ev_outcome,
                    "x":          loc[0] if loc else None,
                    "y":          loc[1] if loc else None,
                })

            # Delivery location scatter
            corner_loc = corner_ev.get("location")
            end_loc    = corner_ev.get("pass", {}).get("end_location")
            if corner_loc and end_loc:
                corner_team = corner_ev.get("team", {}).get("name", "")
                nc = _to_barca_coords(corner_loc, corner_team)
                ne = _to_barca_coords(end_loc, corner_team)
                scatter_records.append({
                    "corner_x": nc[0],
                    "corner_y": nc[1],
                    "x":        ne[0],
                    "y":        ne[1],
                    "outcome":  classify_corner_outcome(corner_ev, events),
                    "side":     corner_side(corner_ev),
                })

    return pd.DataFrame(corner_records), pd.DataFrame(aerial_records), scatter_records


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_summary_charts(corners_df: pd.DataFrame, aerials_df: pd.DataFrame, save: bool = True) -> None:
    """Bar chart of final outcomes and top Barcelona players in aerial events."""
    barca_aerials = aerials_df[aerials_df["is_barca"]]

    outcome_counts = corners_df["final_outcome"].value_counts()
    top_players    = barca_aerials["player"].value_counts().head(10)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.set_facecolor("white")

    axes[0].bar(outcome_counts.index, outcome_counts.values, color="steelblue", edgecolor="white")
    axes[0].set_title("Aerial corner outcomes vs Barcelona")
    axes[0].set_ylabel("Corners")
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].grid(axis="y", alpha=0.25)
    for i, v in enumerate(outcome_counts.values):
        axes[0].text(i, v + 0.1, str(v), ha="center", va="bottom", fontsize=9)

    axes[1].barh(top_players.index[::-1], top_players.values[::-1], color="steelblue", edgecolor="white")
    axes[1].set_title("Barcelona players – aerial events in defending corners")
    axes[1].set_xlabel("Count")
    axes[1].grid(axis="x", alpha=0.25)

    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "def_corners_aerial.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


def plot_delivery_scatter(scatter_records: list[dict], save: bool = True) -> None:
    """Half-pitch scatter of where aerial corners were delivered.

    Barcelona's goal is on the left (x=0). Arrows run from the corner flag
    to the delivery spot; dots are coloured by corner outcome.
    Left corners (y<40) appear at the bottom; right corners (y≥40) at the top.
    """
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#444444",
    )
    fig, ax = pitch.draw(figsize=(10, 8))
    ax.set_xlim(-2, 62)  # left half only — Barcelona's goal at x=0

    plotted_outcomes: set[str] = set()

    for rec in scatter_records:
        outcome = rec["outcome"]
        color   = OUTCOME_COLORS.get(outcome, "#ffffff")

        ax.annotate(
            "",
            xy=(rec["x"], rec["y"]),
            xytext=(rec["corner_x"], rec["corner_y"]),
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
            rec["x"], rec["y"],
            ax=ax,
            color=color,
            edgecolors="white",
            linewidths=0.5,
            s=70,
            label=label,
            zorder=3,
        )

    ax.legend(
        title="Outcome",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        framealpha=0.7,
        fontsize=9,
        title_fontsize=10,
    )
    ax.set_title(
        f"Aerial Corner Delivery Locations – Barcelona Defending (N={len(scatter_records)})\n"
        "Barcelona's goal on the left  ·  bottom = left corner (y<40), top = right corner (y≥40)",
        color="black",
        fontsize=11,
        pad=12,
    )
    fig.set_facecolor("white")
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "def_corners_aerial_delivery.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Scatter saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    corners_df, aerials_df, scatter_records = collect_data()

    print(f"\nAerial corners against Barcelona : {len(corners_df)}")
    print(f"Aerial events inside those       : {len(aerials_df)}")

    if corners_df.empty:
        raise RuntimeError("No aerial corners found.")

    duel_known = corners_df["barca_won_first_duel"].dropna()
    if not duel_known.empty:
        win_rate = duel_known.mean() * 100
        print(f"\nBarcelona first-duel win rate    : {win_rate:.1f}%  "
              f"({duel_known.sum():.0f}/{len(duel_known)} duels)")

    print("\nFinal outcome of aerial corner sequences:")
    print(corners_df["final_outcome"].value_counts().to_string())

    barca_aerials = aerials_df[aerials_df["is_barca"]]
    print("\nTop Barcelona players in aerial events:")
    print(barca_aerials["player"].value_counts().head(10).to_string())

    plot_summary_charts(corners_df, aerials_df)
    plot_delivery_scatter(scatter_records)
