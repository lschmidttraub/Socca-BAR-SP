"""Count passes across all Barcelona UCL league phase matches.

Usage:
    python src/count_passes.py [game_id]

Without arguments, counts passes across all Barcelona matches found in matches.csv.
With a game_id argument, analyzes only that single match.

Example:
    python src/count_passes.py
    python src/count_passes.py 4028825
"""

import csv
import json
import sys
import zipfile
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATSBOMB_ZIP = DATA_DIR / "statsbomb" / "league_phase.zip"
MATCHES_CSV = DATA_DIR / "matches.csv"
TEAM_NAME = "Barcelona"


def load_events(zf: zipfile.ZipFile, game_id: str) -> list[dict]:
    """Load Statsbomb events for a match from an open zip file."""
    filename = f"{game_id}.json"
    matches = [n for n in zf.namelist() if n.endswith(filename)]
    if not matches:
        print(f"  Warning: No event file found for game ID {game_id}, skipping.")
        return []
    with zf.open(matches[0]) as f:
        return json.load(f)


def get_barcelona_game_ids() -> list[dict]:
    """Return match rows from matches.csv where Barcelona is home or away."""
    rows = []
    with open(MATCHES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if TEAM_NAME in row.get("home", "") or TEAM_NAME in row.get("away", ""):
                rows.append(row)
    return rows


def count_passes_in_events(events: list[dict]) -> dict[str, dict]:
    """Return per-team pass stats from a list of events."""
    team_stats: dict[str, dict] = {}
    for e in events:
        if e.get("type", {}).get("name") != "Pass":
            continue
        team = e.get("team", {}).get("name", "Unknown")
        player = e.get("player", {}).get("name", "Unknown")
        completed = e.get("pass", {}).get("outcome") is None

        ts = team_stats.setdefault(team, {"total": 0, "completed": 0, "players": {}})
        ts["total"] += 1
        ts["completed"] += int(completed)

        ps = ts["players"].setdefault(player, {"total": 0, "completed": 0})
        ps["total"] += 1
        ps["completed"] += int(completed)

    return team_stats


def print_match_stats(match_label: str, team_stats: dict[str, dict]) -> None:
    """Print pass stats for a single match."""
    total = sum(s["total"] for s in team_stats.values())
    print(f"\n{match_label} — {total} total passes")
    print(f"{'=' * 60}")

    for team, stats in sorted(team_stats.items()):
        pct = (stats["completed"] / stats["total"] * 100) if stats["total"] else 0
        print(f"\n  {team}: {stats['total']} passes ({pct:.1f}% completion)")
        print(
            f"    Completed: {stats['completed']}  |  Incomplete: {stats['total'] - stats['completed']}"
        )

        print(f"\n    {'Player':<30} {'Total':>6} {'Comp':>6} {'Comp%':>6}")
        print(f"    {'-' * 30} {'-' * 6} {'-' * 6} {'-' * 6}")
        for name, ps in sorted(stats["players"].items(), key=lambda x: -x[1]["total"]):
            p_pct = (ps["completed"] / ps["total"] * 100) if ps["total"] else 0
            print(
                f"    {name:<30} {ps['total']:>6} {ps['completed']:>6} {p_pct:>5.1f}%"
            )


def print_aggregate(all_barca_stats: dict[str, dict]) -> None:
    """Print aggregated Barcelona stats across all matches."""
    print(f"\n{'#' * 60}")
    print(f"AGGREGATE — {TEAM_NAME} across all league phase matches")
    print(f"{'#' * 60}")

    # Merge player stats across games
    players: dict[str, dict] = {}
    for game_players in all_barca_stats.values():
        for name, ps in game_players.items():
            agg = players.setdefault(name, {"total": 0, "completed": 0})
            agg["total"] += ps["total"]
            agg["completed"] += ps["completed"]

    total = sum(s["total"] for s in players.values())
    completed = sum(s["completed"] for s in players.values())
    pct = (completed / total * 100) if total else 0

    total = sum(s["total"] for s in players.values())
    completed = sum(s["completed"] for s in players.values())
    pct = (completed / total * 100) if total else 0

    print(
        f"\nTotal passes: {total}  |  Completed: {completed}  |  Completion: {pct:.1f}%"
    )

    print(f"\n{'Player':<40} {'Total':>6} {'Comp':>6} {'Comp%':>6}")
    print(f"{'-' * 40} {'-' * 6} {'-' * 6} {'-' * 6}")

    for name, ps in sorted(players.items(), key=lambda x: -x[1]["total"]):
        p_pct = (ps["completed"] / ps["total"] * 100) if ps["total"] else 0
        print(f"{name:<40} {ps['total']:>6} {ps['completed']:>6} {p_pct:>5.1f}%")


def main():
    single_game = sys.argv[1] if len(sys.argv) == 2 else None

    if single_game:
        game_rows = [{"statsbomb": single_game, "home": "?", "score": "?", "away": "?"}]
    else:
        game_rows = get_barcelona_game_ids()
        if not game_rows:
            print(f"No {TEAM_NAME} matches found in {MATCHES_CSV}")
            sys.exit(1)
        print(f"Found {len(game_rows)} {TEAM_NAME} matches in league phase.")

    # Collect aggregate Barcelona player stats: {game_id: {player: stats}}
    all_barca_players: dict[str, dict[str, dict]] = {}

    with zipfile.ZipFile(STATSBOMB_ZIP) as zf:
        for row in game_rows:
            game_id = row["statsbomb"]
            label = f"{row['home']} {row['score']} {row['away']}"

            events = load_events(zf, game_id)
            if not events:
                continue

            team_stats = count_passes_in_events(events)
            if single_game:
                print_match_stats(label, team_stats)

            # Collect Barcelona's player-level stats for aggregate
            for team, stats in team_stats.items():
                if TEAM_NAME in team:
                    all_barca_players[game_id] = stats["players"]

    if not single_game and len(all_barca_players) > 1:
        print_aggregate(all_barca_players)


if __name__ == "__main__":
    main()
