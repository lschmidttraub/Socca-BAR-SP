"""Throw-in analysis.

Metrics
-------
total_throw_ins, completed, in_attacking_third (x > 80),
long_throws (length > 25 yd), retained_possession, territory_gained_total.

Derived: completion_rate, territory_gained_avg, throws_per_match.

Breakdowns: by_pitch_third (defensive / middle / attacking).
"""

from __future__ import annotations

from .. import filters as f
from .. import pitch

name = "throw_ins"

LONG_THROW_THRESHOLD = 25  # yards
ATTACKING_THIRD_X = 80  # yards


def _pitch_third(x: float) -> str:
    if x < 40:
        return "defensive"
    elif x < 80:
        return "middle"
    else:
        return "attacking"


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    total = 0
    completed = 0
    in_attacking = 0
    long_throws = 0
    retained = 0
    territory_total = 0.0

    thirds: dict[str, dict[str, int]] = {
        "defensive": {"total": 0, "completed": 0},
        "middle": {"total": 0, "completed": 0},
        "attacking": {"total": 0, "completed": 0},
    }

    # Build index for forward-scanning retained possession
    by_index = {e["index"]: e for e in events}
    max_index = max(by_index) if by_index else 0

    for e in events:
        if not (f.by_team(e, team) and f.is_throw_in(e)):
            continue
        total += 1
        loc = e.get("location")
        end_loc = e.get("pass", {}).get("end_location")
        pass_length = e.get("pass", {}).get("length", 0)
        is_completed = f.is_pass_completed(e)

        if is_completed:
            completed += 1

        if loc and loc[0] > ATTACKING_THIRD_X:
            in_attacking += 1

        if pass_length > LONG_THROW_THRESHOLD:
            long_throws += 1

        # Territory gained (positive = forward)
        if loc and end_loc:
            gain = (end_loc[0] - loc[0]) * pitch.YARDS_TO_METERS
            territory_total += gain

        # Pitch third breakdown
        if loc:
            third = _pitch_third(loc[0])
            thirds[third]["total"] += 1
            if is_completed:
                thirds[third]["completed"] += 1

        # Retained possession: check if next event is still same team
        if is_completed:
            for next_idx in range(e["index"] + 1, min(e["index"] + 5, max_index + 1)):
                nxt = by_index.get(next_idx)
                if nxt is None:
                    continue
                if f.event_team(nxt) == team:
                    retained += 1
                break

    return {
        "total_throw_ins": total,
        "completed": completed,
        "in_attacking_third": in_attacking,
        "long_throws": long_throws,
        "retained_possession": retained,
        "territory_gained_total": round(territory_total, 2),
        "by_pitch_third": thirds,
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    total = totals.get("total_throw_ins", 0)
    comp = totals.get("completed", 0)
    metrics = {
        "total_throw_ins": total,
        "completed": comp,
        "in_attacking_third": totals.get("in_attacking_third", 0),
        "long_throws": totals.get("long_throws", 0),
        "retained_possession": totals.get("retained_possession", 0),
        "territory_gained_total": round(totals.get("territory_gained_total", 0), 2),
        "completion_rate": round(comp / total, 3) if total else 0,
        "territory_gained_avg": (
            round(totals.get("territory_gained_total", 0) / total, 2) if total else 0
        ),
        "throws_per_match": round(total / n_matches, 2) if n_matches else 0,
    }
    breakdowns = {
        "by_pitch_third": totals.get("by_pitch_third", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
