# Corner Routine Efficiency — Barcelona vs League Average

## What it does

Re-creates the two grouped-bar charts embedded in the *Offensive Corners* subsection of the [BAR-SP wiki page](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP). Each Barcelona corner kick is classified as either a **short** routine (opener pass length ≤ 15 yards OR opener end-location inside the attacking penalty box) or a **crossed** routine (everything else). Shots from the `"From Corner"` play pattern (penalties excluded) are attributed to the most recent same-team corner with a smaller event index, so each shot counts against exactly one opener.

The script then aggregates attempts per corner and xG per corner for both categories and compares Barcelona against the league average computed across every team in the dataset that has at least one corner of the relevant type. Two PNGs are written plus a plain-text stdout report.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default: `./corner_routine_plots/`)
- **Data sources**: `data/matches.csv` as the match lookup plus `data/statsbomb/league_phase.zip`, `last16.zip` and `playoffs.zip` streamed without being extracted to disk.

## Output

1. **Stdout** — Barcelona's per-corner attempt and xG rates for both short and crossed routines, alongside the league average and the sample size (number of teams contributing to each category's mean).
2. **PNG plots** — saved into the output directory:
   - `attempts_per_corner_bars.png`
   - `xg_per_corner_bars.png`

![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/attempts_per_corner_bars.png)
![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/xg_per_corner_bars.png)

## Example outputs

### `routine_efficiency.py`

```
Corner routine efficiency — Barcelona
------------------------------------------------------------
  Short corners taken       : 11
  Crossed corners taken     : 36
  Attempts / short corner   : 0.545
  Attempts / crossed corner : 0.417
  xG / short corner         : 0.037
  xG / crossed corner       : 0.041

League average (short n = 22, cross n = 27)
------------------------------------------------------------
  Attempts / short corner   : 0.518
  Attempts / crossed corner : 0.496
  xG / short corner         : 0.054
  xG / crossed corner       : 0.048

Saving plots to corner_routine_plots/ ...
  saved corner_routine_plots/attempts_per_corner_bars.png
  saved corner_routine_plots/xg_per_corner_bars.png
```

## Definitions

- **Short corner**: opener pass length ≤ 15 yards OR opener end-location inside the attacking penalty box (x ≥ 102, 18 ≤ y ≤ 62 after normalising to attacking-right on the StatsBomb 120 × 80 pitch).
- **Crossed corner**: any corner that is not short.
- **Attempts per corner**: shots with `play_pattern == "From Corner"` (penalties excluded), assigned to the most recent same-team corner with a smaller event index, divided by the number of corners of that routine type.
- **xG per corner**: total `shot.statsbomb_xg` from the same "From Corner" shots, divided by the number of corners of that routine type.
- **League average**: arithmetic mean of the per-team per-corner rate across every team with at least one corner of the relevant type. Teams whose `matches.csv` spelling differs from their StatsBomb event name (PSG vs "Paris Saint-Germain", Bayern vs "Bayern Munich", Monaco vs "AS Monaco", Leverkusen vs "Bayer Leverkusen", Dortmund vs "Borussia Dortmund") are dropped from the denominator. Barcelona is spelled consistently and therefore unaffected.

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
