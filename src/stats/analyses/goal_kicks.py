"""Goal kick analysis.

Metrics
-------
total_goal_kicks, short (length < 25 yd), long, completed_short, completed_long.

Derived: short_pct, long_pct, short_completion_rate, long_completion_rate.

Breakdowns: by_target_zone (defensive / midfield / attacking based on end_location).
"""

from __future__ import annotations

from .. import filters as f

name = "goal_kicks"

SHORT_THRESHOLD = 25  # yards


def _target_zone(end_x: float) -> str:
    if end_x < 40:
        return "defensive"
    elif end_x < 80:
        return "midfield"
    else:
        return "attacking"


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    total = 0
    short = 0
    long_ = 0
    completed_short = 0
    completed_long = 0

    zones: dict[str, dict[str, int]] = {
        "defensive": {"total": 0, "completed": 0},
        "midfield": {"total": 0, "completed": 0},
        "attacking": {"total": 0, "completed": 0},
    }

    for e in events:
        if not (f.by_team(e, team) and f.is_goal_kick(e)):
            continue
        total += 1
        pass_length = e.get("pass", {}).get("length", 0)
        is_completed = f.is_pass_completed(e)
        end_loc = e.get("pass", {}).get("end_location")

        if pass_length < SHORT_THRESHOLD:
            short += 1
            if is_completed:
                completed_short += 1
        else:
            long_ += 1
            if is_completed:
                completed_long += 1

        if end_loc:
            zone = _target_zone(end_loc[0])
            zones[zone]["total"] += 1
            if is_completed:
                zones[zone]["completed"] += 1

    return {
        "total_goal_kicks": total,
        "short": short,
        "long": long_,
        "completed_short": completed_short,
        "completed_long": completed_long,
        "by_target_zone": zones,
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    total = totals.get("total_goal_kicks", 0)
    short = totals.get("short", 0)
    long_ = totals.get("long", 0)
    metrics = {
        "total_goal_kicks": total,
        "short": short,
        "long": long_,
        "completed_short": totals.get("completed_short", 0),
        "completed_long": totals.get("completed_long", 0),
        "short_pct": round(short / total, 3) if total else 0,
        "long_pct": round(long_ / total, 3) if total else 0,
        "short_completion_rate": (
            round(totals.get("completed_short", 0) / short, 3) if short else 0
        ),
        "long_completion_rate": (
            round(totals.get("completed_long", 0) / long_, 3) if long_ else 0
        ),
        "goal_kicks_per_match": round(total / n_matches, 2) if n_matches else 0,
    }
    breakdowns = {
        "by_target_zone": totals.get("by_target_zone", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
