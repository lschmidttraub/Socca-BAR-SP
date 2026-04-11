# Set-Piece Statistics — FC Barcelona vs. UCL Field

## What it does

Re-computes every set-piece statistic and re-renders every plot embedded in the **Stats** section of the [BAR-SP wiki page](): Barcelona's offensive and defensive output from free-kick and corner sequences, and their per-match set-piece performance across the UCL 2025-26 campaign.

Each subsection of the wiki maps to one runnable script in this folder:

| Wiki subsection                               | Script                         | Plots produced     |
|-----------------------------------------------|--------------------------------|--------------------|
| Offensive Free-kick Sequences                 | `offensive_free_kicks.py`      | `of01`–`of04` (4)  |
| Offensive Corner Sequences                    | `offensive_corners.py`         | `oc01`–`oc04` (4)  |
| Defensive Free-kick Sequences                 | `defensive_free_kicks.py`      | `df01`–`df04` (4)  |
| Defensive Corner Sequences                    | `defensive_corners.py`         | `dc01`–`dc05` (6)  |
| Set-Piece Performance in FC Barcelona Matches | `per_match_performance.py`     | `matches01`–`04` (4) |

All five scripts share two lightweight helper modules:

- `_loader.py` parses `data/matches.csv` and streams StatsBomb JSONs out of the three ZIP archives in `data/statsbomb/` without unpacking them.
- `_plotting.py` provides the ranked-bar, combined-bar and per-match bar chart helpers used by every script. Styling matches the rest of the project but the helper has no dependency on the project's `src/stats` library — copy the whole folder and the snippet runs anywhere with `matplotlib` and `numpy` installed.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default: `./set_piece_plots/`)
- **Data sources**: StatsBomb event data (`data/statsbomb/league_phase.zip`, `last16.zip`, `playoffs.zip`) and `data/matches.csv` as the match lookup.

## Output

Each script does two things:

1. **Stdout** — a plain-text report with the focus team's metrics alongside the league average across all teams in the dataset.
2. **PNG plots** — saved into the output directory, one file per wiki anchor. Filenames match the wiki naming convention (e.g. `of01_total_goals_fk.png`).

`per_match_performance.py` additionally prints a per-match table with corner and free-kick volume, attempts, xG and goals for every Barcelona fixture — useful for spotting games like the 10-corner / 0.71 xG Copenhagen blowout or the 0.38 xG Frankfurt free-kick haul that the wiki singles out.

The plots can be seen in the [statistics plot section](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/statistics_plot).

## Example outputs

### `offensive_free_kicks.py`

```
Offensive free-kick sequences — Barcelona
------------------------------------------------------------
  Matches played               : 10
  Attacking free kicks         : 44
  Shots from FK sequences      : 21
  Goals from FK sequences      : 3
  Total xG from FK sequences   : 1.82
  Attempt rate per free kick   :  47.7%
  Goal conversion per free kick:   6.8%

League average  (n = 36 teams)
------------------------------------------------------------
  Goals from FK sequences      : 1.86
  Total xG from FK sequences   : 1.67
  Attempt rate per free kick   :  44.9%
  Goal conversion per free kick:   4.8%

Saving plots to set_piece_plots/ ...
  saved set_piece_plots/of01_total_goals_fk.png
  saved set_piece_plots/of02_attempt_rate_fk.png
  saved set_piece_plots/of03_total_xg_fk.png
  saved set_piece_plots/of04_goal_rate_fk.png
```

### `offensive_corners.py`

```
Offensive corner sequences — Barcelona
------------------------------------------------------------
  Matches played            : 10
  Corners taken             : 47
  Shots from corner seq.    : 21
  Goals from corner seq.    : 2
  Attempt rate per corner   :  44.7%
  Goal rate per corner      :   4.3%
  Total xG from corners     : 1.89
  Avg xG from corners / game: 0.189

League average  (n = 36 teams)
------------------------------------------------------------
  Goals from corner seq.    : 2.17
  Attempt rate per corner   :  47.8%
  Goal rate per corner      :   4.8%
  Total xG from corners     : 2.20
  Avg xG from corners / game: 0.223

Saving plots to set_piece_plots/ ...
  saved set_piece_plots/oc01_total_goals_corner.png
  saved set_piece_plots/oc02_attempt_rate_corner.png
  saved set_piece_plots/oc03_xg_corner_avg.png
  saved set_piece_plots/oc04_goal_rate_corner.png
```

### `defensive_free_kicks.py`

```
Defensive free-kick sequences — Barcelona
------------------------------------------------------------
  Matches played                   : 10
  Free kicks faced in own half     : 42
  Free kicks faced per game        : 4.20
  Shots conceded from FK sequences : 14
  Goals conceded from FK sequences : 0
  xG conceded from FK sequences    : 0.87
  Avg xG conceded from FK / game   : 0.087
  Shot rate against per FK faced   :  33.3%

League average  (n = 36 teams)
------------------------------------------------------------
  Goals conceded from FK sequences : 1.86
  Avg xG conceded from FK / game   : 0.180
  Shot rate against per FK faced   :  44.2%
  Free kicks faced per game        : 4.16

Saving plots to set_piece_plots/ ...
  saved set_piece_plots/df01_total_goals_conceded_fk.png
  saved set_piece_plots/df02_xg_conceded_fk_avg.png
  saved set_piece_plots/df03_attempt_rate_conceded_fk.png
  saved set_piece_plots/df04_free_kicks_conceded_avg.png
```

### `defensive_corners.py`

```
Defensive corner sequences — Barcelona
------------------------------------------------------------
  Matches played                       : 10
  Corners faced                        : 38
  Corners faced per game               : 3.80
  Shots conceded from corner seq.      : 12
  Goals conceded from corner seq.      : 1
  xG conceded from corner seq.         : 1.92
  Avg xG conceded from corners / game  : 0.192
  Shot rate against per corner faced   :  31.6%
  Goal rate against per corner faced   :   2.6%

League average  (n = 36 teams)
------------------------------------------------------------
  Goals conceded from corner seq.      : 2.19
  Avg xG conceded from corners / game  : 0.226
  Shot rate against per corner faced   :  47.6%
  Goal rate against per corner faced   :   4.9%
  Corners faced per game               : 4.75

Saving plots to set_piece_plots/ ...
  saved set_piece_plots/dc01_total_goals_conceded_corner.png
  saved set_piece_plots/dc02_xg_conceded_corner_avg.png
  saved set_piece_plots/dc03_attempt_rate_conceded_corner.png
  saved set_piece_plots/dc041_goal_rate_conceded_corner.png
  saved set_piece_plots/dc042_goals_xg_conceded_combined_corners.png
  saved set_piece_plots/dc05_corners_conceded_avg.png
```

### `per_match_performance.py`

```
Per-match offensive set pieces — Barcelona   (10 matches)
-----------------------------------------------------------------------------------------------
Date       Opponent               | Corn ShotsC xGcorner GcC |  FKs ShotsF     xGfk GfK
-----------------------------------------------------------------------------------------------
2025-09-18 Newcastle United       |    4      1     0.04   0 |    7      2     0.15   0
2025-10-01 Paris Saint-Germain    |    4      1     0.05   0 |    6      2     0.10   0
2025-10-21 Olympiacos             |    7      2     0.31   0 |    4      1     0.01   0
2025-11-05 Club Brugge            |    3      0     0.00   0 |    5      4     0.07   0
2025-11-25 Chelsea                |    0      0     0.00   0 |    6      1     0.03   0
2025-12-09 Eintracht Frankfurt    |    5      2     0.12   1 |    6      2     0.38   0
2026-01-21 Slavia Praha           |    4      3     0.11   0 |    2      1     0.04   0
2026-01-28 FC København           |   10      8     0.71   0 |    2      5     0.58   2
2026-03-10 Newcastle United       |    4      1     0.11   0 |    2      1     0.05   0
2026-03-18 Newcastle United       |    6      3     0.44   1 |    4      2     0.40   1
-----------------------------------------------------------------------------------------------
TOTAL                             |   47     21     1.89   2 |   44     21     1.82   3

Saving plots to set_piece_plots/ ...
  saved set_piece_plots/matches01_corners.png
  saved set_piece_plots/matches02_corners_xg.png
  saved set_piece_plots/matches03_free_kicks.png
  saved set_piece_plots/matches04_free_kicks_xg.png
```

## Definitions

- **Free kick (offensive)**: Free-Kick pass *or* direct Free-Kick shot whose event location has `x ≥ 60` on the 120 × 80 StatsBomb pitch (i.e. in the opponent half). Free kicks taken entirely in the defending third are excluded, matching the wiki's "attacking free kicks" framing.
- **Free kick (defensive)**: same predicate applied to the *opponent's* events, which by StatsBomb's coordinate convention lives in the defending team's own half.
- **Corner**: any `Corner`-type pass event for the team.
- **Sequence outcome**: the corresponding `play_pattern` value (`"From Corner"` or `"From Free Kick"`). Penalties are filtered out.
- **xG**: StatsBomb's `shot.statsbomb_xg`.
- **Ranked-bar plot**: every team's value as a vertical bar, ordered descending; the focus team is highlighted in red and the league mean drawn as an extra orange bar inserted at its sorted position.
- **Per-match plot**: grouped bars of one metric per Barcelona fixture, focus team in red, opponent in blue. The xG plots additionally annotate the actual goal count inside each bar so the reader can separate "good xG that scored" from "good xG that didn't".
- **Name normalisation**: `_loader.py` maps CSV team names to their StatsBomb event spelling at load time (e.g. PSG → Paris Saint-Germain, Frankfurt → Eintracht Frankfurt). All 36 teams are included in league averages.

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
