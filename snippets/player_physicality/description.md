# Player Physicality — Mean Height of Top 6 Outfield Players

## What it does

Re-generates the player-physicality plot embedded in the **Player
Physicality** subsection of the [BAR-SP wiki page]():

![all_teams_top6_height]()

For every team in the UCL 2025-26 dataset the script computes the mean
height of the 6 tallest outfield players who actually took the pitch
in at least one match, then draws a ranked bar chart with Barcelona
highlighted in red and the league average drawn as an extra bar in
orange.

The focus-team value (Barcelona: 187.0 cm) and the overall shape of
the competition's height distribution are the key quantitative hooks
for the tactical argument made on the wiki page — Barcelona
compensates for below-average aerial presence through organisation
and shot suppression rather than physical dominance.

## Inputs

- **Team name** (first positional CLI argument, default: `"Barcelona"`)
- **Output path** (second positional CLI argument, default:
  `./all_teams_top6_height.png`)
- **Data sources**: StatsBomb lineup files (`*_lineups.json`) bundled
  inside `data/statsbomb/league_phase.zip` and
  `data/statsbomb/playoffs.zip`. `last16.zip` ships without lineup
  files and is therefore skipped.

## Output

- **Image**: a PNG bar chart written to the path passed on the command
  line (default `./all_teams_top6_height.png`).
- **Console**: prints the number of teams with height data, the focus
  team's top-6 mean height, and the overall league mean so the wiki
  numbers can be verified at a glance.

```
Teams with height data : 36
Barcelona             : 187.0 cm
League average        : 189.2 cm
Plot saved to all_teams_top6_height.png
```

## Definitions

- **Outfield player**: any lineup entry whose `positions` list exists
  (i.e. actually took the pitch) and does not contain `"Goalkeeper"`.
- **Top-6 metric**: the arithmetic mean of the 6 largest
  `player_height` values among that team's unique outfield players,
  deduplicated by StatsBomb `player_id` across all matches.
- **League average**: unweighted mean of the 36 per-team top-6 values.

