"""Free kick analysis.

Metrics
-------
total_free_kicks, direct_shots, crosses, short_passes,
goals_direct, goals_from_fk_play, xg_direct, xg_from_fk_play.

Derived: conversion_rate_direct, xg_per_fk.

Breakdowns: by_distance_bucket (5 m), by_offside (10 m from baseline).
"""

from __future__ import annotations

from collections import defaultdict

from .. import filters as f
from .. import pitch

name = "free_kicks"

FK_BUCKET = 5  # metres, for distance-to-goal buckets
OFFSIDE_BUCKET = 10  # metres, for distance-from-baseline buckets


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    total = 0
    direct_shots = 0
    crosses = 0
    short_passes = 0
    goals_direct = 0
    xg_direct = 0.0
    goals_fk_play = 0
    xg_fk_play = 0.0

    dist_shots: dict[str, int] = defaultdict(int)
    dist_passes: dict[str, int] = defaultdict(int)

    # Free kick passes
    for e in events:
        if not (f.by_team(e, team) and f.is_fk_pass(e)):
            continue
        total += 1
        loc = e.get("location")
        end_loc = e.get("pass", {}).get("end_location")
        if loc:
            d = pitch.distance_to_goal(loc)
            b = pitch.bucket(d, FK_BUCKET)
            dist_passes[str(b)] += 1
            if end_loc and pitch.is_in_box(end_loc):
                crosses += 1
            else:
                short_passes += 1

    # Free kick direct shots
    for e in events:
        if not (f.by_team(e, team) and f.is_fk_shot(e)):
            continue
        total += 1
        direct_shots += 1
        xg_direct += f.shot_xg(e)
        if f.is_goal(e):
            goals_direct += 1
        loc = e.get("location")
        if loc:
            d = pitch.distance_to_goal(loc)
            b = pitch.bucket(d, FK_BUCKET)
            dist_shots[str(b)] += 1

    # Goals / xG from free kick play patterns (includes sequences after delivery)
    for e in events:
        if not (f.by_team(e, team) and f.is_shot(e)):
            continue
        if f.play_pattern(e) == "From Free Kick":
            xg_fk_play += f.shot_xg(e)
            if f.is_goal(e):
                goals_fk_play += 1

    # Offside free kicks: scan for opponent "Pass Offside" → next FK by team
    offside_buckets: dict[str, int] = defaultdict(int)
    by_index = {e["index"]: e for e in events}
    max_index = max(by_index) if by_index else 0

    for e in events:
        if not (
            f.event_team(e) != team
            and e.get("pass", {}).get("outcome", {}).get("name") == "Pass Offside"
        ):
            continue
        for next_idx in range(e["index"] + 1, min(e["index"] + 10, max_index + 1)):
            nxt = by_index.get(next_idx)
            if nxt is None:
                continue
            if f.by_team(nxt, team) and f.is_fk_pass(nxt):
                loc = nxt.get("location")
                if loc:
                    d = pitch.distance_from_baseline(loc)
                    b = pitch.bucket(d, OFFSIDE_BUCKET)
                    offside_buckets[str(b)] += 1
                break

    return {
        "total_free_kicks": total,
        "direct_shots": direct_shots,
        "crosses": crosses,
        "short_passes": short_passes,
        "goals_direct": goals_direct,
        "goals_from_fk_play": goals_fk_play,
        "xg_direct": round(xg_direct, 3),
        "xg_from_fk_play": round(xg_fk_play, 3),
        "by_distance_bucket": {
            "shots": dict(dist_shots),
            "passes": dict(dist_passes),
        },
        "by_offside": dict(offside_buckets),
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    total = totals.get("total_free_kicks", 0)
    ds = totals.get("direct_shots", 0)
    metrics = {
        "total_free_kicks": total,
        "direct_shots": ds,
        "crosses": totals.get("crosses", 0),
        "short_passes": totals.get("short_passes", 0),
        "goals_direct": totals.get("goals_direct", 0),
        "goals_from_fk_play": totals.get("goals_from_fk_play", 0),
        "xg_direct": round(totals.get("xg_direct", 0), 3),
        "xg_from_fk_play": round(totals.get("xg_from_fk_play", 0), 3),
        "conversion_rate_direct": round(totals.get("goals_direct", 0) / ds, 3) if ds else 0,
        "xg_per_fk": round(totals.get("xg_from_fk_play", 0) / total, 3) if total else 0,
        "fk_per_match": round(total / n_matches, 2) if n_matches else 0,
    }
    breakdowns = {
        "by_distance_bucket": totals.get("by_distance_bucket", {}),
        "by_offside": totals.get("by_offside", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
