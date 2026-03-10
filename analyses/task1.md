# Task 1: Pass Analysis

AI tools were used in the creation of the code for this analysis.
The full code is available on [GitHub](https://github.com/lschmidttraub/Socca-BAR-SP)

## Presentation

We create a simple script to count the number of passes by Barcelona throughout all the games available in the dataset.

We first calculate the IDs of the games played by Barcelona:

```python
def get_barcelona_game_ids() -> list[dict]:
    """Return match rows from matches.csv where Barcelona is home or away."""
    rows = []
    with open(MATCHES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if TEAM_NAME in row.get("home", "") or TEAM_NAME in row.get("away", ""):
                rows.append(row)
    return rows
```

We can then load the event data:

```python
def load_events(zf: zipfile.ZipFile, game_id: str) -> list[dict]:
    """Load Statsbomb events for a match from an open zip file."""
    filename = f"{game_id}.json"
    matches = [n for n in zf.namelist() if n.endswith(filename)]
    if not matches:
        print(f"  Warning: No event file found for game ID {game_id}, skipping.")
        return []
    with zf.open(matches[0]) as f:
        return json.load(f)
```

The following function then counts the number of passes on a total and per-player basis for each game:

```python
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

```

Finally, we print the aggregate calculation as follows:

```python
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

    print(f"\nTotal passes: {total}  |  Completed: {completed}  |  Completion: {pct:.1f}%")

    print(f"\n{'Player':<50} {'Total':>6} {'Comp':>6} {'Comp%':>6}")
    print(f"{'-' * 50} {'-' * 6} {'-' * 6} {'-' * 6}")

    for name, ps in sorted(players.items(), key=lambda x: -x[1]["total"]):
        p_pct = (ps["completed"] / ps["total"] * 100) if ps["total"] else 0
        print(f"{name:<50} {ps['total']:>6} {ps['completed']:>6} {p_pct:>5.1f}%")
```

## Results

The final output of the script is:

```
Found 8 Barcelona matches in league phase.

############################################################
AGGREGATE — Barcelona across all league phase matches
############################################################

Total passes: 5181  |  Completed: 4506  |  Completion: 87.0%

Player                                    Total   Comp  Comp%
---------------------------------------- ------ ------ ------
Jules Koundé                                586    531  90.6%
Eric García Martret                         527    482  91.5%
Pau Cubarsí Paredes                         493    449  91.1%
Frenkie de Jong                             417    392  94.0%
Gerard Martín Langreo                       391    339  86.7%
Pedro González López                        351    312  88.9%
Alejandro Balde Martínez                    348    314  90.2%
Lamine Yamal Nasraoui Ebana                 332    269  81.0%
Fermin Lopez Marin                          258    221  85.7%
Marcus Rashford                             220    164  74.5%
Ronald Federico Araújo da Silva             217    188  86.6%
Joan García Pons                            171    140  81.9%
Raphael Dias Belloli                        168    125  74.4%
Marc Casadó Torras                          166    151  91.0%
Daniel Olmo Carvajal                        137    117  85.4%
Wojciech Szczęsny                           113     94  83.2%
Robert Lewandowski                           70     47  67.1%
Ferrán Torres García                         66     41  62.1%
Marc Bernal Casas                            61     54  88.5%
Roony Bardghji                               43     37  86.0%
Andreas Christensen                          24     20  83.3%
Pedro Fernández Sarmiento                   22     19  86.4%
```
