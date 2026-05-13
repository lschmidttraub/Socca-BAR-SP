"""
def_corner_positioning.py

Analyse the positioning of Barcelona players in defending corner situations
using SkillCorner tracking data.

For each corner kick where a team is defending, player positions are read
from the SkillCorner tracking frame closest to the StatsBomb event timestamp
(the moment the ball is kicked, not when it is first received).

Data layout
-----------
data/matches.csv
    columns: date, utc, statsbomb, skillcorner, home, score, away, wyscout, videooffset

data/statsbomb/{statsbomb_id}.json
    Corner kick events (type.id=30, pass.type.name="Corner") with minute/second
    timestamps used to locate the correct tracking frame.

data/skillcorner/{skillcorner_id}.zip
    {id}_tracking_extrapolated.jsonl
        timestamp                 -- HH:MM:SS.sss matched against StatsBomb time
        period                    -- int
        player_data[].player_id   -- int
        player_data[].x / .y      -- position in metres (origin = pitch centre)

    {id}.json
        home_team / away_team     -- {"name": str, "id": int, ...}
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
    read_statsbomb,
)

# CSV team name → StatsBomb spelling (same mapping as snippets/_loader.py)
_CSV_TO_STATSBOMB: dict[str, str] = {
    "Internazionale": "Inter Milan",
    "PSG": "Paris Saint-Germain",
    "Monaco": "AS Monaco",
    "Leverkusen": "Bayer Leverkusen",
    "Dortmund": "Borussia Dortmund",
    "Frankfurt": "Eintracht Frankfurt",
    "Qarabag": "Qarabağ FK",
    "Bayern München": "Bayern Munich",
    "Olympiacos Piraeus": "Olympiacos",
    "PSV": "PSV Eindhoven",
    "København": "FC København",
}


def _csv_to_sb(name: str) -> str:
    return _CSV_TO_STATSBOMB.get(name, name)


def _parse_timestamp(ts: str) -> float:
    """Parse SkillCorner HH:MM:SS.sss timestamp → total seconds."""
    hh, mm, ss = ts.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)

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


def read_match_meta(skillcorner_id: int) -> dict:
    raw = _read_member(skillcorner_id, f"{skillcorner_id}.json")
    return json.loads(raw.decode("utf-8")) if raw else {}


def _sc_team_ids(match_meta: dict) -> tuple[int, int]:
    """Return (home_team_id, away_team_id) from SkillCorner match metadata."""
    home = match_meta.get("home_team") or match_meta.get("homeTeam") or {}
    away = match_meta.get("away_team") or match_meta.get("awayTeam") or {}
    return int(home.get("id") or home["team_id"]), int(away.get("id") or away["team_id"])


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
    statsbomb_id: int,
    sb_home_name: str,
    sc_home_tid: int,
    sc_away_tid: int,
    teams: list[dict],
    player_index: dict,
) -> dict[str, dict]:
    """Return per-team positioning metrics at the moment each corner is taken.

    Uses StatsBomb event timestamps to locate the corner kick frame in the
    SkillCorner tracking stream (same approach as snippets/_loader.py), rather
    than the corner_reception dynamic event which fires at first touch.

    Returns
    -------
    {team_name: {"all": [per-corner avg dist], "top5": [per-corner avg dist, 5 closest players]}}
    """
    try:
        events = read_statsbomb(statsbomb_id)
    except FileNotFoundError:
        return {}

    # ── Build defending corner moments from StatsBomb events ─────────────────
    # corner_moments[defending_sc_tid] = [(period, time_sec), ...]
    corner_moments: dict[int, list[tuple[int, float]]] = {t["id"]: [] for t in teams}
    for ev in events:
        if not (ev.get("type", {}).get("id") == 30 and
                ev.get("pass", {}).get("type", {}).get("name") == "Corner"):
            continue
        period = int(ev.get("period", 1))
        t = float(ev.get("minute", 0) * 60 + ev.get("second", 0))
        # Home team attacks → away team defends, and vice-versa
        def_tid = sc_away_tid if ev.get("team", {}).get("name") == sb_home_name else sc_home_tid
        if def_tid in corner_moments:
            corner_moments[def_tid].append((period, t))

    # Group targets by period for fast per-frame filtering
    targets_by_period: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for tid, moments in corner_moments.items():
        for period, t in moments:
            targets_by_period[period].append((tid, period, t))

    if not targets_by_period:
        return {}

    # Pre-compute time bounds per period to skip non-corner frames cheaply
    WINDOW = 2.0
    period_bounds: dict[int, tuple[float, float]] = {
        p: (min(t for _, _, t in tgts) - WINDOW, max(t for _, _, t in tgts) + WINDOW)
        for p, tgts in targets_by_period.items()
    }

    # ── Single pass over tracking JSONL ──────────────────────────────────────
    # best_frames[(tid, period, t)] = (min_dt, dists)
    best_frames: dict[tuple, tuple] = {}

    for frame in iter_tracking_frames(skillcorner_id):
        ts = frame.get("timestamp")
        fperiod = frame.get("period")
        if not ts or fperiod is None:
            continue
        try:
            fperiod = int(fperiod)
            ftime = _parse_timestamp(str(ts))
        except (ValueError, TypeError):
            continue

        lo, hi = period_bounds.get(fperiod, (None, None))
        if lo is None or not (lo <= ftime <= hi):
            continue

        for tid, period, t in targets_by_period[fperiod]:
            dt = abs(ftime - t)
            if dt > WINDOW:
                continue
            key = (tid, period, t)
            prev = best_frames.get(key)
            if prev is None or dt < prev[0]:
                dists = nearest_opponent_distances(frame, player_index, tid)
                if dists:
                    best_frames[key] = (dt, dists)

    # ── Aggregate both metric variants per team ───────────────────────────────
    result: dict[str, dict] = {}
    for team in teams:
        tid = team["id"]
        all_vals, top5_vals = [], []
        for period, t in corner_moments.get(tid, []):
            entry = best_frames.get((tid, period, t))
            if not entry:
                continue
            _, dists = entry
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

    plt.close(fig)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    matches_df = _read_matches_df(MATCHES_CSV)

    team_distances:    defaultdict[str, list[float]] = defaultdict(list)
    team_distances_5:  defaultdict[str, list[float]] = defaultdict(list)
    barca_per_opponent: defaultdict[str, list[float]] = defaultdict(list)

    for _, match_row in matches_df.iterrows():
        sc_id = int(match_row["skillcorner"]) if pd.notna(match_row["skillcorner"]) else None
        sb_id = int(match_row["statsbomb"])   if pd.notna(match_row["statsbomb"])   else None
        if sc_id is None or sb_id is None or _zip_path(sc_id) is None:
            continue

        match_meta = read_match_meta(sc_id)
        if not match_meta:
            continue

        teams        = teams_from_meta(match_meta)
        player_index = parse_player_index(match_meta)
        if len(teams) < 2:
            continue

        try:
            sc_home_tid, sc_away_tid = _sc_team_ids(match_meta)
        except (KeyError, TypeError, ValueError):
            print(f"  [{sc_id}] cannot determine team IDs, skipping")
            continue
        sb_home_name = _csv_to_sb(str(match_row["home"]))

        game_data = collect_game_data(
            sc_id, sb_id, sb_home_name, sc_home_tid, sc_away_tid,
            teams, player_index,
        )

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
