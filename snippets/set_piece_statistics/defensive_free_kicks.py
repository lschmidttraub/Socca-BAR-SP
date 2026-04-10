"""Defensive free-kick statistics for FC Barcelona vs. the UCL field.

Re-computes every number quoted in the *Defensive Set-Pieces → Free-kick
Sequences* subsection of the BAR-SP wiki page and saves the four
ranked-bar plots embedded there:

* ``df01_total_goals_conceded_fk.png``  — total goals conceded from FK
* ``df02_xg_conceded_fk_avg.png``       — avg xG conceded from FK / game
* ``df03_attempt_rate_conceded_fk.png`` — attempt rate conceded per FK
* ``df04_free_kicks_conceded_avg.png``  — average FKs faced per game

A *defensive* free kick is an opponent free-kick restart (pass or direct
shot) that happens in the defending team's own half. In StatsBomb
coordinates the ball is always placed so that the team in possession
attacks toward x = 120, so opponent free kicks in our own half have
x ≥ 60 from their perspective.

Run with::

    uv run python snippets/set_piece_statistics/defensive_free_kicks.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

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
        "fks_conceded": 0,   # opponent FK restarts in our own half
        "shots_conceded": 0, # opponent shots "From Free Kick"
        "goals_conceded": 0,
        "xg_conceded": 0.0,
    }


def collect_per_team() -> dict[str, dict]:
    """Return ``{team_name: record}`` of defensive FK totals.

    Only the defending team's name is resolved against the events. The
    opponent's events are simply "any event not by the defending team",
    so we never need to know what the opponent is called — which keeps
    us from dropping matches where the opponent's CSV spelling differs
    from its event-side spelling.
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

                # Opponent free-kick restart in *their* opponent half
                # ≡ our own half.
                if (is_free_kick_pass(e) or is_free_kick_shot(e)) and in_opponent_half(e):
                    rec["fks_conceded"] += 1

                if (
                    is_shot(e)
                    and play_pattern(e) == "From Free Kick"
                    and not is_penalty_shot(e)
                ):
                    rec["shots_conceded"] += 1
                    rec["xg_conceded"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_conceded"] += 1

    return dict(records)


def derive_rates(rec: dict) -> dict:
    fk = rec["fks_conceded"]
    n = rec["matches"]
    return {
        "shot_rate_against": rec["shots_conceded"] / fk if fk else 0.0,
        "goal_rate_against": rec["goals_conceded"] / fk if fk else 0.0,
        "xg_per_game": rec["xg_conceded"] / n if n else 0.0,
        "fks_per_game": fk / n if n else 0.0,
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
        "mean_fks_per_game": sum(x["fks_per_game"] for x in rates) / n,
    }


def print_report(focus_team: str = FOCUS_TEAM) -> None:
    records = collect_per_team()
    focus = records.get(focus_team)
    if focus is None:
        raise SystemExit(f"No data for team {focus_team!r}")

    rates = derive_rates(focus)
    avg = league_average(records)

    print(f"Defensive free-kick sequences — {focus_team}")
    print("-" * 60)
    print(f"  Matches played                   : {focus['matches']}")
    print(f"  Free kicks faced in own half     : {focus['fks_conceded']}")
    print(f"  Free kicks faced per game        : {rates['fks_per_game']:.2f}")
    print(f"  Shots conceded from FK sequences : {focus['shots_conceded']}")
    print(f"  Goals conceded from FK sequences : {focus['goals_conceded']}")
    print(f"  xG conceded from FK sequences    : {focus['xg_conceded']:.2f}")
    print(f"  Avg xG conceded from FK / game   : {rates['xg_per_game']:.3f}")
    print(f"  Shot rate against per FK faced   : {rates['shot_rate_against'] * 100:5.1f}%")
    print()
    print(f"League average  (n = {avg['teams']} teams)")
    print("-" * 60)
    print(f"  Goals conceded from FK sequences : {avg['mean_goals_conceded']:.2f}")
    print(f"  Avg xG conceded from FK / game   : {avg['mean_xg_per_game']:.3f}")
    print(f"  Shot rate against per FK faced   : {avg['mean_shot_rate_against'] * 100:5.1f}%")
    print(f"  Free kicks faced per game        : {avg['mean_fks_per_game']:.2f}")


def save_plots(focus_team: str, output_dir: Path) -> None:
    """Render and save the four wiki plots for defensive free kicks."""
    records = collect_per_team()
    if focus_team not in records:
        raise SystemExit(f"No data for team {focus_team!r}")

    teams_with_data = {t: r for t, r in records.items() if r["matches"] > 0}

    goals_conceded = {t: float(r["goals_conceded"]) for t, r in teams_with_data.items()}
    xg_per_game = {t: derive_rates(r)["xg_per_game"] for t, r in teams_with_data.items()}
    shot_rate = {t: derive_rates(r)["shot_rate_against"] for t, r in teams_with_data.items()}
    fks_per_game = {t: derive_rates(r)["fks_per_game"] for t, r in teams_with_data.items()}

    print()
    print(f"Saving plots to {output_dir}/ ...")
    ranked_bar_chart(
        goals_conceded,
        title="Total Goals Conceded from Free Kick Sequences",
        ylabel="Goals conceded (all games)",
        focus_team=focus_team,
        output_path=output_dir / "df01_total_goals_conceded_fk.png",
        fmt=".0f",
    )
    ranked_bar_chart(
        xg_per_game,
        title="Average xG Conceded from Free Kick Sequences per Game",
        ylabel="xG conceded / game",
        focus_team=focus_team,
        output_path=output_dir / "df02_xg_conceded_fk_avg.png",
        fmt=".3f",
    )
    ranked_bar_chart(
        shot_rate,
        title="Attempts Conceded per Free Kick Faced",
        ylabel="Attempts conceded / FK",
        focus_team=focus_team,
        output_path=output_dir / "df03_attempt_rate_conceded_fk.png",
        fmt=".3f",
    )
    ranked_bar_chart(
        fks_per_game,
        title="Average Free Kicks Faced in Own Half per Game",
        ylabel="Free kicks conceded / game",
        focus_team=focus_team,
        output_path=output_dir / "df04_free_kicks_conceded_avg.png",
        fmt=".2f",
    )


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    print_report(team)
    save_plots(team, out)
