"""Per-match set-piece performance for FC Barcelona.

Re-computes the per-match corner and free-kick numbers quoted in the
*Set-Piece Performance in FC Barcelona Matches* subsection of the
BAR-SP wiki page. For every Barcelona fixture it reports:

* corners taken, corner-sequence attempts (shots), corner-sequence xG, goals
* opponent-half free kicks, FK-sequence attempts, FK-sequence xG, goals

The wiki specifically calls out:

* København (attacking pressure: 10 corners, 8 shots, 0.71 xG, 0 goals)
* Club Brugge & Chelsea (almost no attacking corner output)
* Frankfurt (FK: 0.38 xG, 0 goals)
* København (FK: 0.58 xG, 2 goals)
* Newcastle (FK: 0.40 xG, 1 goal)

Run with::

    uv run python snippets/set_piece_statistics/per_match_performance.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    event_team,
    in_opponent_half,
    is_corner_pass,
    is_free_kick_pass,
    is_free_kick_shot,
    is_goal,
    is_penalty_shot,
    is_shot,
    iter_matches,
    play_pattern,
    resolve_team_name,
    shot_xg,
)

FOCUS_TEAM = "Barcelona"


def collect(focus_team: str = FOCUS_TEAM) -> list[dict]:
    """Return a per-match stat record for every focus-team fixture."""
    out: list[dict] = []
    for match in iter_matches():
        if focus_team not in (match.home, match.away):
            continue
        sb_team = resolve_team_name(focus_team, match)
        if sb_team is None:
            continue

        opponent = match.opponent_of(focus_team)
        rec = {
            "date": match.date,
            "opponent": opponent,
            "corners": 0,
            "shots_corner": 0,
            "xg_corner": 0.0,
            "goals_corner": 0,
            "free_kicks": 0,
            "shots_fk": 0,
            "xg_fk": 0.0,
            "goals_fk": 0,
        }

        for e in match.events:
            if event_team(e) != sb_team:
                continue

            if is_corner_pass(e):
                rec["corners"] += 1
            if (is_free_kick_pass(e) or is_free_kick_shot(e)) and in_opponent_half(e):
                rec["free_kicks"] += 1

            if is_shot(e) and not is_penalty_shot(e):
                pattern = play_pattern(e)
                if pattern == "From Corner":
                    rec["shots_corner"] += 1
                    rec["xg_corner"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_corner"] += 1
                elif pattern == "From Free Kick":
                    rec["shots_fk"] += 1
                    rec["xg_fk"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_fk"] += 1

        out.append(rec)

    out.sort(key=lambda r: r["date"])
    return out


def print_report(focus_team: str = FOCUS_TEAM) -> None:
    rows = collect(focus_team)
    if not rows:
        raise SystemExit(f"No matches found for team {focus_team!r}")

    header = (
        f"Per-match offensive set pieces — {focus_team}"
        f"   ({len(rows)} matches)"
    )
    print(header)
    print("-" * 95)
    print(
        f"{'Date':10} {'Opponent':22}"
        f" | {'Corn':>4} {'ShotsC':>6} {'xGcorner':>8} {'GcC':>3}"
        f" | {'FKs':>4} {'ShotsF':>6} {'xGfk':>8} {'GfK':>3}"
    )
    print("-" * 95)

    totals = {
        "corners": 0, "shots_corner": 0, "xg_corner": 0.0, "goals_corner": 0,
        "free_kicks": 0, "shots_fk": 0, "xg_fk": 0.0, "goals_fk": 0,
    }

    for r in rows:
        print(
            f"{r['date']:10} {r['opponent'][:22]:22}"
            f" | {r['corners']:4d} {r['shots_corner']:6d}"
            f" {r['xg_corner']:8.2f} {r['goals_corner']:3d}"
            f" | {r['free_kicks']:4d} {r['shots_fk']:6d}"
            f" {r['xg_fk']:8.2f} {r['goals_fk']:3d}"
        )
        for k in totals:
            totals[k] += r[k]

    print("-" * 95)
    print(
        f"{'TOTAL':<33}"
        f" | {totals['corners']:4d} {totals['shots_corner']:6d}"
        f" {totals['xg_corner']:8.2f} {totals['goals_corner']:3d}"
        f" | {totals['free_kicks']:4d} {totals['shots_fk']:6d}"
        f" {totals['xg_fk']:8.2f} {totals['goals_fk']:3d}"
    )


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    print_report(team)
