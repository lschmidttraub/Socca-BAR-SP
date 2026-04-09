"""
player_heights.py

Plot the height of every Barcelona player who played >= 3 games,
compared to the average player across the whole dataset.

Usage:
    python src/player_heights.py
"""

import json
from collections import defaultdict, Counter
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

from defending_corners import DATA_DIR, MATCHES_CSV, BARCELONA, ASSETS_DIR, _read_matches_df

MIN_GAMES = 3

# Manual overrides for players whose position cannot be resolved from the lineup data
PLAYER_POSITION_OVERRIDES: dict[str, str] = {
    "Diego Kochen":  "Goalkeeper",
    "Jofre Torrents": "Left Back",
}

# Position group mapping (StatsBomb position names → broad group)
POSITION_GROUPS = {
    "Goalkeeper":               ("GK",  "#e07b54"),
    "Center Back":              ("DEF", "#5b8db8"),
    "Left Back":                ("DEF", "#5b8db8"),
    "Right Back":               ("DEF", "#5b8db8"),
    "Left Wing Back":           ("DEF", "#5b8db8"),
    "Right Wing Back":          ("DEF", "#5b8db8"),
    "Left Center Back":         ("DEF", "#5b8db8"),
    "Right Center Back":        ("DEF", "#5b8db8"),
    "Center Midfield":          ("MID", "#6abf69"),
    "Left Center Midfield":     ("MID", "#6abf69"),
    "Right Center Midfield":    ("MID", "#6abf69"),
    "Defensive Midfield":       ("MID", "#6abf69"),
    "Left Defensive Midfield":  ("MID", "#6abf69"),
    "Right Defensive Midfield": ("MID", "#6abf69"),
    "Attacking Midfield":       ("MID", "#6abf69"),
    "Center Attacking Midfield":("MID", "#6abf69"),
    "Left Midfield":            ("MID", "#6abf69"),
    "Right Midfield":           ("MID", "#6abf69"),
    "Left Wing":                ("FWD", "#c678a8"),
    "Right Wing":               ("FWD", "#c678a8"),
    "Center Forward":           ("FWD", "#c678a8"),
    "Left Center Forward":      ("FWD", "#c678a8"),
    "Right Center Forward":     ("FWD", "#c678a8"),
    "Secondary Striker":        ("FWD", "#c678a8"),
}


def position_group(position_name: str) -> tuple[str, str]:
    """Return (label, color) for a raw StatsBomb position string."""
    return POSITION_GROUPS.get(position_name, ("?", "#aaaaaa"))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def read_lineups(statsbomb_id: int) -> list:
    path = DATA_DIR / f"{statsbomb_id}_lineups.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def starting_position(player: dict) -> str | None:
    """Return the first listed position name for a player, or None."""
    positions = player.get("positions", [])
    if positions:
        return positions[0].get("position")
    return None


def collect_heights():
    """
    Returns:
        barca_players : dict  player_name -> {"height": float, "games": int, "position": str}
        all_heights   : list  of all player heights across the whole dataset
    """
    df = _read_matches_df(MATCHES_CSV)
    all_game_ids = df["statsbomb"].astype(int).tolist()

    all_heights = []
    barca_player_games:    dict[str, set]     = defaultdict(set)
    barca_player_height:   dict[str, float]   = {}
    barca_player_positions: dict[str, Counter] = defaultdict(Counter)

    for game_id in all_game_ids:
        path = DATA_DIR / f"{game_id}_lineups.json"
        if not path.exists():
            continue

        lineups = read_lineups(game_id)

        for team_entry in lineups:
            team_name = team_entry.get("team_name", "")
            is_barca  = BARCELONA.casefold() in team_name.casefold()

            for player in team_entry.get("lineup", []):
                height = player.get("player_height")
                if height is None:
                    continue

                all_heights.append(float(height))

                if is_barca:
                    name = player["player_name"]
                    barca_player_games[name].add(game_id)
                    barca_player_height[name] = float(height)
                    pos = starting_position(player)
                    if pos:
                        barca_player_positions[name][pos] += 1

    barca_players = {}
    for name, games in barca_player_games.items():
        if len(games) < MIN_GAMES:
            continue
        pos_counter = barca_player_positions[name]
        most_common_pos = PLAYER_POSITION_OVERRIDES.get(
            name,
            pos_counter.most_common(1)[0][0] if pos_counter else "Unknown",
        )
        barca_players[name] = {
            "height":   barca_player_height[name],
            "games":    len(games),
            "position": most_common_pos,
        }

    return barca_players, all_heights


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot(barca_players: dict, all_heights: list):
    avg_all    = sum(all_heights) / len(all_heights) if all_heights else 0
    sorted_h   = sorted(all_heights)
    n          = len(sorted_h)
    median_all = (sorted_h[n // 2 - 1] + sorted_h[n // 2]) / 2 if n % 2 == 0 else sorted_h[n // 2]

    # Sort by height ascending (horizontal bars read naturally bottom→top)
    sorted_players = sorted(barca_players.items(), key=lambda x: x[1]["height"])
    names    = [p[0] for p in sorted_players]
    heights  = [p[1]["height"] for p in sorted_players]
    games    = [p[1]["games"] for p in sorted_players]
    positions = [p[1]["position"] for p in sorted_players]
    colors   = [position_group(pos)[1] for pos in positions]
    pos_labels = [position_group(pos)[0] for pos in positions]

    fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.38)))

    bars = ax.barh(names, heights, color=colors, edgecolor="white", zorder=2)

    # Label each bar: height + game count + position group
    x_min = min(heights + [avg_all]) - 6
    for bar, h, g, pl in zip(bars, heights, games, pos_labels):
        ax.text(
            h + 0.2,
            bar.get_y() + bar.get_height() / 2,
            f"{h:.0f} cm  ·  {pl}  ({g}g)",
            va="center", ha="left", fontsize=8,
        )

    # Average and median lines
    ax.axvline(avg_all,    color="tomato",  linewidth=1.5, linestyle="--", zorder=3)
    ax.axvline(median_all, color="orange",  linewidth=1.5, linestyle=":",  zorder=3)

    # Position group legend
    seen = {}
    for pos, color in POSITION_GROUPS.values():
        if pos not in seen:
            seen[pos] = color
    legend_patches = [mpatches.Patch(color=c, label=lbl) for lbl, c in seen.items()]
    legend_patches.append(mpatches.Patch(color="tomato", label=f"Dataset avg {avg_all:.1f} cm",    fill=False))
    legend_patches.append(mpatches.Patch(color="orange", label=f"Dataset median {median_all:.1f} cm", fill=False))
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8)

    x_max = max(heights) + 12
    ax.set_xlim(x_min, x_max)
    ax.set_xlabel("Height (cm)")
    ax.set_title(f"Barcelona player heights (≥ {MIN_GAMES} games played)")
    ax.grid(axis="x", alpha=0.25, zorder=1)

    plt.tight_layout()

    out_path = ASSETS_DIR / "player_heights.png"
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Plot saved to {out_path}")
    plt.show()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    barca_players, all_heights = collect_heights()
    print(f"Barcelona players with >= {MIN_GAMES} games: {len(barca_players)}")
    print(f"Dataset avg height: {sum(all_heights)/len(all_heights):.1f} cm  ({len(all_heights)} player appearances)")
    unknown = {p["position"] for p in barca_players.values() if position_group(p["position"])[0] == "?"}
    if unknown:
        print(f"Unmapped positions: {unknown}")
    plot(barca_players, all_heights)
