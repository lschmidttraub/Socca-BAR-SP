"""Defensive corner statistics for FC Barcelona vs. the UCL field.

Re-computes every number quoted in the *Defensive Set-Pieces → Corner
Sequences* subsection of the BAR-SP wiki page:

* corners conceded per game
* goals conceded from corner sequences
* average xG conceded from corner sequences per game
* share of corners faced that generated a shot
* share of corners faced that led to a goal

Run with::

    uv run python snippets/set_piece_statistics/defensive_corners.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    event_team,
    is_corner_pass,
    is_goal,
    is_penalty_shot,
    is_shot,
    iter_matches,
    play_pattern,
    resolve_team_name,
    shot_xg,
)

FOCUS_TEAM = "Barcelona"


def _empty_record() -> dict:
    return {
        "matches": 0,
        "corners_conceded": 0,
        "shots_conceded": 0,
        "goals_conceded": 0,
        "xg_conceded": 0.0,
    }


def collect_per_team() -> dict[str, dict]:
    """Return ``{team_name: record}`` of defensive corner totals.

    Only the defending team is resolved against the event-side names;
    opponent events are just "anything not by the defending team", so
    CSV ↔ event spelling drift on the opponent side never causes
    matches to be dropped.
    """
    records: dict[str, dict] = defaultdict(_empty_record)

    for match in iter_matches():
        for csv_team in (match.home, match.away):
            team_sb = resolve_team_name(csv_team, match)
            if team_sb is None:
                continue

            rec = records[csv_team]
            rec["matches"] += 1

            for e in match.events:
                et = event_team(e)
                if not et or et == team_sb:
                    continue
                if is_corner_pass(e):
                    rec["corners_conceded"] += 1
                if (
                    is_shot(e)
                    and play_pattern(e) == "From Corner"
                    and not is_penalty_shot(e)
                ):
                    rec["shots_conceded"] += 1
                    rec["xg_conceded"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_conceded"] += 1

    return dict(records)


def derive_rates(rec: dict) -> dict:
    c = rec["corners_conceded"]
    n = rec["matches"]
    return {
        "shot_rate_against": rec["shots_conceded"] / c if c else 0.0,
        "goal_rate_against": rec["goals_conceded"] / c if c else 0.0,
        "xg_per_game": rec["xg_conceded"] / n if n else 0.0,
        "corners_per_game": c / n if n else 0.0,
    }


def league_average(records: dict[str, dict]) -> dict:
    teams = [r for r in records.values() if r["matches"] > 0]
    n = len(teams)
    if n == 0:
        return {}
    rates = [derive_rates(r) for r in teams]
    return {
        "teams": n,
        "mean_goals_conceded": sum(r["goals_conceded"] for r in teams) / n,
        "mean_xg_per_game": sum(x["xg_per_game"] for x in rates) / n,
        "mean_shot_rate_against": sum(x["shot_rate_against"] for x in rates) / n,
        "mean_goal_rate_against": sum(x["goal_rate_against"] for x in rates) / n,
        "mean_corners_per_game": sum(x["corners_per_game"] for x in rates) / n,
    }


def print_report(focus_team: str = FOCUS_TEAM) -> None:
    records = collect_per_team()
    focus = records.get(focus_team)
    if focus is None:
        raise SystemExit(f"No data for team {focus_team!r}")

    rates = derive_rates(focus)
    avg = league_average(records)

    print(f"Defensive corner sequences — {focus_team}")
    print("-" * 60)
    print(f"  Matches played                       : {focus['matches']}")
    print(f"  Corners faced                        : {focus['corners_conceded']}")
    print(f"  Corners faced per game               : {rates['corners_per_game']:.2f}")
    print(f"  Shots conceded from corner seq.      : {focus['shots_conceded']}")
    print(f"  Goals conceded from corner seq.      : {focus['goals_conceded']}")
    print(f"  xG conceded from corner seq.         : {focus['xg_conceded']:.2f}")
    print(f"  Avg xG conceded from corners / game  : {rates['xg_per_game']:.3f}")
    print(f"  Shot rate against per corner faced   : {rates['shot_rate_against'] * 100:5.1f}%")
    print(f"  Goal rate against per corner faced   : {rates['goal_rate_against'] * 100:5.1f}%")
    print()
    print(f"League average  (n = {avg['teams']} teams)")
    print("-" * 60)
    print(f"  Goals conceded from corner seq.      : {avg['mean_goals_conceded']:.2f}")
    print(f"  Avg xG conceded from corners / game  : {avg['mean_xg_per_game']:.3f}")
    print(f"  Shot rate against per corner faced   : {avg['mean_shot_rate_against'] * 100:5.1f}%")
    print(f"  Goal rate against per corner faced   : {avg['mean_goal_rate_against'] * 100:5.1f}%")
    print(f"  Corners faced per game               : {avg['mean_corners_per_game']:.2f}")


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    print_report(team)
