"""Count passes in a Barcelona UCL match using Statsbomb event data.

Usage:
    python src/count_passes.py <game_id>

Example:
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


def load_events(game_id: str) -> list[dict]:
    """Load Statsbomb events for a match from the league_phase zip."""
    filename = f"{game_id}.json"
    with zipfile.ZipFile(STATSBOMB_ZIP) as zf:
        # Find the matching file (may be nested in a subdirectory)
        matches = [n for n in zf.namelist() if n.endswith(filename)]
        if not matches:
            print(f"Error: No event file found for game ID {game_id}")
            print(
                f"Available files: {[n for n in zf.namelist() if n.endswith('.json')][:10]}..."
            )
            sys.exit(1)
        with zf.open(matches[0]) as f:
            return json.load(f)


def get_match_info(game_id: str) -> dict | None:
    """Look up match info from matches.csv."""
    if not MATCHES_CSV.exists():
        return None
    with open(MATCHES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Try common column names for the statsbomb match ID
            for col in reader.fieldnames:
                if row.get(col, "").strip() == game_id:
                    return row
    return None


def count_passes(events: list[dict]) -> None:
    """Count and display pass statistics from Statsbomb events."""
    passes = [e for e in events if e.get("type", {}).get("name") == "Pass"]
    total = len(passes)

    # Group by team
    team_passes: dict[str, list[dict]] = {}
    for p in passes:
        team = p.get("team", {}).get("name", "Unknown")
        team_passes.setdefault(team, []).append(p)

    print(f"\nTotal passes: {total}")
    print(f"{'=' * 50}")

    for team, team_p in sorted(team_passes.items()):
        completed = sum(
            1
            for p in team_p
            if p.get("pass", {}).get("outcome") is None  # no outcome = complete
        )
        incomplete = len(team_p) - completed
        pct = (completed / len(team_p) * 100) if team_p else 0

        print(f"\n{team}: {len(team_p)} passes ({pct:.1f}% completion)")
        print(f"  Completed: {completed}")
        print(f"  Incomplete: {incomplete}")

        # Per-player breakdown
        player_passes: dict[str, dict] = {}
        for p in team_p:
            name = p.get("player", {}).get("name", "Unknown")
            stats = player_passes.setdefault(name, {"total": 0, "completed": 0})
            stats["total"] += 1
            if p.get("pass", {}).get("outcome") is None:
                stats["completed"] += 1

        print(f"\n  {'Player':<30} {'Total':>6} {'Comp':>6} {'Comp%':>6}")
        print(f"  {'-' * 30} {'-' * 6} {'-' * 6} {'-' * 6}")
        for name, stats in sorted(player_passes.items(), key=lambda x: -x[1]["total"]):
            p_pct = (stats["completed"] / stats["total"] * 100) if stats["total"] else 0
            print(
                f"  {name:<30} {stats['total']:>6} {stats['completed']:>6} {p_pct:>5.1f}%"
            )


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    game_id = sys.argv[1]

    # Show match info if available
    match_info = get_match_info(game_id)
    if match_info:
        print(f"Match info: {match_info}")

    print(f"\nLoading events for game {game_id}...")
    events = load_events(game_id)
    print(f"Loaded {len(events)} events.")

    count_passes(events)


if __name__ == "__main__":
    main()
