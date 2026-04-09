"""
def_corners_aerial.py

Analyze how Barcelona defends aerial corners.

An "aerial corner" is a corner kick delivered into the box (not short),
where the first contest is an aerial duel or a headed action.

StatsBomb aerial-relevant event types used here:
    type.id == 21  Duel       – duel.type.name == "Aerial Lost" (both sides recorded)
    type.id == 9   Clearance  – clearance.head == true  → headed clearance
    type.id == 16  Shot       – shot.body_part.name == "Head" → headed shot
    type.id == 30  Pass       – pass.body_part.name == "Head" → headed pass / flick-on
    type.id == 23  Goalkeeper – gk action (claim, punch, etc.)

Usage:
    python src/def_corners_aerial.py
"""

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from mplsoccer import Pitch

from defending_corners import (
    ASSETS_DIR,
    DEF_CORNER_ASSETS_DIR,
    BARCELONA,
    barca_games,
    barca_defend_corners,
    corner_sequence,
    corner_side,
    classify_corner_outcome,
    normalize_to_right,
    read_statsbomb,
    playing_teams,
    barca_opponent,
)

OUT_DIR = DEF_CORNER_ASSETS_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

# StatsBomb type ids
TYPE_DUEL        = 21
TYPE_CLEARANCE   = 9
TYPE_SHOT        = 16
TYPE_PASS        = 30
TYPE_GOALKEEPER  = 23

SHORT_CORNER_LENGTH = 10  # same threshold as defending_corners.py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    return is_aerial_duel(ev) or is_headed_clearance(ev) or is_headed_shot(ev) or is_headed_pass(ev)


def aerial_duel_winner(ev: dict) -> str | None:
    """
    For a Duel (Aerial Lost) event, StatsBomb records the event from the
    perspective of the player who LOST. So the winner is the opposing team.
    Returns team name of the winner, or None if not determinable.
    """
    outcome = ev.get("duel", {}).get("outcome", {}).get("name", "")
    # Outcomes: "Lost", "Won", "Lost In Play", "Won"…
    team = ev.get("team", {}).get("name")
    if outcome in ("Won", "Won Out"):
        return team           # this player won
    if outcome in ("Lost", "Lost In Play", "Lost Out"):
        return None           # the other team won — we don't easily know who
    return None


# ---------------------------------------------------------------------------
# Main data collection
# ---------------------------------------------------------------------------

aerial_records = []    # one row per aerial event inside a corner sequence
corner_records = []    # one row per aerial corner sequence (summary)

for game_id in barca_games():
    events = read_statsbomb(game_id)
    teams  = playing_teams(game_id)
    opponent = barca_opponent(teams)

    for corner_ev in barca_defend_corners(events):
        length = corner_ev.get("pass", {}).get("length", float("inf"))
        if length < SHORT_CORNER_LENGTH:
            continue   # skip short corners

        seq = corner_sequence(corner_ev, events)
        aerial_events = [ev for ev in seq if is_aerial_event(ev)]

        if not aerial_events:
            continue   # not an aerial corner — skip

        # ── Corner-level summary ──────────────────────────────────────────
        barca_won_first_duel = None
        first_aerial = aerial_events[0]

        if is_aerial_duel(first_aerial):
            outcome = first_aerial.get("duel", {}).get("outcome", {}).get("name", "")
            acting_team = first_aerial.get("team", {}).get("name", "")
            if outcome in ("Won", "Won Out"):
                barca_won_first_duel = (acting_team == BARCELONA)
            elif outcome in ("Lost", "Lost In Play", "Lost Out"):
                barca_won_first_duel = (acting_team != BARCELONA)

        # Did the sequence end in a goal / shot / clearance?
        final_outcome = "Other"
        for ev in reversed(seq):
            type_id = ev.get("type", {}).get("id")
            if type_id == TYPE_SHOT:
                result = ev.get("shot", {}).get("outcome", {}).get("name", "")
                final_outcome = "Goal" if result == "Goal" else "Shot"
                break
            if type_id == TYPE_CLEARANCE:
                final_outcome = "Clearance"
                break
            if type_id == TYPE_GOALKEEPER:
                final_outcome = "Goalkeeper"
                break

        corner_records.append({
            "game_id":            game_id,
            "opponent":           opponent,
            "period":             corner_ev.get("period"),
            "minute":             corner_ev.get("minute"),
            "aerial_events":      len(aerial_events),
            "barca_won_first_duel": barca_won_first_duel,
            "final_outcome":      final_outcome,
        })

        # ── Per-event rows ────────────────────────────────────────────────
        for ev in aerial_events:
            type_id   = ev.get("type", {}).get("id")
            team      = ev.get("team", {}).get("name", "Unknown")
            player    = ev.get("player", {}).get("name", "Unknown")
            location  = ev.get("location")

            if type_id == TYPE_DUEL:
                ev_label = "Aerial Duel"
                outcome  = ev.get("duel", {}).get("outcome", {}).get("name", "")
            elif type_id == TYPE_CLEARANCE:
                ev_label = "Headed Clearance"
                outcome  = ev.get("clearance", {}).get("outcome", {}).get("name", "Success")
            elif type_id == TYPE_SHOT:
                ev_label = "Headed Shot"
                outcome  = ev.get("shot", {}).get("outcome", {}).get("name", "")
            elif type_id == TYPE_PASS:
                ev_label = "Headed Pass"
                outcome  = ev.get("pass", {}).get("outcome", {}).get("name", "Complete")
            else:
                ev_label = "Other"
                outcome  = ""

            aerial_records.append({
                "game_id":    game_id,
                "opponent":   opponent,
                "corner_idx": corner_ev.get("index"),
                "team":       team,
                "player":     player,
                "is_barca":   BARCELONA.casefold() in team.casefold(),
                "event_type": ev_label,
                "outcome":    outcome,
                "x":          location[0] if location else None,
                "y":          location[1] if location else None,
            })


# ---------------------------------------------------------------------------
# DataFrames
# ---------------------------------------------------------------------------

corners_df = pd.DataFrame(corner_records)
aerials_df = pd.DataFrame(aerial_records)

print(f"Aerial corners against Barcelona : {len(corners_df)}")
print(f"Aerial events inside those       : {len(aerials_df)}")

if corners_df.empty:
    raise RuntimeError("No aerial corners found.")

# ---------------------------------------------------------------------------
# Analysis
# TODO: add your own analyses below
# ---------------------------------------------------------------------------

# First-duel win rate for Barcelona
duel_known = corners_df["barca_won_first_duel"].dropna()
if not duel_known.empty:
    win_rate = duel_known.mean() * 100
    print(f"\nBarcelona first-duel win rate   : {win_rate:.1f}%  ({duel_known.sum():.0f}/{len(duel_known)} duels)")

# Final outcome distribution
print("\nFinal outcome of aerial corner sequences:")
print(corners_df["final_outcome"].value_counts().to_string())

# Top Barcelona players in aerial events
barca_aerials = aerials_df[aerials_df["is_barca"]]
print("\nTop Barcelona players in aerial events:")
print(barca_aerials["player"].value_counts().head(10).to_string())


# ---------------------------------------------------------------------------
# Plotting
# TODO: replace / extend with your own charts
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# -- Chart 1: final outcome distribution ------------------------------------
outcome_counts = corners_df["final_outcome"].value_counts()
axes[0].bar(outcome_counts.index, outcome_counts.values, color="steelblue", edgecolor="white")
axes[0].set_title("Aerial corner outcomes vs Barcelona")
axes[0].set_ylabel("Corners")
axes[0].tick_params(axis="x", rotation=30)
axes[0].grid(axis="y", alpha=0.25)

# -- Chart 2: top Barcelona players in aerial duels -------------------------
top_players = barca_aerials["player"].value_counts().head(10)
axes[1].barh(top_players.index[::-1], top_players.values[::-1], color="steelblue", edgecolor="white")
axes[1].set_title("Barcelona players – aerial events in defending corners")
axes[1].set_xlabel("Count")
axes[1].grid(axis="x", alpha=0.25)

plt.tight_layout()
out_path = OUT_DIR / "def_corners_aerial.png"
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\nPlot saved to {out_path}")
plt.show()

OUTCOME_COLORS = {
    "Goal":         "#e63946",
    "Shot":         "#f4a261",
    "Goalkeeper":   "#9b5de5",
    "Clearance":    "#4895ef",
    "Interception": "#2dc653",
    "Block":        "#00b4d8",
    "Foul":         "#f9c74f",
    "Other":        "#dee2e6",
}

# -- Chart 3: scatter of where aerial corners were delivered ----------------
scatter_records = []
for game_id in barca_games():
    events = read_statsbomb(game_id)
    for corner_ev in barca_defend_corners(events):
        length = corner_ev.get("pass", {}).get("length", float("inf"))
        if length < SHORT_CORNER_LENGTH:
            continue
        seq = corner_sequence(corner_ev, events)
        if not any(is_aerial_event(ev) for ev in seq):
            continue
        corner_loc = corner_ev.get("location")
        end_loc    = corner_ev.get("pass", {}).get("end_location")
        if corner_loc is None or end_loc is None:
            continue
        norm_end    = normalize_to_right(end_loc, corner_loc)
        norm_corner = normalize_to_right(corner_loc, corner_loc)
        outcome     = classify_corner_outcome(corner_ev, events)
        scatter_records.append({
            "x":        norm_end[0],
            "y":        norm_end[1],
            "corner_x": norm_corner[0],
            "corner_y": norm_corner[1],
            "outcome":  outcome,
            "side":     corner_side(corner_ev),
        })

pitch = Pitch(
    pitch_type="statsbomb",
    half=True,
    pitch_color="#1a1a2e",
    line_color="#aaaaaa",
)
fig_sc, ax_sc = pitch.draw(figsize=(14, 8))

plotted_outcomes = set()
for rec in scatter_records:
    outcome = rec["outcome"]
    color   = OUTCOME_COLORS.get(outcome, "#ffffff")
    label   = outcome if outcome not in plotted_outcomes else "_nolegend_"
    plotted_outcomes.add(outcome)

    ax_sc.annotate(
        "",
        xy=(rec["x"], rec["y"]),
        xytext=(rec["corner_x"], rec["corner_y"]),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=0.8, alpha=0.4, mutation_scale=8),
        zorder=2,
    )
    pitch.scatter(
        rec["x"], rec["y"],
        ax=ax_sc,
        color=color,
        edgecolors="white",
        linewidths=0.5,
        s=70,
        label=label,
        zorder=3,
    )

ax_sc.legend(
    title="Outcome",
    loc="upper left",
    bbox_to_anchor=(1.01, 1.0),
    framealpha=0.7,
    fontsize=9,
    title_fontsize=10,
)
ax_sc.set_title(
    f"Where aerial corners against Barcelona were delivered (N={len(scatter_records)})\n"
    "Normalised to attacking right — arrows from corner flag to delivery spot",
    color="white",
    fontsize=11,
    pad=12,
)
fig_sc.set_facecolor("#1a1a2e")
plt.tight_layout()

sc_path = OUT_DIR / "def_corners_aerial_delivery.png"
fig_sc.savefig(sc_path, dpi=150, bbox_inches="tight")
print(f"Scatter saved to {sc_path}")
plt.show()
