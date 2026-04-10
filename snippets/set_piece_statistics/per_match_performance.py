"""Per-match set-piece performance for FC Barcelona.

Re-computes the per-match corner and free-kick numbers quoted in the
*Set-Piece Performance in FC Barcelona Matches* subsection of the
BAR-SP wiki page and saves the four per-match plots embedded there:

* ``matches01_corners.png``       — corners taken (focus team vs opponent)
* ``matches02_corners_xg.png``    — xG from corner sequences with goals annotated
* ``matches03_free_kicks.png``    — opponent-half free kicks (focus team vs opponent)
* ``matches04_free_kicks_xg.png`` — xG from FK sequences with goals annotated

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

from _loader import (
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
from _plotting import per_match_bar_chart

FOCUS_TEAM = "Barcelona"
DEFAULT_OUTPUT_DIR = Path("set_piece_plots")


def collect(focus_team: str = FOCUS_TEAM) -> list[dict]:
    """Return a per-match stat record for every focus-team fixture.

    Each record contains both focus-team and opponent counts so the
    plots can show them side-by-side. Opponent events are inferred as
    "any event whose team is not the focus team's resolved StatsBomb
    name", which sidesteps the spelling-drift problem entirely.
    """
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
            "corners": 0, "shots_corner": 0, "xg_corner": 0.0, "goals_corner": 0,
            "free_kicks": 0, "shots_fk": 0, "xg_fk": 0.0, "goals_fk": 0,
            "opp_corners": 0, "opp_shots_corner": 0, "opp_xg_corner": 0.0, "opp_goals_corner": 0,
            "opp_free_kicks": 0, "opp_shots_fk": 0, "opp_xg_fk": 0.0, "opp_goals_fk": 0,
        }

        for e in match.events:
            et = event_team(e)
            if not et:
                continue
            is_focus = et == sb_team

            if is_corner_pass(e):
                rec["corners" if is_focus else "opp_corners"] += 1
            if (is_free_kick_pass(e) or is_free_kick_shot(e)) and in_opponent_half(e):
                rec["free_kicks" if is_focus else "opp_free_kicks"] += 1

            if is_shot(e) and not is_penalty_shot(e):
                pattern = play_pattern(e)
                if pattern == "From Corner":
                    rec["shots_corner" if is_focus else "opp_shots_corner"] += 1
                    rec["xg_corner" if is_focus else "opp_xg_corner"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_corner" if is_focus else "opp_goals_corner"] += 1
                elif pattern == "From Free Kick":
                    rec["shots_fk" if is_focus else "opp_shots_fk"] += 1
                    rec["xg_fk" if is_focus else "opp_xg_fk"] += shot_xg(e)
                    if is_goal(e):
                        rec["goals_fk" if is_focus else "opp_goals_fk"] += 1

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


def save_plots(focus_team: str, output_dir: Path) -> None:
    """Render and save the four per-match wiki plots."""
    rows = collect(focus_team)
    if not rows:
        raise SystemExit(f"No matches found for team {focus_team!r}")

    matches = [
        {
            "label": f"vs {r['opponent']}",
            "team_corners": r["corners"],
            "opp_corners": r["opp_corners"],
            "team_xg_corner": r["xg_corner"],
            "opp_xg_corner": r["opp_xg_corner"],
            "team_goals_corner": r["goals_corner"],
            "opp_goals_corner": r["opp_goals_corner"],
            "team_fks": r["free_kicks"],
            "opp_fks": r["opp_free_kicks"],
            "team_xg_fk": r["xg_fk"],
            "opp_xg_fk": r["opp_xg_fk"],
            "team_goals_fk": r["goals_fk"],
            "opp_goals_fk": r["opp_goals_fk"],
        }
        for r in rows
    ]

    print()
    print(f"Saving plots to {output_dir}/ ...")
    per_match_bar_chart(
        matches,
        title=f"{focus_team} — Corners per Match (focus team vs opponent)",
        ylabel="Corners",
        focus_team=focus_team,
        team_key="team_corners",
        opp_key="opp_corners",
        output_path=output_dir / "matches01_corners.png",
        fmt=".0f",
    )
    per_match_bar_chart(
        matches,
        title=f"{focus_team} — xG from Corner Sequences per Match",
        ylabel="xG",
        focus_team=focus_team,
        team_key="team_xg_corner",
        opp_key="opp_xg_corner",
        output_path=output_dir / "matches02_corners_xg.png",
        fmt=".2f",
        fixed_y_max=2.0,
        team_goals_key="team_goals_corner",
        opp_goals_key="opp_goals_corner",
    )
    per_match_bar_chart(
        matches,
        title=f"{focus_team} — Free Kicks in Opponent Half per Match",
        ylabel="Free kicks",
        focus_team=focus_team,
        team_key="team_fks",
        opp_key="opp_fks",
        output_path=output_dir / "matches03_free_kicks.png",
        fmt=".0f",
    )
    per_match_bar_chart(
        matches,
        title=f"{focus_team} — xG from Free Kick Sequences per Match",
        ylabel="xG",
        focus_team=focus_team,
        team_key="team_xg_fk",
        opp_key="opp_xg_fk",
        output_path=output_dir / "matches04_free_kicks_xg.png",
        fmt=".2f",
        fixed_y_max=2.0,
        team_goals_key="team_goals_fk",
        opp_goals_key="opp_goals_fk",
    )


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    print_report(team)
    save_plots(team, out)
