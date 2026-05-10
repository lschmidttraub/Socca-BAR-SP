"""Shared helpers for analysing Barcelona's defensive free kicks.

Mirrors ``defending_corners.py`` for free kicks. A "defensive free kick"
is any free kick taken by the opponent in their attacking half
(StatsBomb x >= 60 in the opponent's frame), since this is the zone in
which a free kick is a real set-piece threat — direct shots, crosses or
designed routines, rather than a midfield restart.
"""

import math
import sys
from pathlib import Path

# Reuse data-loading helpers from the sibling corners module.  The defense
# scripts run as flat scripts (no package), so we inject the corners
# folder onto sys.path and import directly — same pattern other defense
# scripts already use.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corners"))
from defending_corners import (  # noqa: E402  (after sys.path mutation)
    BARCELONA,
    DATA_DIR,
    MATCHES_CSV,
    ASSETS_DIR,
    all_teams,
    average_distributions,
    barca_opponent,
    distance,
    get_result,
    playing_teams,
    read_statsbomb,
    team_games,
    is_aerial,
    action_body_part,
)
# Note: we deliberately do NOT re-export defending_corners.compute_outcome_pcts
# because it is hardcoded to classify_corner_outcome.  Use ``fk_outcome_pcts``
# below instead.

DEF_FK_ASSETS_DIR = ASSETS_DIR / "def_fk_analysis"

# ── Constants ────────────────────────────────────────────────────────────────

# StatsBomb event type ids (mirrored from defending_corners.py)
TYPE_PASS         = 30
TYPE_SHOT         = 16
TYPE_CLEARANCE    = 9
TYPE_GOALKEEPER   = 23
TYPE_INTERCEPTION = 10
TYPE_BLOCK        = 6
TYPE_FOUL_WON     = 21
TYPE_FOUL_COMMIT  = 22

# Minimum x (opponent frame) to count as an attacking-half FK.  60 yards
# = halfway line; matches setpiece_counts_avg_defensive.OPPONENT_HALF_X.
OPP_ATTACKING_X = 60.0

# FK passes shorter than this are treated as short / tap restarts and
# excluded from "designed delivery" analyses.
SHORT_FK_LENGTH = 10.0

# Pitch geometry (StatsBomb 120 x 80, attacking right by convention)
GOAL_X = 120.0
GOAL_Y = 40.0
PEN_AREA_Y_MIN, PEN_AREA_Y_MAX = 18.0, 62.0  # 18-yard box width
PEN_AREA_X_MIN = 102.0                       # edge of 18-yard box

# Distance bands (yards from goal centre, opponent attacking frame)
DIST_BAND_DIRECT_MAX = 25.0    # direct shooting range
DIST_BAND_CROSS_MAX = 40.0     # typical crossing range


# ── FK identification ─────────────────────────────────────────────────────────

def _pass_type_name(ev: dict) -> str | None:
    return ev.get("pass", {}).get("type", {}).get("name")


def _shot_type_name(ev: dict) -> str | None:
    return ev.get("shot", {}).get("type", {}).get("name")


def is_fk_pass(ev: dict) -> bool:
    return ev.get("type", {}).get("id") == TYPE_PASS and _pass_type_name(ev) == "Free Kick"


def is_fk_shot(ev: dict) -> bool:
    return ev.get("type", {}).get("id") == TYPE_SHOT and _shot_type_name(ev) == "Free Kick"


def is_fk_event(ev: dict) -> bool:
    return is_fk_pass(ev) or is_fk_shot(ev)


def fk_in_attacking_half(ev: dict) -> bool:
    loc = ev.get("location")
    return bool(loc and loc[0] >= OPP_ATTACKING_X)


# ── Defensive FK collection ───────────────────────────────────────────────────

def team_defend_fks(events: list, team_name: str) -> list:
    """Return all opponent free-kick events (pass or direct shot) in their
    attacking half against *team_name* in this match's events."""
    return [
        ev for ev in events
        if is_fk_event(ev)
        and fk_in_attacking_half(ev)
        and team_name.casefold() not in ev.get("team", {}).get("name", "").casefold()
    ]


def barca_defend_fks(events: list) -> list:
    return team_defend_fks(events, BARCELONA)


def build_pairs(team_name: str) -> list[tuple]:
    """Return ``(fk_event, events)`` pairs for every defensive FK of
    *team_name* across all of their league-phase matches."""
    pairs: list[tuple] = []
    for game_id in team_games(team_name):
        path = DATA_DIR / f"{game_id}.json"
        if not path.exists():
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue
        events = read_statsbomb(game_id)
        for fk in team_defend_fks(events, team_name):
            pairs.append((fk, events))
    return pairs


# ── FK side / origin zone / distance band ─────────────────────────────────────

def fk_side(fk_ev: dict) -> str:
    """'Left' / 'Right' / 'Central' from the defending team's perspective.

    Coordinate is in the opponent's attacking frame (x = 120 → defender
    goal); we use the y coordinate of the FK location to classify side.
    """
    loc = fk_ev.get("location")
    if not loc:
        return "Unknown"
    y = loc[1]
    if y < PEN_AREA_Y_MIN:
        return "Left"
    if y > PEN_AREA_Y_MAX:
        return "Right"
    return "Central"


def fk_distance_band(fk_ev: dict) -> str:
    """Coarse distance from goal: 'Direct', 'Crossing', 'Long Range'."""
    loc = fk_ev.get("location")
    if not loc:
        return "Unknown"
    d = math.hypot(GOAL_X - loc[0], GOAL_Y - loc[1])
    if d <= DIST_BAND_DIRECT_MAX:
        return "Direct"
    if d <= DIST_BAND_CROSS_MAX:
        return "Crossing"
    return "Long Range"


def fk_origin_zone(fk_ev: dict) -> str:
    """Combined zone label, e.g. 'Central / Direct'."""
    return f"{fk_side(fk_ev)} / {fk_distance_band(fk_ev)}"


# ── Sequence helpers ─────────────────────────────────────────────────────────

def fk_sequence(fk_ev: dict, events: list) -> list:
    """Events that follow *fk_ev* and belong to the same 'From Free Kick'
    play-pattern sequence, in index order."""
    fk_index = fk_ev.get("index", -1)
    seq: list = []
    for ev in sorted(events, key=lambda e: e.get("index", -1)):
        if ev.get("index", -1) <= fk_index:
            continue
        if ev.get("play_pattern", {}).get("name") == "From Free Kick":
            seq.append(ev)
        else:
            break
    return seq


def first_sequence_action(fk_ev: dict, events: list) -> dict | None:
    seq = fk_sequence(fk_ev, events)
    return seq[0] if seq else None


def fk_to_first_action_distance(fk_ev: dict, events: list) -> float | None:
    first = first_sequence_action(fk_ev, events)
    if first is None:
        return None
    fk_loc = fk_ev.get("location")
    act_loc = first.get("location")
    if fk_loc is None or act_loc is None:
        return None
    return distance(fk_loc, act_loc)


# ── Outcome classification ───────────────────────────────────────────────────

def classify_fk_outcome(fk_ev: dict, events: list) -> str:
    """Classify a defensive free-kick outcome.

    Priority:
      Direct Goal      – the FK itself was a direct shot and went in
      Direct Shot      – the FK itself was a direct shot (saved/blocked/off)
      Short FK         – played short (pass length < SHORT_FK_LENGTH)
      Goal             – sequence contained a shot that went in
      Shot             – sequence contained a shot
      Goalkeeper       – goalkeeper action
      Clearance        – defending header / kick clear
      Interception     – defending interception
      Block            – block on a shot/pass
      Foul             – foul during the sequence
      Out of Play      – nothing followed the FK
      Other            – fallback
    """
    if is_fk_shot(fk_ev):
        outcome = fk_ev.get("shot", {}).get("outcome", {}).get("name", "")
        return "Direct Goal" if outcome == "Goal" else "Direct Shot"

    length = fk_ev.get("pass", {}).get("length", float("inf"))
    if length < SHORT_FK_LENGTH:
        return "Short FK"

    sequence = fk_sequence(fk_ev, events)
    if not sequence:
        return "Out of Play"

    has_shot = False
    for ev in sequence:
        if ev.get("type", {}).get("id") == TYPE_SHOT:
            if ev.get("shot", {}).get("outcome", {}).get("name") == "Goal":
                return "Goal"
            has_shot = True
    if has_shot:
        return "Shot"

    for ev in sequence:
        type_id = ev.get("type", {}).get("id")
        if type_id == TYPE_GOALKEEPER:
            return "Goalkeeper"
        if type_id == TYPE_CLEARANCE:
            return "Clearance"
        if type_id == TYPE_INTERCEPTION:
            return "Interception"
        if type_id == TYPE_BLOCK:
            return "Block"
        if type_id in (TYPE_FOUL_WON, TYPE_FOUL_COMMIT):
            return "Foul"

    return "Other"


# Stable display order for outcome categories
OUTCOME_ORDER = [
    "Direct Goal", "Direct Shot",
    "Goal", "Shot",
    "Goalkeeper", "Clearance", "Interception", "Block",
    "Foul", "Short FK", "Out of Play", "Other",
]

# Colours used by every plot for consistent visual identity
OUTCOME_COLORS = {
    "Direct Goal":  "#b30000",
    "Direct Shot":  "#e63946",
    "Goal":         "#d62728",
    "Shot":         "#f4a261",
    "Goalkeeper":   "#9b5de5",
    "Clearance":    "#4895ef",
    "Interception": "#2dc653",
    "Block":        "#00b4d8",
    "Foul":         "#f9c74f",
    "Short FK":     "#adb5bd",
    "Out of Play":  "#6c757d",
    "Other":        "#dee2e6",
}


def order_outcomes(keys: list[str]) -> list[str]:
    """Return *keys* in OUTCOME_ORDER, then any extras alphabetically."""
    in_order = [o for o in OUTCOME_ORDER if o in keys]
    extras = sorted(k for k in keys if k not in OUTCOME_ORDER)
    return in_order + extras


def fk_outcome_pcts(pairs: list[tuple]) -> dict[str, float]:
    """Outcome → percentage distribution for a list of (fk_event, events)
    pairs, using the FK-specific classifier."""
    counts: dict[str, int] = {}
    for fk, events in pairs:
        outcome = classify_fk_outcome(fk, events)
        counts[outcome] = counts.get(outcome, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: 100 * v / total for k, v in counts.items()}


# ── Coordinate normalisation ──────────────────────────────────────────────────

def normalize_to_right(loc: list, fk_loc: list) -> list:
    """Mirror the corner-side helper: flip x so all FKs appear on the
    right half (Barcelona's defensive goal at x=120) for half-pitch
    plotting."""
    x, y = loc
    if fk_loc[0] < 60:
        x = 120 - x
    return [x, y]


# ── Convenience exports ──────────────────────────────────────────────────────

__all__ = [
    # Constants
    "BARCELONA", "DATA_DIR", "MATCHES_CSV", "ASSETS_DIR", "DEF_FK_ASSETS_DIR",
    "OPP_ATTACKING_X", "SHORT_FK_LENGTH",
    "GOAL_X", "GOAL_Y", "PEN_AREA_X_MIN",
    "OUTCOME_ORDER", "OUTCOME_COLORS",
    # Predicates / collectors
    "is_fk_pass", "is_fk_shot", "is_fk_event", "fk_in_attacking_half",
    "team_defend_fks", "barca_defend_fks", "build_pairs",
    # Classifiers
    "fk_side", "fk_distance_band", "fk_origin_zone", "classify_fk_outcome",
    # Sequence helpers
    "fk_sequence", "first_sequence_action", "fk_to_first_action_distance",
    # Aggregation
    "fk_outcome_pcts", "average_distributions", "order_outcomes",
    # Re-exported from defending_corners
    "all_teams", "team_games", "read_statsbomb", "playing_teams",
    "barca_opponent", "get_result",
    "is_aerial", "action_body_part", "distance", "normalize_to_right",
]
