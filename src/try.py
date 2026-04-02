"""
try.py - Explore Barcelona UCL StatsBomb event data.

Usage:
    python src/try.py                     # list all Barcelona games
    python src/try.py <match_id>          # summarise event types for one game
    python src/try.py <match_id> <type_id>  # print events of a given type
    python src/try.py penalties             # list all penalties for/against Barcelona
    python src/try.py freekicks             # list all Barcelona free kicks + whether a goal followed
    python src/try.py fk-takers            # breakdown of who takes free kicks (<40m) by type & side
"""

import json
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "statsbomb" / "league_phase"


def load_lineup(match_id: str) -> list | None:
    path = DATA_DIR / f"{match_id}_lineups.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_events(match_id: str) -> list:
    with open(DATA_DIR / f"{match_id}.json", encoding="utf-8") as f:
        return json.load(f)


def team_names_from_events(events: list) -> list[str]:
    seen = []
    for e in events:
        name = e.get("team", {}).get("name")
        if name and name not in seen:
            seen.append(name)
        if len(seen) == 2:
            break
    return seen


def teams(lineup: list | None, events: list | None = None) -> tuple[str, str]:
    if lineup:
        names = [t["team_name"] for t in lineup]
    elif events:
        names = team_names_from_events(events)
    else:
        return "Barcelona", "Unknown"
    barca = next((n for n in names if n == "Barcelona"), names[0])
    opp = next((n for n in names if n != "Barcelona"), names[1] if len(names) > 1 else "Unknown")
    return barca, opp


def all_match_ids() -> list[str]:
    """Return all match IDs that have an event file, sorted."""
    return sorted(
        p.stem for p in DATA_DIR.glob("*.json")
        if not p.stem.endswith("_lineups")
    )


def barca_matches() -> list[tuple[str, str]]:
    """Return (match_id, opponent) for all Barcelona games."""
    result = []
    for mid in all_match_ids():
        lineup = load_lineup(mid)
        if lineup:
            team_names = [t["team_name"] for t in lineup]
            if "Barcelona" not in team_names:
                continue
            opp = next(n for n in team_names if n != "Barcelona")
        else:
            events = load_events(mid)
            names = team_names_from_events(events)
            if "Barcelona" not in names:
                continue
            opp = next((n for n in names if n != "Barcelona"), "Unknown")
        result.append((mid, opp))
    return result


def list_games():
    barca_matches_list = barca_matches()

    print(f"{'Match ID':<12}  Opponent")
    print("-" * 40)
    for mid, opp in barca_matches_list:
        print(f"{mid:<12}  {opp}")
    print(f"\n{len(barca_matches_list)} Barcelona games found.")


def summarise_game(match_id: str):
    events = load_events(match_id)
    lineup = load_lineup(match_id)
    _, opp = teams(lineup, events)

    print(f"\nMatch {match_id}  —  Barcelona vs {opp}")
    print(f"Total events: {len(events)}\n")

    counter: Counter = Counter()
    for e in events:
        key = (e["type"]["id"], e["type"]["name"], e["team"]["name"])
        counter[key] += 1

    print(f"{'ID':>4}  {'Type':<35}  {'Team':<25}  Count")
    print("-" * 75)
    for (tid, tname, team), count in sorted(counter.items(), key=lambda x: (-x[1], x[0][0])):
        print(f"{tid:>4}  {tname:<35}  {team:<25}  {count}")


def print_events(match_id: str, type_id: int):
    events = load_events(match_id)
    lineup = load_lineup(match_id)
    _, opp = teams(lineup, events)

    filtered = [e for e in events if e["type"]["id"] == type_id]
    print(f"\nMatch {match_id}  —  Barcelona vs {opp}")
    print(f"Event type {type_id} ({filtered[0]['type']['name'] if filtered else '?'}): {len(filtered)} events\n")

    for e in filtered:
        minute = e.get("minute", "?")
        second = e.get("second", "?")
        team = e["team"]["name"]
        player = e.get("player", {}).get("name", "—")
        print(f"  {minute:>3}:{second:02}  {team:<25}  {player}")


def list_penalties():
    print(f"{'Match ID':<12}  {'Opponent':<25}  {'For/Against':<12}  {'Min':>3}  {'Player':<25}  Outcome")
    print("-" * 100)
    total_for = total_against = 0
    for mid, opp in barca_matches():
        events = load_events(mid)
        for e in events:
            if e["type"]["id"] != 16:  # Shot
                continue
            shot = e.get("shot", {})
            if shot.get("type", {}).get("name") != "Penalty":
                continue
            team = e["team"]["name"]
            minute = e.get("minute", "?")
            player = e.get("player", {}).get("name", "—")
            outcome = shot.get("outcome", {}).get("name", "?")
            if team == "Barcelona":
                side = "FOR"
                total_for += 1
            else:
                side = "AGAINST"
                total_against += 1
            print(f"{mid:<12}  {opp:<25}  {side:<12}  {minute:>3}  {player:<25}  {outcome}")

    print(f"\nTotal: {total_for} for Barcelona, {total_against} against Barcelona")


def fk_distance_m(event: dict) -> float | None:
    """Distance from event location to goal centre in metres (StatsBomb pitch is in yards)."""
    loc = event.get("location")
    if not loc:
        return None
    x, y = loc[0], loc[1]
    # Goal centre is at (120, 40) yards on a 120x80 yard pitch
    dist_yards = ((120 - x) ** 2 + (40 - y) ** 2) ** 0.5
    return dist_yards * 0.9144


def list_freekicks(max_distance_m: float | None = None):
    if max_distance_m is not None:
        print(f"Filtering: free kicks within {max_distance_m}m of goal\n")
    print(f"{'Match ID':<12}  {'Opponent':<25}  {'Min':>3}  {'Player':<25}  {'Type':<10}  {'Dist(m)':>7}  Goal?")
    print("-" * 105)
    total = goal_count = 0
    for mid, opp in barca_matches():
        events = load_events(mid)

        # Build a set of possession numbers that ended in a goal
        goal_possessions = {
            e["possession"] for e in events
            if e["type"]["id"] == 16
            and e.get("shot", {}).get("outcome", {}).get("name") == "Goal"
        }

        for e in events:
            if e["team"]["name"] != "Barcelona":
                continue

            # Free kick pass or direct free kick shot
            is_fk_pass = (
                e["type"]["id"] == 30
                and e.get("pass", {}).get("type", {}).get("name") == "Free Kick"
            )
            is_fk_shot = (
                e["type"]["id"] == 16
                and e.get("shot", {}).get("type", {}).get("name") == "Free Kick"
            )
            if not (is_fk_pass or is_fk_shot):
                continue

            dist = fk_distance_m(e)
            if max_distance_m is not None and (dist is None or dist > max_distance_m):
                continue

            minute = e.get("minute", "?")
            player = e.get("player", {}).get("name", "—")
            fk_type = "Shot" if is_fk_shot else "Pass"
            goal = "GOAL" if e["possession"] in goal_possessions else "-"
            dist_str = f"{dist:.1f}" if dist is not None else "?"
            if goal == "GOAL":
                goal_count += 1
            total += 1
            print(f"{mid:<12}  {opp:<25}  {minute:>3}  {player:<25}  {fk_type:<10}  {dist_str:>7}  {goal}")

    print(f"\nTotal: {total} Barcelona free kicks, {goal_count} led to a goal ({100*goal_count//total if total else 0}%)")


def fk_side(event: dict) -> str:
    """Left / Center / Right based on y-coordinate (pitch is 80 yards wide)."""
    loc = event.get("location")
    if not loc:
        return "?"
    y = loc[1]
    if y < 80 / 3:
        return "Left"
    elif y > 160 / 3:
        return "Right"
    return "Center"


def fk_takers(max_distance_m: float = 40.0):
    # stats[player][type][side] = count
    from collections import defaultdict
    stats: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for mid, _ in barca_matches():
        events = load_events(mid)
        for e in events:
            if e["team"]["name"] != "Barcelona":
                continue
            is_fk_pass = (
                e["type"]["id"] == 30
                and e.get("pass", {}).get("type", {}).get("name") == "Free Kick"
            )
            is_fk_shot = (
                e["type"]["id"] == 16
                and e.get("shot", {}).get("type", {}).get("name") == "Free Kick"
            )
            if not (is_fk_pass or is_fk_shot):
                continue
            dist = fk_distance_m(e)
            if dist is None or dist > max_distance_m:
                continue
            player = e.get("player", {}).get("name", "Unknown")
            fk_type = "Shot" if is_fk_shot else "Pass"
            side = fk_side(e)
            stats[player][fk_type][side] += 1

    # Flatten into rows and sort by total desc
    rows = []
    for player, types in stats.items():
        s = types["Shot"]
        p = types["Pass"]
        total = sum(s.values()) + sum(p.values())
        rows.append((player, s["Left"], s["Center"], s["Right"], p["Left"], p["Center"], p["Right"], total))
    rows.sort(key=lambda r: -r[7])

    print(f"Barcelona free kick takers within {max_distance_m}m of goal\n")
    print(f"{'Player':<30}  {'S-L':>4}  {'S-C':>4}  {'S-R':>4}  {'P-L':>4}  {'P-C':>4}  {'P-R':>4}  {'Tot':>4}")
    print(f"{'':30}  {'Shot Left':>4}  {'Shot Ctr':>4}  {'Shot Rgt':>4}  {'Pass Left':>4}  {'Pass Ctr':>4}  {'Pass Rgt':>4}  {'Total':>5}")
    print("-" * 85)
    for player, sl, sc, sr, pl, pc, pr, total in rows:
        print(f"{player:<30}  {sl:>8}  {sc:>8}  {sr:>8}  {pl:>9}  {pc:>8}  {pr:>8}  {total:>5}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not DATA_DIR.exists():
        print(f"Data directory not found: {DATA_DIR}")
        sys.exit(1)
    max_dist = float(args[1]) if len(args) > 1 else 40.0
    fk_takers(max_dist)
    if len(args) == 0:
        list_games()
    elif args[0] == "penalties":
        list_penalties()
    elif args[0] == "freekicks":
        max_dist = float(args[1]) if len(args) > 1 else None
        list_freekicks(max_dist)
    elif args[0] == "fk-takers":
        max_dist = float(args[1]) if len(args) > 1 else 40.0
        fk_takers(max_dist)
    elif len(args) == 1:
        (summarise_game(args[0]))
    elif len(args) == 2:
        print_events(args[0], int(args[1]))
    else:
        print(__doc__)
