"""
def_corner_duels.py

Analyze duels that occur inside corner sequences when Barcelona is defending.

StatsBomb duel events (type.id == 21):
    duel.type.name          -- "Tackle" or "Aerial Lost"
    duel.outcome.name       -- "Won", "Lost", "Lost In Play", "Lost Out",
                               "Won Out", "Success", "Success In Play", "Success Out"
    location                -- [x, y] on 120×80 pitch
    player.name             -- player who initiated the duel
    team.name               -- team of that player

Note: StatsBomb records "Aerial Lost" from the perspective of the losing player,
so the duel appears twice in the feed (once per participant). Tackles appear
only from the tackler's perspective.

Usage:
    python src/def_corner_duels.py
"""

# TODO THIS FILE IS NOT COMPLETE 

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
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
    corner_side,
    normalize_to_right,
    playing_teams,
    read_statsbomb,
)

OUT_DIR = DEF_CORNER_ASSETS_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

DUEL_WIN_OUTCOMES  = {"Won", "Won Out", "Success", "Success In Play", "Success Out"}
DUEL_LOSS_OUTCOMES = {"Lost", "Lost In Play", "Lost Out"}


# ---------------------------------------------------------------------------
# Extended corner sequence — ball-range window
# ---------------------------------------------------------------------------

TAIL_EVENTS = 4   # extra events to grab after play_pattern leaves "From Corner"


def corner_sequence_in_zone(
    corner_ev: dict,
    events: list,
    tail: int = TAIL_EVENTS,
) -> list:
    """
    Return all events in the corner sequence, plus `tail` extra events
    immediately after the play_pattern leaves "From Corner".

    This captures second-ball duels that StatsBomb assigns a new play_pattern
    but are still part of the corner situation.
    Period changes always end the sequence.
    """
    corner_index  = corner_ev.get("index", -1)
    corner_period = corner_ev.get("period")

    in_corner_phase = False
    tail_remaining  = 0
    result = []

    for ev in sorted(events, key=lambda e: e.get("index", -1)):
        if ev.get("index", -1) <= corner_index:
            continue
        if ev.get("period") != corner_period:
            break

        is_from_corner = ev.get("play_pattern", {}).get("name") == "From Corner"

        if is_from_corner:
            in_corner_phase = True
            tail_remaining  = tail   # reset tail on every From Corner event
            result.append(ev)
        elif in_corner_phase and tail_remaining > 0:
            tail_remaining -= 1
            result.append(ev)
        elif in_corner_phase and tail_remaining == 0:
            break   # tail exhausted — sequence is over

    return result


# ---------------------------------------------------------------------------
# Data collectors
# ---------------------------------------------------------------------------

def is_duel(ev: dict) -> bool:
    # Match by name — type IDs can differ between StatsBomb dataset versions
    return ev.get("type", {}).get("name") == "Duel"


def duel_type(ev: dict) -> str:
    """Return 'Tackle' or 'Aerial' (or 'Unknown')."""
    name = ev.get("duel", {}).get("type", {}).get("name", "")
    if name == "Tackle":
        return "Tackle"
    if name == "Aerial Lost":
        return "Aerial"
    return "Unknown"


def duel_outcome_won(ev: dict) -> bool | None:
    """
    Return True if the acting player won the duel, False if lost, None if unclear.

    For Aerial Lost events StatsBomb records the event from the loser's POV
    — so "Won" outcome means the *other* team won. This function normalises
    that: True always means the acting player came out on top.
    """
    outcome = ev.get("duel", {}).get("outcome", {}).get("name", "")
    d_type  = duel_type(ev)

    if d_type == "Aerial":
        # Aerial Lost: outcome is from the loser's perspective
        if outcome in DUEL_LOSS_OUTCOMES:
            return False   # acting player lost
        if outcome in DUEL_WIN_OUTCOMES:
            return True    # acting player won (rare — usually the winner's event)
        return None

    # Tackle: outcome is from the tackler's perspective
    if outcome in DUEL_WIN_OUTCOMES:
        return True
    if outcome in DUEL_LOSS_OUTCOMES:
        return False
    return None


def collect_duel_records(skip_short: bool = True) -> list[dict]:
    """
    Return one record per duel event inside a Barcelona defending corner sequence.

    Each record contains:
        game_id, opponent, period, minute
        corner_side          -- "Left" / "Right"
        corner_outcome       -- classify_corner_outcome result
        team                 -- team name of the acting player
        player               -- player name
        is_barca             -- True if the duel was initiated by a Barcelona player
        duel_type            -- "Tackle" or "Aerial"
        won                  -- True / False / None  (from acting player's POV)
        x, y                 -- raw StatsBomb location
        x_norm, y_norm       -- normalised so Barcelona always defends right
    """
    records = []

    for game_id in barca_games():
        events   = read_statsbomb(game_id)
        teams    = playing_teams(game_id)
        opponent = barca_opponent(teams)

        for corner_ev in barca_defend_corners(events):
            length = corner_ev.get("pass", {}).get("length", float("inf"))
            if skip_short and length < SHORT_CORNER_LENGTH:
                continue

            seq     = corner_sequence_in_zone(corner_ev, events)
            outcome = classify_corner_outcome(corner_ev, events)
            c_side  = corner_side(corner_ev)
            corner_loc = corner_ev.get("location")

            for ev in seq:
                if not is_duel(ev):
                    continue

                loc    = ev.get("location")
                team   = ev.get("team", {}).get("name", "Unknown")
                player = ev.get("player", {}).get("name", "Unknown")

                x_norm, y_norm = None, None
                if loc and corner_loc:
                    norm = normalize_to_right(loc[:2], corner_loc)
                    x_norm, y_norm = norm[0], norm[1]

                records.append({
                    "game_id":       game_id,
                    "opponent":      opponent,
                    "period":        corner_ev.get("period"),
                    "minute":        corner_ev.get("minute"),
                    "corner_side":   c_side,
                    "corner_outcome": outcome,
                    "team":          team,
                    "player":        player,
                    "is_barca":      BARCELONA.casefold() in team.casefold(),
                    "duel_type":     duel_type(ev),
                    "won":           duel_outcome_won(ev),
                    "x":             loc[0] if loc else None,
                    "y":             loc[1] if loc else None,
                    "x_norm":        x_norm,
                    "y_norm":        y_norm,
                })

    return records


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------

def win_rate(df: pd.DataFrame) -> float | None:
    """Return the win rate (0–1) for rows where 'won' is not None."""
    known = df["won"].dropna()
    return known.mean() if not known.empty else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    records = collect_duel_records()
    df = pd.DataFrame(records)

    print(f"Total duel events in Barca defending corners : {len(df)}")
    if df.empty:
        raise RuntimeError("No duel records found.")

    barca_df = df[df["is_barca"]]
    opp_df   = df[~df["is_barca"]]

    print(f"  Barcelona duels : {len(barca_df)}")
    print(f"  Opponent  duels : {len(opp_df)}")

    # --- Win rates ---
    for label, sub in [("Barcelona", barca_df), ("Opponent", opp_df)]:
        for d_type in ("Aerial", "Tackle"):
            sub_t = sub[sub["duel_type"] == d_type]
            wr    = win_rate(sub_t)
            n     = sub_t["won"].notna().sum()
            if wr is not None:
                print(f"  {label:12s} {d_type:7s} win rate : {wr*100:.1f}%  ({int(wr*n)}/{n})")

    # --- Top Barcelona players in duels ---
    print("\nTop Barcelona players in corner duels:")
    if not barca_df.empty:
        print(barca_df["player"].value_counts().head(10).to_string())
    else:
        print("  (none)")

    # --- Duel type breakdown ---
    print("\nDuel type breakdown:")
    print(df.groupby(["is_barca", "duel_type"]).size().to_string())

    # ---------------------------------------------------------------------------
    # Plots — Barcelona duel outcomes by type
    # ---------------------------------------------------------------------------

    # --- Build outcome counts for Barcelona duels ---
    outcome_label = {True: "Won", False: "Lost", None: "Unclear"}
    barca_plot = barca_df.copy()
    barca_plot["outcome_label"] = barca_plot["won"].map(outcome_label)

    counts = (
        barca_plot.groupby(["duel_type", "outcome_label"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["Won", "Lost", "Unclear"], fill_value=0)
    )

    # 1. Grouped bar chart — wins/losses per duel type
    fig, ax = plt.subplots(figsize=(8, 5))
    x      = range(len(counts))
    width  = 0.25
    colors = {"Won": "#2ecc71", "Lost": "#e74c3c", "Unclear": "#95a5a6"}

    for i, outcome in enumerate(["Won", "Lost", "Unclear"]):
        bars = ax.bar(
            [xi + i * width for xi in x],
            counts[outcome],
            width=width,
            label=outcome,
            color=colors[outcome],
        )
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + 0.3,
                    str(int(h)),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                )

    ax.set_xticks([xi + width for xi in x])
    ax.set_xticklabels(counts.index, fontsize=12)
    ax.set_ylabel("Number of duels")
    ax.set_title("Barcelona duel outcomes during defending corners\n(by duel type)")
    ax.legend(title="Outcome")
    ax.set_ylim(0, counts.values.max() * 1.15)
    plt.tight_layout()
    out_path = OUT_DIR / "barca_duel_outcomes_bar.png"
    fig.savefig(out_path, dpi=150)
    print(f"\nSaved: {out_path}")
    plt.close(fig)

    # 2. Stacked percentage bar — relative win/loss split per duel type
    fig, ax = plt.subplots(figsize=(7, 5))
    known = counts[["Won", "Lost"]]
    totals = known.sum(axis=1)
    pct = known.div(totals, axis=0) * 100

    bottom = [0] * len(pct)
    for outcome, color in [("Won", "#2ecc71"), ("Lost", "#e74c3c")]:
        bars = ax.bar(pct.index, pct[outcome], bottom=bottom, color=color, label=outcome)
        for bar, b in zip(bars, bottom):
            h = bar.get_height()
            if h > 2:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    b + h / 2,
                    f"{h:.1f}%",
                    ha="center",
                    va="center",
                    fontsize=11,
                    color="white",
                    fontweight="bold",
                )
        bottom = [b + v for b, v in zip(bottom, pct[outcome])]

    ax.set_ylabel("Percentage (%)")
    ax.set_title("Barcelona duel win/loss split during defending corners\n(known outcomes only)")
    ax.set_ylim(0, 100)
    ax.legend(title="Outcome")
    plt.tight_layout()
    out_path = OUT_DIR / "barca_duel_outcomes_pct.png"
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close(fig)