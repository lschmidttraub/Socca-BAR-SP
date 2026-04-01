"""Penalty analysis.

Metrics
-------
total_penalties, goals, saved, missed, xg_total.

Derived: conversion_rate, xg_per_penalty.

Breakdowns: by_taker (player -> taken / scored).
"""

from __future__ import annotations

from collections import defaultdict

from .. import filters as f

name = "penalties"


def analyze_match(events: list[dict], team: str) -> dict:
    """Return raw additive counts for one team in one match."""
    total = 0
    goals = 0
    saved = 0
    missed = 0
    xg_total = 0.0
    by_taker: dict[str, dict[str, int]] = defaultdict(lambda: {"taken": 0, "scored": 0})

    for e in events:
        if not (f.by_team(e, team) and f.is_penalty_shot(e)):
            continue
        total += 1
        xg_total += f.shot_xg(e)
        player = f.event_player(e)
        by_taker[player]["taken"] += 1

        outcome = f.shot_outcome(e)
        if outcome == "Goal":
            goals += 1
            by_taker[player]["scored"] += 1
        elif outcome == "Saved":
            saved += 1
        else:
            missed += 1

    return {
        "total_penalties": total,
        "goals": goals,
        "saved": saved,
        "missed": missed,
        "xg_total": round(xg_total, 3),
        "by_taker": dict(by_taker),
    }


def summarize(totals: dict, n_matches: int) -> dict:
    """Compute derived metrics from aggregated totals."""
    total = totals.get("total_penalties", 0)
    metrics = {
        "total_penalties": total,
        "goals": totals.get("goals", 0),
        "saved": totals.get("saved", 0),
        "missed": totals.get("missed", 0),
        "xg_total": round(totals.get("xg_total", 0), 3),
        "conversion_rate": round(totals.get("goals", 0) / total, 3) if total else 0,
        "xg_per_penalty": round(totals.get("xg_total", 0) / total, 3) if total else 0,
    }
    breakdowns = {
        "by_taker": totals.get("by_taker", {}),
    }
    return {"metrics": metrics, "breakdowns": breakdowns}
