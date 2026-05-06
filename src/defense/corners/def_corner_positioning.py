"""
def_corner_positioning.py

Analyze the positioning of Barcelona players in defending corner situations
using SkillCorner tracking data.

For each corner_reception frame where Barcelona is defending, all player
positions are read from the tracking stream — giving the full picture of
all 22 players, not just those who touched the ball.

Data layout
-----------
data/matches.csv
    columns: date, utc, statsbomb, skillcorner, home, score, away, wyscout, videooffset

data_new/skillcorner/{skillcorner_id}.zip  (or extracted folder)
    {id}_dynamic_events.csv
        start_type  -- "corner_reception" identifies the frame of interest
        frame_start -- frame number to look up in tracking
        group       -- "home team" / "away team" (the attacking team)

    {id}_tracking_extrapolated.jsonl
        frame                     -- int
        period                    -- int
        timestamp                 -- float (seconds)
        ball_data.x / .y          -- ball position in metres (origin = pitch centre)
        player_data[].player_id   -- int
        player_data[].x / .y      -- position in metres (origin = pitch centre)
        player_data[].is_detected -- bool

    {id}_match.json
        home_team / away_team     -- {"name": str, ...}
        players[]                 -- [{"id": int, "name": str, "team_id": int,
                                       "position": {"name": str}, ...}]

Usage:
    python src/def_corner_positioning.py
"""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from defending_corners import (
    BARCELONA,
    DEF_CORNER_ASSETS_DIR,
    MATCHES_CSV,
    _read_matches_df,
    distance,
)

SKILLCORNER_DIR = Path(__file__).parent.parent.parent.parent / "data" / "skillcorner"
OUT_DIR         = DEF_CORNER_ASSETS_DIR / "positioning"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PITCH_LENGTH = 105.0
PITCH_WIDTH  = 68.0


# ---------------------------------------------------------------------------
# SkillCorner package I/O
# ---------------------------------------------------------------------------

def _zip_path(skillcorner_id: int) -> Path | None:
    p = SKILLCORNER_DIR / f"{skillcorner_id}.zip"
    return p if p.exists() else None


def _read_member(skillcorner_id: int, filename: str) -> bytes | None:
    """Read a named file from {skillcorner_id}.zip."""
    p = _zip_path(skillcorner_id)
    if p is None:
        return None
    with zipfile.ZipFile(p) as zf:
        return zf.read(filename) if filename in zf.namelist() else None


def read_dynamic_events(skillcorner_id: int) -> pd.DataFrame | None:
    raw = _read_member(skillcorner_id, f"{skillcorner_id}_dynamic_events.csv")
    return pd.read_csv(io.BytesIO(raw)) if raw else None


def read_match_meta(skillcorner_id: int) -> dict:
    raw = _read_member(skillcorner_id, f"{skillcorner_id}.json")
    return json.loads(raw.decode("utf-8")) if raw else {}


def iter_tracking_frames(skillcorner_id: int):
    """Yield one dict per frame from the extrapolated tracking JSONL."""
    raw = _read_member(skillcorner_id, f"{skillcorner_id}_tracking_extrapolated.jsonl")
    if raw is None:
        return
    for line in io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"):
        line = line.strip()
        if line:
            yield json.loads(line)


# ---------------------------------------------------------------------------
# Corner helpers
# ---------------------------------------------------------------------------

def corners_against(skillcorner_id: int, defending_tid: int) -> list[dict]:
    """
    Return all corner_reception events in a game where `defending_tid` is defending.

    Parameters
    ----------
    skillcorner_id : SkillCorner game id
    defending_tid  : team_id of the defending team

    Returns
    -------
    List of dicts, one per corner, with keys:
        frame_start, period, minute_start, second_start, attacking_side
    """
    dynamic_events = read_dynamic_events(skillcorner_id)
    if dynamic_events is None:
        return []

    corner_rows = dynamic_events[
        (dynamic_events["start_type"].astype(str).str.casefold() == "corner_reception")
        & (dynamic_events["team_id"] != defending_tid)
    ]

    return corner_rows[[
        "frame_start", "period", "minute_start", "second_start", "attacking_side",
    ]].dropna(subset=["frame_start"]).to_dict(orient="records")


def per_corner_avg_distances(
    skillcorner_id: int,
    defending_tid: int,
    player_index: dict,
    n_smallest: int | None = None,
) -> list[float]:
    """
    Return one float per corner: the average nearest-opponent distance across
    outfield players at that corner frame.

    Parameters
    ----------
    n_smallest : if given, average only over the N players whose nearest-opponent
                 distance is smallest (i.e. most tightly marked); otherwise
                 average over all outfield players.
    """
    corners = corners_against(skillcorner_id, defending_tid)
    if not corners:
        return []

    target_frames = {int(c["frame_start"]): None for c in corners}
    remaining = set(target_frames)

    for tracking_frame in iter_tracking_frames(skillcorner_id):
        fid = tracking_frame.get("frame")
        if fid in remaining:
            dists = nearest_opponent_distance(tracking_frame, player_index, defending_tid)
            if dists:
                if n_smallest is not None:
                    dists = sorted(dists)[:n_smallest]
                target_frames[fid] = sum(dists) / len(dists)
            remaining.discard(fid)
            if not remaining:
                break

    return [v for v in target_frames.values() if v is not None]


def game_avg_distances(skillcorner_id: int, defending_tid: int, player_index: dict) -> float | None:
    """Average nearest-opponent distance across all corners in a single game."""
    vals = per_corner_avg_distances(skillcorner_id, defending_tid, player_index)
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# Match metadata helpers
# ---------------------------------------------------------------------------

def parse_player_index(match_meta: dict) -> dict[int, dict]:
    """
    Return player_id -> {name, team_id, team_side, is_gk} from match.json.
    team_side is "home team" or "away team".
    """
    index: dict[int, dict] = {}
    for player in match_meta.get("players", []):
        pid = player.get("id") or player.get("player_id")
        if pid is None:
            continue
        side = player.get("team_side") or player.get("group", "")
        index[int(pid)] = {
            "name":      player.get("name") or player.get("short_name", str(pid)),
            "team_id":   player.get("team_id"),
            "team_side": side,
            "is_gk":     player.get("position", {}).get("name", "") == "Goalkeeper"
                         if isinstance(player.get("position"), dict)
                         else False,
        }
    return index


def teams_from_meta(match_meta: dict) -> list[dict]:
    """
    Return [{name, id}, {name, id}] for the two teams in a match from match.json.
    """
    result = []
    for key in ("home_team", "away_team", "homeTeam", "awayTeam"):
        val = match_meta.get(key)
        if isinstance(val, dict):
            name = val.get("name") or val.get("short_name", "")
            tid  = val.get("id") or val.get("team_id")
            if name and tid is not None:
                result.append({"name": name, "id": int(tid)})
    return result


def barca_team_id(match_meta: dict) -> int | None:
    """Return the SkillCorner team_id for Barcelona from match.json, or None."""
    for t in teams_from_meta(match_meta):
        if BARCELONA.casefold() in t["name"].casefold():
            return t["id"]
    return None


# ---------------------------------------------------------------------------
# Positioning helper
# ---------------------------------------------------------------------------

def nearest_opponent_distance(
    frame: dict,
    player_index: dict[int, dict],
    barca_tid: int,
) -> list[float]:
    """
    Return [distance to nearest opponent from player p | p <- barcelona_players \ {goalkeeper}].

    Excludes both the Barcelona GK (from the Barcelona set) and the opponent GK
    (from the opponent set). Returns one float per outfield Barcelona player who
    has a known position in the frame.

    Parameters
    ----------
    frame        : one dict from iter_tracking_frames()
    player_index : output of parse_player_index()
    barca_tid    : SkillCorner team_id for Barcelona
    """
    barca_positions: dict[int, list] = {}
    opp_positions:   dict[int, list] = {}

    for p in frame.get("player_data", []):
        pid = p.get("player_id")
        x   = p.get("x")
        y   = p.get("y")
        if pid is None or x is None or y is None:
            continue
        meta  = player_index.get(int(pid), {})
        tid   = meta.get("team_id")
        is_gk = meta.get("is_gk", False)

        if tid == barca_tid and not is_gk:
            barca_positions[int(pid)] = [x, y]
        elif tid != barca_tid and not is_gk:
            opp_positions[int(pid)] = [x, y]

    if not opp_positions:
        return []

    result = []
    for pid, loc in barca_positions.items():
        nearest_id = min(opp_positions, key=lambda o: distance(loc, opp_positions[o]))
        result.append(distance(loc, opp_positions[nearest_id]))

    return result


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

import matplotlib.pyplot as plt
from collections import defaultdict

# ---------------------------------------------------------------------------
# Main loop — all games, all teams
# ---------------------------------------------------------------------------

matches_df = _read_matches_df(MATCHES_CSV)
team_distances:    defaultdict[str, list[float]] = defaultdict(list)
team_distances_5:  defaultdict[str, list[float]] = defaultdict(list)
# team_name -> list of per-corner avg distances (one float per corner, across all their games)

for _, match_row in matches_df.iterrows():
    skillcorner_id = int(match_row["skillcorner"]) if pd.notna(match_row["skillcorner"]) else None
    if skillcorner_id is None or _zip_path(skillcorner_id) is None:
        continue

    match_meta = read_match_meta(skillcorner_id)
    if not match_meta:
        continue

    teams        = teams_from_meta(match_meta)
    player_index = parse_player_index(match_meta)

    if len(teams) < 2:
        continue

    for team in teams:
        corner_dists = per_corner_avg_distances(skillcorner_id, team["id"], player_index)
        if corner_dists:
            team_distances[team["name"]].extend(corner_dists)

        corner_dists_5 = per_corner_avg_distances(skillcorner_id, team["id"], player_index, n_smallest=5)
        if corner_dists_5:
            team_distances_5[team["name"]].extend(corner_dists_5)

        if corner_dists:
            print(f"  [{skillcorner_id}] {team['name']:30s}  +{len(corner_dists)} corners")

# ---------------------------------------------------------------------------
# Plot: avg defending-corner distance per team (all teams)
# ---------------------------------------------------------------------------

team_df = pd.DataFrame([
    {
        "team":      name,
        "avg_dist":  sum(dists) / len(dists),
        "n_corners": len(dists),
    }
    for name, dists in team_distances.items()
]).sort_values("avg_dist")

fig, ax = plt.subplots(figsize=(10, max(4, len(team_df) * 0.38)))
bars = ax.barh(team_df["team"], team_df["avg_dist"], color="steelblue", edgecolor="white")

# Highlight Barcelona
barca_idx = team_df["team"].str.contains(BARCELONA, case=False)
for bar, is_barca in zip(bars, barca_idx):
    if is_barca:
        bar.set_color("#e63946")

for bar, val, n in zip(bars, team_df["avg_dist"], team_df["n_corners"]):
    ax.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
            f"{val:.2f} m  ({n}c)", va="center", fontsize=7.5)

ax.set_xlabel("Avg nearest-opponent distance during defending corners (m)")
ax.set_title("Defending corner compactness — all teams\n(red = Barcelona)")
ax.grid(axis="x", alpha=0.25)
plt.tight_layout()

out_path = OUT_DIR / "avg_distances_all_teams.png"
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"\nPlot saved to {out_path}")
plt.show()

# ---------------------------------------------------------------------------
# Plot: avg defending-corner distance — 5 most tightly marked players per team
# ---------------------------------------------------------------------------

team_df_5 = pd.DataFrame([
    {
        "team":      name,
        "avg_dist":  sum(dists) / len(dists),
        "n_corners": len(dists),
    }
    for name, dists in team_distances_5.items()
]).sort_values("avg_dist")

fig2, ax2 = plt.subplots(figsize=(10, max(4, len(team_df_5) * 0.38)))
bars2 = ax2.barh(team_df_5["team"], team_df_5["avg_dist"], color="steelblue", edgecolor="white")

barca_idx_5 = team_df_5["team"].str.contains(BARCELONA, case=False)
for bar, is_barca in zip(bars2, barca_idx_5):
    if is_barca:
        bar.set_color("#e63946")

for bar, val, n in zip(bars2, team_df_5["avg_dist"], team_df_5["n_corners"]):
    ax2.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
             f"{val:.2f} m  ({n}c)", va="center", fontsize=7.5)

ax2.set_xlabel("Avg nearest-opponent distance during defending corners (m) — 5 most marked players")
ax2.set_title("Defending corner compactness — 5 most tightly marked players per team\n(red = Barcelona)")
ax2.grid(axis="x", alpha=0.25)
plt.tight_layout()

out_path_5 = OUT_DIR / "avg_distances_all_teams_top5marked.png"
fig2.savefig(out_path_5, dpi=150, bbox_inches="tight")
print(f"Plot saved to {out_path_5}")
plt.show()