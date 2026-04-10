"""Offensive corner statistics for FC Barcelona vs. the UCL field.

Re-computes every number quoted in the *Offensive Set-Pieces → Corner
Sequences* subsection of the BAR-SP wiki page and saves the four
ranked-bar plots embedded there:

* ``oc01_total_goals_corner.png`` — total goals from corner sequences
* ``oc02_attempt_rate_corner.png`` — attempt rate per corner
* ``oc03_xg_corner_avg.png``       — avg xG from corner sequences per game
* ``oc04_goal_rate_corner.png``    — goal rate per corner

A corner is counted when a Corner pass restart event occurs for the team.
Sequence outputs are any non-penalty shot with
``play_pattern == "From Corner"``.

Run with::

    uv run python snippets/set_piece_statistics/offensive_corners.py
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
from _plotting import ranked_bar_chart  # noqa: E402

FOCUS_TEAM = "Barcelona"
DEFAULT_OUTPUT_DIR = Path("set_piece_plots")


def _empty_record() -> dict:
    return {
        "matches": 0,
        "corners": 0,
        "shots": 0,
        "goals": 0,
        "xg": 0.0,
    }


def collect_per_team() -> dict[str, dict]:
    """Return ``{team_name: record}`` aggregated across all matches."""
    records: dict[str, dict] = defaultdict(_empty_record)

    for match in iter_matches():
        for csv_team in (match.home, match.away):
            if not csv_team:
                continue
            sb_team = resolve_team_name(csv_team, match)
            if sb_team is None:
                continue

            rec = records[csv_team]
            rec["matches"] += 1

            for e in match.events:
                if event_team(e) != sb_team:
                    continue
                if is_corner_pass(e):
                    rec["corners"] += 1
                if (
                    is_shot(e)
                    and play_pattern(e) == "From Corner"
                    and not is_penalty_shot(e)
                ):
                    rec["shots"] += 1
                    rec["xg"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals"] += 1

    return dict(records)


def derive_rates(rec: dict) -> dict:
    c = rec["corners"]
    n = rec["matches"]
    return {
        "attempt_rate": rec["shots"] / c if c else 0.0,
        "goal_rate": rec["goals"] / c if c else 0.0,
        "xg_per_game": rec["xg"] / n if n else 0.0,
    }


def league_average(records: dict[str, dict]) -> dict:
    """Arithmetic mean across teams — the baseline used in the wiki."""
    teams = [r for r in records.values() if r["matches"] > 0]
    n = len(teams)
    if n == 0:
        return {}
    attempt_rates = [derive_rates(r)["attempt_rate"] for r in teams]
    goal_rates = [derive_rates(r)["goal_rate"] for r in teams]
    xg_per_game = [derive_rates(r)["xg_per_game"] for r in teams]
    return {
        "teams": n,
        "mean_corners": sum(r["corners"] for r in teams) / n,
        "mean_goals": sum(r["goals"] for r in teams) / n,
        "mean_xg": sum(r["xg"] for r in teams) / n,
        "mean_attempt_rate": sum(attempt_rates) / n,
        "mean_goal_rate": sum(goal_rates) / n,
        "mean_xg_per_game": sum(xg_per_game) / n,
    }


def print_report(focus_team: str = FOCUS_TEAM) -> None:
    records = collect_per_team()
    focus = records.get(focus_team)
    if focus is None:
        raise SystemExit(f"No data for team {focus_team!r}")

    rates = derive_rates(focus)
    avg = league_average(records)

    print(f"Offensive corner sequences — {focus_team}")
    print("-" * 60)
    print(f"  Matches played            : {focus['matches']}")
    print(f"  Corners taken             : {focus['corners']}")
    print(f"  Shots from corner seq.    : {focus['shots']}")
    print(f"  Goals from corner seq.    : {focus['goals']}")
    print(f"  Attempt rate per corner   : {rates['attempt_rate'] * 100:5.1f}%")
    print(f"  Goal rate per corner      : {rates['goal_rate'] * 100:5.1f}%")
    print(f"  Total xG from corners     : {focus['xg']:.2f}")
    print(f"  Avg xG from corners / game: {rates['xg_per_game']:.3f}")
    print()
    print(f"League average  (n = {avg['teams']} teams)")
    print("-" * 60)
    print(f"  Goals from corner seq.    : {avg['mean_goals']:.2f}")
    print(f"  Attempt rate per corner   : {avg['mean_attempt_rate'] * 100:5.1f}%")
    print(f"  Goal rate per corner      : {avg['mean_goal_rate'] * 100:5.1f}%")
    print(f"  Total xG from corners     : {avg['mean_xg']:.2f}")
    print(f"  Avg xG from corners / game: {avg['mean_xg_per_game']:.3f}")


def save_plots(focus_team: str, output_dir: Path) -> None:
    """Render and save the four wiki plots for offensive corners."""
    records = collect_per_team()
    if focus_team not in records:
        raise SystemExit(f"No data for team {focus_team!r}")

    teams_with_data = {t: r for t, r in records.items() if r["matches"] > 0}

    goals = {t: float(r["goals"]) for t, r in teams_with_data.items()}
    attempt_rate = {t: derive_rates(r)["attempt_rate"] for t, r in teams_with_data.items()}
    xg_per_game = {t: derive_rates(r)["xg_per_game"] for t, r in teams_with_data.items()}
    goal_rate = {t: derive_rates(r)["goal_rate"] for t, r in teams_with_data.items()}

    print()
    print(f"Saving plots to {output_dir}/ ...")
    ranked_bar_chart(
        goals,
        title="Total Goals from Corner Sequences",
        ylabel="Goals (all games)",
        focus_team=focus_team,
        output_path=output_dir / "oc01_total_goals_corner.png",
        fmt=".0f",
    )
    ranked_bar_chart(
        attempt_rate,
        title="Attempts per Corner (ratio of corners that generated a shot)",
        ylabel="Attempts / corner",
        focus_team=focus_team,
        output_path=output_dir / "oc02_attempt_rate_corner.png",
        fmt=".3f",
    )
    ranked_bar_chart(
        xg_per_game,
        title="Average xG from Corner Sequences per Game",
        ylabel="xG / game",
        focus_team=focus_team,
        output_path=output_dir / "oc03_xg_corner_avg.png",
        fmt=".3f",
    )
    ranked_bar_chart(
        goal_rate,
        title="Goals per Corner (ratio of corners that generated a goal)",
        ylabel="Goals / corner",
        focus_team=focus_team,
        output_path=output_dir / "oc04_goal_rate_corner.png",
        fmt=".4f",
    )


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    print_report(team)
    save_plots(team, out)
