"""
throwins.py

Data-collection helpers for throw-in analysis using StatsBomb event data.

StatsBomb throw-in events are Pass events (type.id == 30) where
pass.type.name == "Throw-in".  Key fields on each event:

    location              [x, y] where the throw-in was taken
    pass.end_location     [x, y] where the ball was thrown to
    pass.length           distance in metres
    pass.angle            radians; 0 = toward positive x (attacking direction)
    pass.outcome.name     absent/None = complete; "Incomplete", "Out", etc.
    pass.recipient.name   player who received the throw
    player.name           player who took the throw
    team.name             team taking the throw

Coordinate convention (StatsBomb per-team normalisation)
---------------------------------------------------------
Every team's events have that team always attacking left-to-right (x: 0→120).
So for Barcelona's own throw-in events no coordinate flip is needed:
    x ≈ 0   → Barcelona's defensive end
    x ≈ 120 → Barcelona's attacking end
    y ≈ 0   → right touchline (when attacking right)
    y ≈ 80  → left touchline  (when attacking right)
"""

import json
import math
import zipfile
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
# throwins.py lives at src/throwins/throwins.py; project root is three levels up.

_PROJECT_ROOT     = Path(__file__).parent.parent.parent
ASSETS_DIR        = _PROJECT_ROOT / "assets"
THROWINS_ASSETS_DIR = ASSETS_DIR / "throwins"
MATCHES_CSV       = _PROJECT_ROOT / "data" / "matches.csv"
STATSBOMB_DIR     = _PROJECT_ROOT / "data" / "statsbomb"

BARCELONA = "Barcelona"

_STATSBOMB_ZIPS = ["league_phase.zip", "last16.zip", "playoffs.zip", "quarterfinals.zip"]

# ── Thresholds ────────────────────────────────────────────────────────────────

SHORT_THROW      = 10   # metres — below this is a short throw
LONG_THROW       = 25   # metres — above this is a long throw

DEFENSIVE_THIRD_MAX  = 40   # StatsBomb x, 0–120
ATTACKING_THIRD_MIN  = 80

# cos(angle) thresholds for direction classification (~70° cone)
_FORWARD_COS  =  0.34
_BACKWARD_COS = -0.34

# StatsBomb event type IDs
_TYPE_PASS         = 30
_TYPE_SHOT         = 16
_TYPE_FOUL_WON     = 21
_TYPE_FOUL_COMMIT  = 22


# ── StatsBomb I/O ─────────────────────────────────────────────────────────────

def _build_statsbomb_index() -> dict[str, Path]:
    """Map every filename inside any StatsBomb ZIP to the ZIP that contains it."""
    index: dict[str, Path] = {}
    for zip_name in _STATSBOMB_ZIPS:
        zip_path = STATSBOMB_DIR / zip_name
        if not zip_path.exists():
            continue
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                index[name] = zip_path
    return index


_STATSBOMB_INDEX: dict[str, Path] = _build_statsbomb_index()


def _read_statsbomb_bytes(filename: str) -> bytes | None:
    zip_path = _STATSBOMB_INDEX.get(filename)
    if zip_path is None:
        return None
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(filename)


def _read_matches_df() -> pd.DataFrame:
    return pd.read_csv(
        MATCHES_CSV,
        names=["date", "utc", "statsbomb", "skillcorner", "home", "score",
               "away", "wyscout", "videooffset"],
        header=0,
    )


def team_games(team_name: str) -> list[int]:
    """Return StatsBomb match IDs for all matches where team_name appears."""
    df   = _read_matches_df()
    mask = (
        df["home"].str.contains(team_name, case=False, na=False)
        | df["away"].str.contains(team_name, case=False, na=False)
    )
    return df.loc[mask, "statsbomb"].astype(int).tolist()


def read_statsbomb(statsbomb_id: int) -> list:
    """Return the full event list for a match."""
    raw = _read_statsbomb_bytes(f"{statsbomb_id}.json")
    if raw is None:
        raise FileNotFoundError(f"StatsBomb events not found for match {statsbomb_id}")
    return json.loads(raw.decode("utf-8"))


# ── Throw-in filtering ────────────────────────────────────────────────────────

def team_throw_ins(events: list, team_name: str) -> list:
    """Return all throw-in events taken by team_name in the event list."""
    return [
        ev for ev in events
        if ev.get("type", {}).get("id") == _TYPE_PASS
        and ev.get("pass", {}).get("type", {}).get("name") == "Throw-in"
        and team_name.casefold() in ev.get("team", {}).get("name", "").casefold()
    ]


def barca_throw_ins(events: list) -> list:
    return team_throw_ins(events, BARCELONA)


def opponent_throw_ins(events: list, team_name: str) -> list:
    """Return throw-ins taken AGAINST team_name (i.e. by the opponent)."""
    return [
        ev for ev in events
        if ev.get("type", {}).get("id") == _TYPE_PASS
        and ev.get("pass", {}).get("type", {}).get("name") == "Throw-in"
        and team_name.casefold() not in ev.get("team", {}).get("name", "").casefold()
    ]


# ── Throw-in property functions ───────────────────────────────────────────────

def throw_in_zone(ev: dict) -> str:
    """Return 'Defensive', 'Middle', or 'Attacking' based on x-coordinate.

    Assumes Barcelona's perspective (x: 0→120 = own goal → opponent goal).
    """
    x = (ev.get("location") or [None])[0]
    if x is None:
        return "Unknown"
    if x <= DEFENSIVE_THIRD_MAX:
        return "Defensive"
    if x >= ATTACKING_THIRD_MIN:
        return "Attacking"
    return "Middle"


def throw_in_side(ev: dict) -> str:
    """Return 'Left' or 'Right' touchline.

    Matches the corner_side convention: y < 40 → 'Left', y ≥ 40 → 'Right'.
    """
    loc = ev.get("location") or []
    y   = loc[1] if len(loc) > 1 else None
    if y is None:
        return "Unknown"
    return "Left" if y < 40 else "Right"


def throw_in_direction(ev: dict) -> str:
    """Return 'Forward', 'Backward', or 'Lateral'.

    Uses pass.angle (radians; 0 = toward x=120 = Barcelona's attacking direction).
    A ~70° cone around each axis determines Forward/Backward; the rest is Lateral.
    """
    angle = ev.get("pass", {}).get("angle")
    if angle is None:
        return "Unknown"
    c = math.cos(angle)
    if c > _FORWARD_COS:
        return "Forward"
    if c < _BACKWARD_COS:
        return "Backward"
    return "Lateral"


def throw_in_length_category(ev: dict) -> str:
    """Return 'Short' (< 10 m), 'Medium', or 'Long' (> 25 m)."""
    length = ev.get("pass", {}).get("length")
    if length is None:
        return "Unknown"
    if length < SHORT_THROW:
        return "Short"
    if length > LONG_THROW:
        return "Long"
    return "Medium"


def throw_in_outcome(ev: dict) -> str:
    """Return 'Complete', 'Incomplete', 'Out', or the raw outcome name."""
    outcome_name = ev.get("pass", {}).get("outcome", {}).get("name", "")
    if not outcome_name:
        return "Complete"
    if outcome_name in ("Incomplete", "Pass Offside"):
        return "Incomplete"
    return outcome_name   # e.g. "Out", "Unknown"


# ── Sequence helpers ──────────────────────────────────────────────────────────

def throw_in_sequence(ev: dict, events: list) -> list:
    """Return events following this throw-in while play_pattern == 'From Throw In'.

    The throw-in event itself is excluded; the list is in chronological order.
    """
    idx    = ev.get("index", -1)
    result = []
    for e in sorted(events, key=lambda x: x.get("index", -1)):
        if e.get("index", -1) <= idx:
            continue
        if e.get("play_pattern", {}).get("name") == "From Throw In":
            result.append(e)
        else:
            break
    return result


def sequence_outcome(ev: dict, events: list) -> str:
    """Classify what happened after the throw-in.

    Priority: Goal > Shot > Foul > Possession Lost > Possession Kept
    """
    if throw_in_outcome(ev) != "Complete":
        return "Possession Lost"

    seq        = throw_in_sequence(ev, events)
    throw_team = ev.get("team", {}).get("name", "").casefold()

    for e in seq:
        type_id = e.get("type", {}).get("id")
        if type_id == _TYPE_SHOT:
            result = e.get("shot", {}).get("outcome", {}).get("name", "")
            return "Goal" if result == "Goal" else "Shot"
        if type_id in (_TYPE_FOUL_WON, _TYPE_FOUL_COMMIT):
            return "Foul"

    if not seq:
        return "Possession Kept"

    last_team = seq[-1].get("team", {}).get("name", "").casefold()
    return "Possession Kept" if last_team == throw_team else "Possession Lost"


def next_action(ev: dict, events: list) -> dict | None:
    """Return the first event after the throw-in in the sequence, or None."""
    seq = throw_in_sequence(ev, events)
    return seq[0] if seq else None


def throw_in_possession_won(ev: dict, events: list) -> bool | None:
    """Return whether the throwing team retained possession after the throw-in.

    True  — possession kept (Goal, Shot, Possession Kept, or foul won)
    False — possession lost or foul committed
    None  — indeterminate
    """
    outcome = sequence_outcome(ev, events)
    if outcome in ("Goal", "Shot", "Possession Kept"):
        return True
    if outcome == "Possession Lost":
        return False
    if outcome == "Foul":
        throw_team = ev.get("team", {}).get("name", "").casefold()
        for e in throw_in_sequence(ev, events):
            type_id = e.get("type", {}).get("id")
            if type_id == _TYPE_FOUL_WON:
                return e.get("team", {}).get("name", "").casefold() == throw_team
            if type_id == _TYPE_FOUL_COMMIT:
                return e.get("team", {}).get("name", "").casefold() != throw_team
    return None


# ── Build functions ───────────────────────────────────────────────────────────

def build_pairs(team_name: str) -> list[tuple]:
    """Return (throw_in_ev, events) for every throw-in by team_name across all games."""
    pairs = []
    for game_id in team_games(team_name):
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue
        for ev in team_throw_ins(events, team_name):
            pairs.append((ev, events))
    return pairs


def build_records(team_name: str) -> pd.DataFrame:
    """Return a DataFrame with one row per throw-in, all properties pre-computed.

    Columns
    -------
    game_id, player, minute, period,
    x, y, end_x, end_y, length, angle,
    zone, side, direction, length_category, outcome, sequence_outcome,
    possession_won
    """
    rows = []
    for game_id in team_games(team_name):
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue

        # Pre-sort once per game so throw_in_sequence doesn't re-sort each time
        sorted_events = sorted(events, key=lambda e: e.get("index", -1))

        for ev in team_throw_ins(sorted_events, team_name):
            loc     = ev.get("location") or [None, None]
            end_loc = ev.get("pass", {}).get("end_location") or [None, None]
            rows.append({
                "game_id":          game_id,
                "player":           ev.get("player", {}).get("name"),
                "minute":           ev.get("minute"),
                "period":           ev.get("period"),
                "x":                loc[0],
                "y":                loc[1],
                "end_x":            end_loc[0],
                "end_y":            end_loc[1],
                "length":           ev.get("pass", {}).get("length"),
                "angle":            ev.get("pass", {}).get("angle"),
                "zone":             throw_in_zone(ev),
                "side":             throw_in_side(ev),
                "direction":        throw_in_direction(ev),
                "length_category":  throw_in_length_category(ev),
                "outcome":          throw_in_outcome(ev),
                "sequence_outcome": sequence_outcome(ev, sorted_events),
                "possession_won":   throw_in_possession_won(ev, sorted_events),
            })

    return pd.DataFrame(rows)
