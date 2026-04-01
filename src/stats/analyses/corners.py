"""Corner kick analysis.

Metrics
-------
total_corners, completed, short_corners (length < 15 yd), long_corners,
shots_from_corners, goals_from_corners, xg_from_corners.

Derived: completion_rate, xg_per_corner, corners_per_match.

Breakdowns: by_side (left / right), by_delivery (short / long).
"""

from __future__ import annotations

from .. import filters as f
from .. import pitch

name = "corners"


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    total = 0
    completed = 0
    short = 0
    long_ = 0
    shots = 0
    goals = 0
    xg = 0.0

    left_total = 0
    left_completed = 0
    right_total = 0
    right_completed = 0

    short_completed = 0
    long_completed = 0

    # Count corner deliveries (passes)
    for e in events:
        if f.by_team(e, team) and f.is_corner_pass(e):
            total += 1
            loc = e.get("location")
            pass_length = e.get("pass", {}).get("length", 0)
            is_completed = f.is_pass_completed(e)

            if is_completed:
                completed += 1

            if pass_length < 15:
                short += 1
                if is_completed:
                    short_completed += 1
            else:
                long_ += 1
                if is_completed:
                    long_completed += 1

            # Side: y < 40 = right side, y > 40 = left side in StatsBomb coords
            if loc:
                if loc[1] < 40:
                    right_total += 1
                    if is_completed:
                        right_completed += 1
                else:
                    left_total += 1
                    if is_completed:
                        left_completed += 1

    # Count shots/goals/xG from corner sequences
    for e in events:
        if not (f.by_team(e, team) and f.is_shot(e)):
            continue
        if f.play_pattern(e) == "From Corner":
            shots += 1
            xg += f.shot_xg(e)
            if f.is_goal(e):
                goals += 1

    return {
        "total_corners": total,
        "completed": completed,
        "short_corners": short,
        "long_corners": long_,
        "shots_from_corners": shots,
        "goals_from_corners": goals,
        "xg_from_corners": round(xg, 3),
        "by_side": {
            "left": {"total": left_total, "completed": left_completed},
            "right": {"total": right_total, "completed": right_completed},
        },
        "by_delivery": {
            "short": {"total": short, "completed": short_completed},
            "long": {"total": long_, "completed": long_completed},
        },
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    tc = totals.get("total_corners", 0)
    metrics = {
        "total_corners": tc,
        "completed": totals.get("completed", 0),
        "short_corners": totals.get("short_corners", 0),
        "long_corners": totals.get("long_corners", 0),
        "shots_from_corners": totals.get("shots_from_corners", 0),
        "goals_from_corners": totals.get("goals_from_corners", 0),
        "xg_from_corners": round(totals.get("xg_from_corners", 0), 3),
        "completion_rate": round(totals.get("completed", 0) / tc, 3) if tc else 0,
        "xg_per_corner": round(totals.get("xg_from_corners", 0) / tc, 3) if tc else 0,
        "corners_per_match": round(tc / n_matches, 2) if n_matches else 0,
    }
    breakdowns = {
        "by_side": totals.get("by_side", {}),
        "by_delivery": totals.get("by_delivery", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
