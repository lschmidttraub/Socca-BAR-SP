# Player Physicality — Mean Height of Top 6 Outfield Players

## What it does

Re-generates both player-physicality plots embedded in the **Player Physicality** subsection of the [BAR-SP wiki page](). Two scripts cover the two distinct views the wiki uses:

| Wiki plot                                       | Script                       |
|-------------------------------------------------|------------------------------|
| `phy01_all_teams_top6_height.png` (all teams)   | `top6_height_comparison.py`  |
| `phy02_barca_match_height.png` (per-match H2H)  | `barca_match_height.py`      |

The focus-team value (Barcelona: 187.0 cm) and the overall shape of the competition's height distribution are the key quantitative hooks for the tactical argument made on the wiki page — Barcelona compensates for below-average aerial presence through organisation and shot suppression rather than physical dominance.

### `top6_height_comparison.py`

For every team in the UCL 2025-26 dataset, computes the mean height of the 6 tallest outfield players who actually took the pitch in at least one match, then draws a ranked bar chart with Barcelona highlighted in red and the league average drawn as an extra bar in orange.

### `barca_match_height.py`

For every Barcelona fixture, draws a grouped bar chart of Barcelona's top-6 mean height versus the opponent's top-6 mean height in that specific match. Makes the matchups against Newcastle (193.3 cm) and Slavia Praha (190.2 cm) — the two clearest height disadvantages — pop out at a glance.

The two scripts are independent: each can be run on its own, and they share no helper module.

## Inputs

- **Team name** (first positional CLI argument, default: `"Barcelona"`)
- **Output path** (second positional CLI argument, default: `./all_teams_top6_height.png` or `./barca_match_height.png`)
- **Data sources**: StatsBomb lineup files (`*_lineups.json`) bundled inside `data/statsbomb/league_phase.zip` and `data/statsbomb/playoffs.zip`. `last16.zip` ships without lineup files and is therefore skipped — that's why a couple of fixtures are missing from `barca_match_height.py`'s output.

## Output

Each script writes a PNG to the output path passed on the command line and prints a small verification report to stdout.

![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/statistics/phy01_all_teams_top6_height.png)
![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/statistics/phy02_barca_match_height.png)

## Example outputs

### `top6_height_comparison.py`

```
Teams with height data : 36
Barcelona             : 187.0 cm
League average        : 189.2 cm
Plot saved to all_teams_top6_height.png
```

### `barca_match_height.py`

```
Barcelona matches with lineup data: 8
  vs Newcastle United            Barcelona   =185.8 cm  opp=193.3 cm  Δ=+7.5 cm
  vs PSG                         Barcelona   =186.3 cm  opp=186.7 cm  Δ=+0.3 cm
  vs Olympiacos Piraeus          Barcelona   =185.2 cm  opp=185.5 cm  Δ=+0.3 cm
  vs Club Brugge                 Barcelona   =184.8 cm  opp=187.2 cm  Δ=+2.3 cm
  vs Chelsea                     Barcelona   =185.8 cm  opp=185.7 cm  Δ=-0.2 cm
  vs Frankfurt                   Barcelona   =184.8 cm  opp=186.7 cm  Δ=+1.8 cm
  vs Slavia Praha                Barcelona   =185.3 cm  opp=190.2 cm  Δ=+4.8 cm
  vs København                   Barcelona   =186.3 cm  opp=185.7 cm  Δ=-0.7 cm
Plot saved to barca_match_height.png
```

## Definitions

- **Outfield player**: any lineup entry whose `positions` list exists (i.e. actually took the pitch) and does not contain `"Goalkeeper"`.
- **Top-6 metric**: the arithmetic mean of the 6 largest `player_height` values among that team's outfield players. The all-team chart deduplicates by StatsBomb `player_id` across all matches; the per-match chart uses the lineup as it stood for that one fixture.
- **League average**: unweighted mean of the per-team top-6 values (used in `top6_height_comparison.py` only).

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
