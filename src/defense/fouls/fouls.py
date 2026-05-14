"""
fouls.py

Data collection and analysis utilities for fouls committed by Barcelona
and the defending set-piece situations they create for the opponent.

Each foul record captures:
  - Where on the pitch the foul was committed (Barcelona's attacking frame)
  - Who committed it and what card (if any) was given
  - The set piece the opponent received (Free Kick / Penalty)
  - The outcome of that subsequent set-piece sequence

StatsBomb orientation note
--------------------------
Events are stored so that the team that performed the action always
attacks toward x = 120.  For "Foul Committed" events by Barcelona the
location is therefore in Barcelona's attacking frame: their own goal is
near x = 0, the opponent's goal near x = 120.  Fouls close to x = 0
are the most dangerous (near Barcelona's goal).  The subsequent
opponent free kick lives in the opponent's attacking frame and its
x-coordinate is NOT flipped here — call sites that need a common frame
should apply the usual reflection (x → 120 − x) themselves.

Usage
-----
    from fouls import all_barca_fouls, dangerous_fouls, setpiece_outcome_rate

    records = all_barca_fouls()          # list[dict], one per foul
    danger  = dangerous_fouls(records)   # fouls in own / middle third
    rates   = setpiece_outcome_rate(danger)
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match

_SB_ROOT  = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
DATA      = _SB_ROOT
TEAM = "Barcelona"

# ── StatsBomb type IDs ────────────────────────────────────────────────────────

TYPE_FOUL_COMMITTED = 22
TYPE_FOUL_WON       = 21
TYPE_SHOT           = 16
TYPE_PASS           = 30
TYPE_CLEARANCE      = 9
TYPE_GOALKEEPER     = 23
TYPE_INTERCEPTION   = 10
TYPE_BLOCK          = 6

# Barcelona's own goal center in their attacking frame
_OWN_GOAL_X = 0.0
_OWN_GOAL_Y = 40.0

# How many events to scan forward when looking for the resulting set piece
_FK_SCAN_WINDOW = 15


# ── Pitch zone helpers ────────────────────────────────────────────────────────

def dist_to_own_goal(x: float, y: float) -> float:
    """Euclidean distance from (x, y) to Barcelona's own goal center.

    Lower values mean the foul was in a more dangerous area.
    """
    return math.sqrt((x - _OWN_GOAL_X) ** 2 + (y - _OWN_GOAL_Y) ** 2)


def foul_zone(x: float) -> str:
    """Pitch third from Barcelona's defensive perspective (own goal at x = 0).

    Own third    x < 40  — most dangerous, FK close to goal
    Middle third 40 ≤ x < 80
    Final third  x ≥ 80  — tactical foul, far from goal
    """
    if x < 40:
        return "Own third"
    if x < 80:
        return "Middle third"
    return "Final third"


def is_dangerous_zone(x: float) -> bool:
    """True if the foul is in the own or middle third (x < 80)."""
    return x < 80


# ── Foul event field accessors ────────────────────────────────────────────────

def is_foul_committed(ev: dict) -> bool:
    return ev.get("type", {}).get("id") == TYPE_FOUL_COMMITTED


def foul_card(ev: dict) -> str | None:
    """Card name ("Yellow Card", "Red Card", "Second Yellow") or None."""
    card = ev.get("foul_committed", {}).get("card", {})
    return card.get("name") if card else None


def is_penalty_foul(ev: dict) -> bool:
    """True if the foul was inside the penalty box (StatsBomb penalty flag)."""
    return bool(ev.get("foul_committed", {}).get("penalty"))


def foul_type_name(ev: dict) -> str | None:
    """Foul sub-type name (e.g. 'Foul Out', 'Dangerous Play') or None."""
    ft = ev.get("foul_committed", {}).get("type", {})
    return ft.get("name") if ft else None


def foul_advantage(ev: dict) -> bool:
    """True if the referee played advantage after the foul."""
    return bool(ev.get("foul_committed", {}).get("advantage"))


# ── Set-piece sequence helpers ────────────────────────────────────────────────

def _is_fk_restart(ev: dict, opponent_team: str) -> bool:
    """True if ev is a free kick pass or penalty/FK shot by the opponent."""
    if ev.get("team", {}).get("name") != opponent_team:
        return False
    type_id = ev.get("type", {}).get("id")
    if type_id == TYPE_PASS:
        return ev.get("pass", {}).get("type", {}).get("name") == "Free Kick"
    if type_id == TYPE_SHOT:
        return ev.get("shot", {}).get("type", {}).get("name") in ("Free Kick", "Penalty")
    return False


def setpiece_after_foul(
    foul_ev: dict,
    events: list[dict],
    opponent_team: str,
) -> dict | None:
    """Return the opponent's FK or penalty restart event following this foul.

    Scans up to _FK_SCAN_WINDOW events forward within the same period.
    Returns None if no restart is found (e.g. advantage played, or data gap).
    """
    foul_index  = foul_ev.get("index", -1)
    foul_period = foul_ev.get("period")
    scanned = 0
    for ev in events:
        if ev.get("index", -1) <= foul_index:
            continue
        if ev.get("period") != foul_period:
            break
        if _is_fk_restart(ev, opponent_team):
            return ev
        scanned += 1
        if scanned >= _FK_SCAN_WINDOW:
            break
    return None


def setpiece_sequence(setpiece_ev: dict, events: list[dict]) -> list[dict]:
    """Return all events belonging to the set-piece sequence.

    Uses the StatsBomb possession ID to bound the sequence: events are
    collected while period and possession match those of setpiece_ev.
    """
    sp_index      = setpiece_ev.get("index", -1)
    sp_possession = setpiece_ev.get("possession")
    sp_period     = setpiece_ev.get("period")
    result = []
    for ev in events:
        idx = ev.get("index", -1)
        if idx < sp_index:
            continue
        if ev.get("period") != sp_period or ev.get("possession") != sp_possession:
            if result:
                break
            continue
        result.append(ev)
    return result


def classify_setpiece_outcome(setpiece_ev: dict, events: list[dict]) -> str:
    """Classify what happened in the set-piece sequence after a foul.

    Priority (highest to lowest):
      Goal         — sequence contained a goal
      Shot         — sequence contained a shot (no goal)
      Goalkeeper   — GK action (claim, punch, save)
      Clearance    — defending player cleared the ball
      Interception — defending player intercepted
      Block        — player blocked shot or pass
      Other        — anything else (e.g. long sequence ending in corner)
    """
    sequence = setpiece_sequence(setpiece_ev, events)

    has_shot = False
    for ev in sequence:
        type_id = ev.get("type", {}).get("id")
        if type_id == TYPE_SHOT:
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

    return "Other"


def setpiece_xg(setpiece_ev: dict, events: list[dict]) -> float:
    """Total xG from all shots in the set-piece sequence."""
    return sum(
        float(ev.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)
        for ev in setpiece_sequence(setpiece_ev, events)
        if ev.get("type", {}).get("id") == TYPE_SHOT
    )


# ── Per-match collector ───────────────────────────────────────────────────────

def collect_barca_fouls(
    game_id: str,
    events: list[dict],
    barca_sb: str,
    opponent: str,
) -> list[dict]:
    """Return one record per foul committed by Barcelona in a single match.

    Parameters
    ----------
    game_id   : StatsBomb match ID string
    events    : full event list for the match
    barca_sb  : Barcelona's team name as it appears in the events
    opponent  : opponent's team name as it appears in the events

    Record fields
    -------------
    game_id, opponent, period, minute, second,
    player, x, y, zone, dist_to_goal,
    card, foul_type, is_penalty, advantage,
    setpiece_type, setpiece_outcome, setpiece_xg,
    setpiece_x, setpiece_y
    """
    records: list[dict] = []

    for ev in events:
        if not is_foul_committed(ev):
            continue
        if ev.get("team", {}).get("name") != barca_sb:
            continue

        loc = ev.get("location")
        if loc is None:
            continue
        x, y = float(loc[0]), float(loc[1])

        is_pen = is_penalty_foul(ev)

        sp_ev = setpiece_after_foul(ev, events, opponent)

        if sp_ev is None:
            sp_type    = "None"
            sp_outcome = "None"
            sp_xg_val  = 0.0
            sp_x = sp_y = None
        else:
            type_id = sp_ev.get("type", {}).get("id")
            if type_id == TYPE_SHOT:
                shot_type_name = sp_ev.get("shot", {}).get("type", {}).get("name", "")
                sp_type = "Penalty" if shot_type_name == "Penalty" else "Free Kick"
            else:
                sp_type = "Penalty" if is_pen else "Free Kick"

            sp_outcome = classify_setpiece_outcome(sp_ev, events)
            sp_xg_val  = setpiece_xg(sp_ev, events)
            sp_loc     = sp_ev.get("location")
            sp_x       = float(sp_loc[0]) if sp_loc else None
            sp_y       = float(sp_loc[1]) if sp_loc else None

        records.append({
            "game_id":          game_id,
            "opponent":         opponent,
            "period":           ev.get("period"),
            "minute":           ev.get("minute"),
            "second":           ev.get("second"),
            "player":           ev.get("player", {}).get("name", "Unknown"),
            "x":                x,
            "y":                y,
            "zone":             foul_zone(x),
            "dist_to_goal":     dist_to_own_goal(x, y),
            "card":             foul_card(ev),
            "foul_type":        foul_type_name(ev),
            "is_penalty":       is_pen,
            "advantage":        foul_advantage(ev),
            "setpiece_type":    sp_type,
            "setpiece_outcome": sp_outcome,
            "setpiece_xg":      sp_xg_val,
            "setpiece_x":       sp_x,
            "setpiece_y":       sp_y,
        })

    return records


# ── Full-dataset collector ────────────────────────────────────────────────────

def _opponent_label(row: dict, team: str) -> str:
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    return away if team == home else home


def all_barca_fouls(data_dir: Path = DATA) -> list[dict]:
    """Collect all foul records for Barcelona across every match in the dataset."""
    records: list[dict] = []
    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            barca_sb = _team_in_match(TEAM, row, events)
            if barca_sb is None:
                continue
            game_id  = row.get("statsbomb", "").strip()
            opponent = _opponent_label(row, TEAM)
            opp_sb = _team_in_match(opponent, row, events) or opponent
            records.extend(collect_barca_fouls(game_id, events, barca_sb, opp_sb))
    return records


# ── Aggregation helpers ───────────────────────────────────────────────────────

def fouls_by_player(records: list[dict]) -> Counter:
    """Count of fouls per player, sorted most-to-least."""
    return Counter(r["player"] for r in records)


def fouls_by_zone(records: list[dict]) -> Counter:
    """Count of fouls per pitch zone."""
    return Counter(r["zone"] for r in records)


def fouls_by_card(records: list[dict]) -> Counter:
    """Count per card type (None = no card)."""
    return Counter(r["card"] for r in records)


def setpiece_outcome_rate(records: list[dict]) -> dict[str, float]:
    """Fraction of set pieces ending in each outcome.

    Only records where a set piece was found (setpiece_type != 'None')
    are included in the denominator.
    """
    relevant = [r for r in records if r["setpiece_type"] != "None"]
    if not relevant:
        return {}
    total = len(relevant)
    counts = Counter(r["setpiece_outcome"] for r in relevant)
    return {outcome: count / total for outcome, count in counts.items()}


def dangerous_fouls(records: list[dict]) -> list[dict]:
    """Filter to fouls in the own third or middle third (x < 80)."""
    return [r for r in records if is_dangerous_zone(r["x"])]


def penalty_fouls(records: list[dict]) -> list[dict]:
    """Filter to fouls that resulted in a penalty."""
    return [r for r in records if r["is_penalty"]]


def fouls_leading_to_shot(records: list[dict]) -> list[dict]:
    """Filter to fouls where the resulting set piece produced a shot or goal."""
    return [r for r in records if r["setpiece_outcome"] in ("Shot", "Goal")]


def avg_setpiece_xg(records: list[dict]) -> float:
    """Average xG of the set piece sequence across all records with a set piece."""
    relevant = [r for r in records if r["setpiece_type"] != "None"]
    if not relevant:
        return 0.0
    return sum(r["setpiece_xg"] for r in relevant) / len(relevant)
