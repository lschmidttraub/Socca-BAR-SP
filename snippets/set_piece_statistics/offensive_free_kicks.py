"""Offensive free-kick statistics for FC Barcelona vs. the UCL field.

Re-computes every number quoted in the *Offensive Set-Pieces → Free-kick
Sequences* subsection of the BAR-SP wiki page and saves the four
ranked-bar plots embedded there:

* ``of01_total_goals_fk.png``     — total goals from FK sequences
* ``of02_attempt_rate_fk.png``    — attempt rate per FK
* ``of03_total_xg_fk.png``        — total xG from FK sequences
* ``of04_goal_rate_fk.png``       — goal conversion per FK

A free kick is counted when a Free-Kick pass or a direct Free-Kick shot
occurs in the opponent half (x ≥ 60 on the 120×80 StatsBomb pitch).
A free-kick *sequence* contribution is any non-penalty shot with
``play_pattern == "From Free Kick"``.

Run with::

    uv run python snippets/set_piece_statistics/offensive_free_kicks.py

Default focus team is Barcelona; pass a different name as the first CLI
argument to retarget. Plots are written to ``./set_piece_plots/`` by
default — pass an output directory as the second positional argument
to override.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Allow running as ``python snippets/set_piece_statistics/offensive_free_kicks.py``
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _loader import (  # noqa: E402
    event_team,
    in_opponent_half,
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
from _plotting import ranked_bar_chart  # noqa: E402

FOCUS_TEAM = "Barcelona"
DEFAULT_OUTPUT_DIR = Path("set_piece_plots")


def _empty_record() -> dict:
    return {
        "matches": 0,
        "free_kicks": 0,      # attacking FK set pieces (opponent half)
        "shots": 0,           # shots from "From Free Kick" possessions
        "goals": 0,
        "xg": 0.0,
    }


def collect_per_team() -> dict[str, dict]:
    """Return ``{team_name: record}`` across every match in matches.csv."""
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

                # Count set-piece restart (pass or direct shot) in opponent half
                if (is_free_kick_pass(e) or is_free_kick_shot(e)) and in_opponent_half(e):
                    rec["free_kicks"] += 1

                # Count sequence outcomes — non-penalty shot from a FK possession
                if (
                    is_shot(e)
                    and play_pattern(e) == "From Free Kick"
                    and not is_penalty_shot(e)
                ):
                    rec["shots"] += 1
                    rec["xg"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals"] += 1

    return dict(records)


def derive_rates(rec: dict) -> dict:
    """Compute ratios (shot rate, goal rate) from an aggregated record."""
    fk = rec["free_kicks"]
    return {
        "attempt_rate": rec["shots"] / fk if fk else 0.0,
        "goal_rate": rec["goals"] / fk if fk else 0.0,
    }


def league_average(records: dict[str, dict]) -> dict:
    """Mean across all teams — the comparison baseline used in the wiki."""
    teams = [r for r in records.values() if r["matches"] > 0]
    n = len(teams)
    if n == 0:
        return {}
    mean = lambda field: sum(r[field] for r in teams) / n  # noqa: E731
    shot_rates = [derive_rates(r)["attempt_rate"] for r in teams]
    goal_rates = [derive_rates(r)["goal_rate"] for r in teams]
    return {
        "teams": n,
        "mean_free_kicks": mean("free_kicks"),
        "mean_goals": mean("goals"),
        "mean_xg": mean("xg"),
        "mean_attempt_rate": sum(shot_rates) / n,
        "mean_goal_rate": sum(goal_rates) / n,
    }


def print_report(focus_team: str = FOCUS_TEAM) -> None:
    records = collect_per_team()
    focus = records.get(focus_team)
    if focus is None:
        raise SystemExit(f"No data for team {focus_team!r}")

    focus_rates = derive_rates(focus)
    avg = league_average(records)

    print(f"Offensive free-kick sequences — {focus_team}")
    print("-" * 60)
    print(f"  Matches played               : {focus['matches']}")
    print(f"  Attacking free kicks         : {focus['free_kicks']}")
    print(f"  Shots from FK sequences      : {focus['shots']}")
    print(f"  Goals from FK sequences      : {focus['goals']}")
    print(f"  Total xG from FK sequences   : {focus['xg']:.2f}")
    print(f"  Attempt rate per free kick   : {focus_rates['attempt_rate'] * 100:5.1f}%")
    print(f"  Goal conversion per free kick: {focus_rates['goal_rate'] * 100:5.1f}%")
    print()
    print(f"League average  (n = {avg['teams']} teams)")
    print("-" * 60)
    print(f"  Goals from FK sequences      : {avg['mean_goals']:.2f}")
    print(f"  Total xG from FK sequences   : {avg['mean_xg']:.2f}")
    print(f"  Attempt rate per free kick   : {avg['mean_attempt_rate'] * 100:5.1f}%")
    print(f"  Goal conversion per free kick: {avg['mean_goal_rate'] * 100:5.1f}%")


def save_plots(focus_team: str, output_dir: Path) -> None:
    """Render and save the four wiki plots for offensive free kicks."""
    records = collect_per_team()
    if focus_team not in records:
        raise SystemExit(f"No data for team {focus_team!r}")

    teams_with_data = {t: r for t, r in records.items() if r["matches"] > 0}

    goals = {t: float(r["goals"]) for t, r in teams_with_data.items()}
    total_xg = {t: float(r["xg"]) for t, r in teams_with_data.items()}
    attempt_rate = {t: derive_rates(r)["attempt_rate"] for t, r in teams_with_data.items()}
    goal_rate = {t: derive_rates(r)["goal_rate"] for t, r in teams_with_data.items()}

    print()
    print(f"Saving plots to {output_dir}/ ...")
    ranked_bar_chart(
        goals,
        title="Total Goals from Free Kick Sequences",
        ylabel="Goals (all games)",
        focus_team=focus_team,
        output_path=output_dir / "of01_total_goals_fk.png",
        fmt=".0f",
    )
    ranked_bar_chart(
        attempt_rate,
        title="Attempts per Free Kick (ratio of FKs that generated a shot)",
        ylabel="Attempts / FK",
        focus_team=focus_team,
        output_path=output_dir / "of02_attempt_rate_fk.png",
        fmt=".3f",
    )
    ranked_bar_chart(
        total_xg,
        title="Total xG from Free Kick Sequences",
        ylabel="xG (all games)",
        focus_team=focus_team,
        output_path=output_dir / "of03_total_xg_fk.png",
        fmt=".2f",
    )
    ranked_bar_chart(
        goal_rate,
        title="Goals per Free Kick (ratio of FKs that generated a goal)",
        ylabel="Goals / FK",
        focus_team=focus_team,
        output_path=output_dir / "of04_goal_rate_fk.png",
        fmt=".4f",
    )


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    print_report(team)
    save_plots(team, out)
