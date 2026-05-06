"""
def_corner_positioning.py

Analyse the positioning of Barcelona players in defending corner situations
using SkillCorner tracking data.

For each corner_reception frame where Barcelona is defending, all player
positions are read from the tracking stream — giving the full picture of
all 22 players, not just those who touched the ball.

Data layout
-----------
data/matches.csv
    columns: date, utc, statsbomb, skillcorner, home, score, away, wyscout, videooffset

data/skillcorner/{skillcorner_id}.zip
    {id}_dynamic_events.csv
        start_type  -- "corner_reception" identifies the frame of interest
        frame_start -- frame number to look up in tracking
        team_id     -- team that is attacking (i.e. NOT the defending team)

    {id}_tracking_extrapolated.jsonl
        frame                     -- int
        player_data[].player_id   -- int
        player_data[].x / .y      -- position in metres (origin = pitch centre)

    {id}.json
        home_team / away_team     -- {"name": str, ...}
        players[]                 -- [{"id": int, "name": str, "team_id": int,
                                       "position": {"name": str}, ...}]

Usage:
    python src/defense/corners/def_corner_positioning.py
"""

import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
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


# ── SkillCorner I/O ───────────────────────────────────────────────────────────

def _zip_path(skillcorner_id: int) -> Path | None:
    p = SKILLCORNER_DIR / f"{skillcorner_id}.zip"
    return p if p.exists() else None


def _read_member(skillcorner_id: int, filename: str) -> bytes | None:
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


# ── Match metadata helpers ────────────────────────────────────────────────────

def parse_player_index(match_meta: dict) -> dict[int, dict]:
    """Return player_id -> {name, team_id, is_gk} from match.json."""
    index: dict[int, dict] = {}
    for player in match_meta.get("players", []):
        pid = player.get("id") or player.get("player_id")
        if pid is None:
            continue
        index[int(pid)] = {
            "name":    player.get("name") or player.get("short_name", str(pid)),
            "team_id": player.get("team_id"),
            "is_gk":   (player.get("position", {}).get("name", "") == "Goalkeeper"
                        if isinstance(player.get("position"), dict) else False),
        }
    return index


def teams_from_meta(match_meta: dict) -> list[dict]:
    """Return [{name, id}, {name, id}] for the two teams in a match."""
    result = []
    for key in ("home_team", "away_team", "homeTeam", "awayTeam"):
        val = match_meta.get(key)
        if isinstance(val, dict):
            name = val.get("name") or val.get("short_name", "")
            tid  = val.get("id") or val.get("team_id")
            if name and tid is not None:
                result.append({"name": name, "id": int(tid)})
    return result


# ── Positioning helper ────────────────────────────────────────────────────────

def nearest_opponent_distances(
    frame: dict,
    player_index: dict[int, dict],
    barca_tid: int,
) -> list[float]:
    """Return one distance per outfield Barcelona player: distance to their nearest opponent.

    Both goalkeepers are excluded from both sets.
    """
    barca_positions: dict[int, list] = {}
    opp_positions:   dict[int, list] = {}

    for p in frame.get("player_data", []):
        pid = p.get("player_id")
        x, y = p.get("x"), p.get("y")
        if pid is None or x is None or y is None:
            continue
        meta  = player_index.get(int(pid), {})
        tid   = meta.get("team_id")
        if meta.get("is_gk", False):
            continue
        if tid == barca_tid:
            barca_positions[int(pid)] = [x, y]
        else:
            opp_positions[int(pid)] = [x, y]

    if not opp_positions:
        return []

    opp_locs = list(opp_positions.values())
    return [
        min(distance(loc, opp) for opp in opp_locs)
        for loc in barca_positions.values()
    ]


# ── Core data collection — single pass per game ───────────────────────────────

def collect_game_data(
    skillcorner_id: int,
    teams: list[dict],
    player_index: dict,
) -> dict[str, dict]:
    """Return per-team positioning metrics using exactly one read of each data file.

    The old approach made four passes over the tracking JSONL per game
    (two metric variants × two teams). This function makes one pass and
    computes both variants simultaneously.

    Returns
    -------
    {team_name: {"all": [per-corner avg dist], "top5": [per-corner avg dist, 5 closest players]}}
    """
    # ── Read dynamic events once for all teams ────────────────────────────────
    dynamic_events = read_dynamic_events(skillcorner_id)
    if dynamic_events is None:
        return {}

    corner_rows = dynamic_events[
        dynamic_events["start_type"].astype(str).str.casefold() == "corner_reception"
    ]

    # Build frame_id → defending team_id map (one read covers all teams)
    team_frames: dict[int, list[int]] = {}   # tid -> [frame_ids]
    frame_to_tid: dict[int, int] = {}        # frame_id -> defending tid

    for team in teams:
        rows = corner_rows[corner_rows["team_id"] != team["id"]].dropna(subset=["frame_start"])
        fids = [int(f) for f in rows["frame_start"]]
        team_frames[team["id"]] = fids
        for fid in fids:
            frame_to_tid.setdefault(fid, team["id"])

    if not frame_to_tid:
        return {}

    # ── Single pass over tracking JSONL ──────────────────────────────────────
    remaining = set(frame_to_tid)
    frame_dists: dict[int, list[float]] = {}

    for frame in iter_tracking_frames(skillcorner_id):
        fid = frame.get("frame")
        if fid not in remaining:
            continue
        dists = nearest_opponent_distances(frame, player_index, frame_to_tid[fid])
        if dists:
            frame_dists[fid] = dists
        remaining.discard(fid)
        if not remaining:
            break

    # ── Aggregate both metric variants per team ───────────────────────────────
    result: dict[str, dict] = {}
    for team in teams:
        tid = team["id"]
        all_vals, top5_vals = [], []
        for fid in team_frames.get(tid, []):
            dists = frame_dists.get(fid)
            if not dists:
                continue
            all_vals.append(sum(dists) / len(dists))
            s = sorted(dists)[:5]
            top5_vals.append(sum(s) / len(s))
        result[team["name"]] = {"all": all_vals, "top5": top5_vals}

    return result


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_distances(
    distances: dict[str, list[float]],
    title: str,
    xlabel: str,
    out_path: Path,
    highlight: str | None = None,
    save: bool = True,
) -> None:
    """Horizontal bar chart of average nearest-opponent distance per team/opponent.

    Parameters
    ----------
    distances : {label: [per-corner distances]}
    highlight : if given, colour that bar red (used to mark Barcelona)
    """
    team_df = pd.DataFrame([
        {"team": name, "avg_dist": sum(d) / len(d), "n_corners": len(d)}
        for name, d in distances.items()
        if d
    ]).sort_values("avg_dist")

    fig, ax = plt.subplots(figsize=(10, max(4, len(team_df) * 0.38)))
    fig.set_facecolor("white")
    bars = ax.barh(team_df["team"], team_df["avg_dist"], color="steelblue", edgecolor="white")

    if highlight:
        mask = team_df["team"].str.contains(highlight, case=False)
        for bar, is_highlighted in zip(bars, mask):
            if is_highlighted:
                bar.set_color("#e63946")

    for bar, val, n in zip(bars, team_df["avg_dist"], team_df["n_corners"]):
        ax.text(
            val + 0.05, bar.get_y() + bar.get_height() / 2,
            f"{val:.2f} m  ({n}c)", va="center", fontsize=7.5,
        )

    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    matches_df = _read_matches_df(MATCHES_CSV)

    team_distances:    defaultdict[str, list[float]] = defaultdict(list)
    team_distances_5:  defaultdict[str, list[float]] = defaultdict(list)
    barca_per_opponent: defaultdict[str, list[float]] = defaultdict(list)

    for _, match_row in matches_df.iterrows():
        sc_id = int(match_row["skillcorner"]) if pd.notna(match_row["skillcorner"]) else None
        if sc_id is None or _zip_path(sc_id) is None:
            continue

        match_meta = read_match_meta(sc_id)
        if not match_meta:
            continue

        teams        = teams_from_meta(match_meta)
        player_index = parse_player_index(match_meta)
        if len(teams) < 2:
            continue

        game_data = collect_game_data(sc_id, teams, player_index)

        for team_name, metrics in game_data.items():
            if not metrics["all"]:
                continue
            team_distances[team_name].extend(metrics["all"])
            team_distances_5[team_name].extend(metrics["top5"])
            print(f"  [{sc_id}] {team_name:30s}  +{len(metrics['all'])} corners")

        # Accumulate per-opponent data for Barcelona-specific plot
        barca_entry = next(
            ((name, data) for name, data in game_data.items()
             if BARCELONA.casefold() in name.casefold()),
            None,
        )
        if barca_entry:
            barca_name, barca_data = barca_entry
            opponent = next(
                (t["name"] for t in teams if t["name"] != barca_name), None
            )
            if opponent and barca_data["all"]:
                barca_per_opponent[opponent].extend(barca_data["all"])

    plot_distances(
        team_distances,
        title="Defending corner compactness — all teams\n(red = Barcelona)",
        xlabel="Avg nearest-opponent distance during defending corners (m)",
        out_path=OUT_DIR / "avg_distances_all_teams.png",
        highlight=BARCELONA,
    )

    plot_distances(
        team_distances_5,
        title="Defending corner compactness — 5 most tightly marked players per team\n(red = Barcelona)",
        xlabel="Avg nearest-opponent distance — 5 most marked players (m)",
        out_path=OUT_DIR / "avg_distances_all_teams_top5marked.png",
        highlight=BARCELONA,
    )

    plot_distances(
        barca_per_opponent,
        title="Barcelona defending corners — avg nearest-opponent distance per game",
        xlabel="Avg nearest-opponent distance (m)",
        out_path=OUT_DIR / "avg_distances_per_game.png",
    )
