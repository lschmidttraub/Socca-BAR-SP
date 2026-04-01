"""Defensive set piece analysis.

Analyses opponent set pieces *against* the team — i.e. how well does the
team defend corners, free kicks, and penalties taken by the opponent.

Metrics
-------
corners_faced, goals_conceded_from_corners, xg_conceded_from_corners,
fk_faced_dangerous (opponent FK within 30 m of our goal),
goals_conceded_from_fk, xg_conceded_from_fk,
penalties_conceded, penalties_conceded_scored.

Derived: goals_conceded_per_corner, xg_conceded_per_corner.

Breakdowns: by_set_piece_type (corner / free_kick / penalty).
"""

from __future__ import annotations

from .. import filters as f
from .. import pitch

name = "defensive"

DANGEROUS_FK_DISTANCE = 30  # metres from goal


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    corners_faced = 0
    goals_corner = 0
    xg_corner = 0.0

    fk_faced_dangerous = 0
    goals_fk = 0
    xg_fk = 0.0

    penalties_conceded = 0
    penalties_scored = 0
    xg_penalty = 0.0

    # Opponent corners
    for e in events:
        if f.by_team(e, team):
            continue
        if f.is_corner_pass(e):
            corners_faced += 1

    # Opponent free kicks in dangerous positions
    for e in events:
        if f.by_team(e, team):
            continue
        if f.is_fk_pass(e) or f.is_fk_shot(e):
            loc = e.get("location")
            if loc and pitch.distance_to_goal(loc) <= DANGEROUS_FK_DISTANCE:
                fk_faced_dangerous += 1

    # Opponent penalties
    for e in events:
        if f.by_team(e, team):
            continue
        if f.is_penalty_shot(e):
            penalties_conceded += 1
            xg_penalty += f.shot_xg(e)
            if f.is_goal(e):
                penalties_scored += 1

    # Goals / xG conceded from set piece play patterns (opponent shots)
    for e in events:
        if f.by_team(e, team):
            continue
        if not f.is_shot(e):
            continue
        pp = f.play_pattern(e)
        xg_val = f.shot_xg(e)
        scored = f.is_goal(e)
        if pp == "From Corner":
            xg_corner += xg_val
            if scored:
                goals_corner += 1
        elif pp == "From Free Kick":
            xg_fk += xg_val
            if scored:
                goals_fk += 1

    return {
        "corners_faced": corners_faced,
        "goals_conceded_from_corners": goals_corner,
        "xg_conceded_from_corners": round(xg_corner, 3),
        "fk_faced_dangerous": fk_faced_dangerous,
        "goals_conceded_from_fk": goals_fk,
        "xg_conceded_from_fk": round(xg_fk, 3),
        "penalties_conceded": penalties_conceded,
        "penalties_conceded_scored": penalties_scored,
        "xg_conceded_from_penalties": round(xg_penalty, 3),
        "by_set_piece_type": {
            "corner": {
                "faced": corners_faced,
                "goals_conceded": goals_corner,
                "xg_conceded": round(xg_corner, 3),
            },
            "free_kick": {
                "faced": fk_faced_dangerous,
                "goals_conceded": goals_fk,
                "xg_conceded": round(xg_fk, 3),
            },
            "penalty": {
                "faced": penalties_conceded,
                "goals_conceded": penalties_scored,
                "xg_conceded": round(xg_penalty, 3),
            },
        },
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    cf = totals.get("corners_faced", 0)
    metrics = {
        "corners_faced": cf,
        "goals_conceded_from_corners": totals.get("goals_conceded_from_corners", 0),
        "xg_conceded_from_corners": round(totals.get("xg_conceded_from_corners", 0), 3),
        "fk_faced_dangerous": totals.get("fk_faced_dangerous", 0),
        "goals_conceded_from_fk": totals.get("goals_conceded_from_fk", 0),
        "xg_conceded_from_fk": round(totals.get("xg_conceded_from_fk", 0), 3),
        "penalties_conceded": totals.get("penalties_conceded", 0),
        "penalties_conceded_scored": totals.get("penalties_conceded_scored", 0),
        "xg_conceded_from_penalties": round(totals.get("xg_conceded_from_penalties", 0), 3),
        "goals_conceded_per_corner": round(
            totals.get("goals_conceded_from_corners", 0) / cf, 3
        ) if cf else 0,
        "xg_conceded_per_corner": round(
            totals.get("xg_conceded_from_corners", 0) / cf, 3
        ) if cf else 0,
    }
    breakdowns = {
        "by_set_piece_type": totals.get("by_set_piece_type", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
