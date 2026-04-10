# Set-Piece Statistics — FC Barcelona vs. UCL Field

## What it does

Re-computes every set-piece statistic and re-renders every plot embedded
in the **Stats** section of the [BAR-SP wiki page](): Barcelona's
offensive and defensive output from free-kick and corner sequences, and
their per-match set-piece performance across the UCL 2025-26 campaign.

Each subsection of the wiki maps to one runnable script in this folder:

| Wiki subsection                               | Script                         | Plots produced     |
|-----------------------------------------------|--------------------------------|--------------------|
| Offensive Free-kick Sequences                 | `offensive_free_kicks.py`      | `of01`–`of04` (4)  |
| Offensive Corner Sequences                    | `offensive_corners.py`         | `oc01`–`oc04` (4)  |
| Defensive Free-kick Sequences                 | `defensive_free_kicks.py`      | `df01`–`df04` (4)  |
| Defensive Corner Sequences                    | `defensive_corners.py`         | `dc01`–`dc05` (6)  |
| Set-Piece Performance in FC Barcelona Matches | `per_match_performance.py`     | `matches01`–`04` (4) |

All five scripts share two lightweight helper modules:

- `_loader.py` parses `data/matches.csv` and streams StatsBomb JSONs
  out of the three ZIP archives in `data/statsbomb/` without unpacking
  them.
- `_plotting.py` provides the ranked-bar, combined-bar and per-match
  bar chart helpers used by every script. Styling matches the rest of
  the project but the helper has no dependency on the project's
  `src/stats` library — copy the whole folder and the snippet runs
  anywhere with `matplotlib` and `numpy` installed.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default:
  `./set_piece_plots/`)
- **Data sources**: StatsBomb event data
  (`data/statsbomb/league_phase.zip`, `last16.zip`, `playoffs.zip`)
  and `data/matches.csv` as the match lookup.

## Output

Each script does two things:

1. **Stdout** — a plain-text report with the focus team's metrics
   alongside the league average across all teams in the dataset.
2. **PNG plots** — saved into the output directory, one file per wiki
   anchor. Filenames match the wiki naming convention (e.g.
   `of01_total_goals_fk.png`).

`per_match_performance.py` additionally prints a per-match table with
corner and free-kick volume, attempts, xG and goals for every Barcelona
fixture — useful for spotting games like the 10-corner / 0.71 xG
Copenhagen blowout or the 0.38 xG Frankfurt free-kick haul that the
wiki singles out.

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

League average  (n = 27 teams)
------------------------------------------------------------
  Goals from FK sequences      : 1.48
  Total xG from FK sequences   : 1.47
  Attempt rate per free kick   :  41.2%
  Goal conversion per free kick:   3.6%

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

League average  (n = 27 teams)
------------------------------------------------------------
  Goals from corner seq.    : 2.22
  Attempt rate per corner   :  49.8%
  Goal rate per corner      :   6.2%
  Total xG from corners     : 2.13
  Avg xG from corners / game: 0.218

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

League average  (n = 27 teams)
------------------------------------------------------------
  Goals conceded from FK sequences : 1.81
  Avg xG conceded from FK / game   : 0.168
  Shot rate against per FK faced   :  42.5%
  Free kicks faced per game        : 4.22

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

League average  (n = 27 teams)
------------------------------------------------------------
  Goals conceded from corner seq.      : 1.81
  Avg xG conceded from corners / game  : 0.224
  Shot rate against per corner faced   :  46.0%
  Goal rate against per corner faced   :   4.4%
  Corners faced per game               : 4.74

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
2025-10-01 PSG                    |    4      1     0.05   0 |    6      2     0.10   0
2025-10-21 Olympiacos Piraeus     |    7      2     0.31   0 |    4      1     0.01   0
2025-11-05 Club Brugge            |    3      0     0.00   0 |    5      4     0.07   0
2025-11-25 Chelsea                |    0      0     0.00   0 |    6      1     0.03   0
2025-12-09 Frankfurt              |    5      2     0.12   1 |    6      2     0.38   0
2026-01-21 Slavia Praha           |    4      3     0.11   0 |    2      1     0.04   0
2026-01-28 København              |   10      8     0.71   0 |    2      5     0.58   2
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

- **Free kick (offensive)**: Free-Kick pass *or* direct Free-Kick shot
  whose event location has `x ≥ 60` on the 120 × 80 StatsBomb pitch
  (i.e. in the opponent half). Free kicks taken entirely in the
  defending third are excluded, matching the wiki's "attacking free
  kicks" framing.
- **Free kick (defensive)**: same predicate applied to the *opponent's*
  events, which by StatsBomb's coordinate convention lives in the
  defending team's own half.
- **Corner**: any `Corner`-type pass event for the team.
- **Sequence outcome**: the corresponding `play_pattern` value
  (`"From Corner"` or `"From Free Kick"`). Penalties are filtered out.
- **xG**: StatsBomb's `shot.statsbomb_xg`.
- **Ranked-bar plot**: every team's value as a vertical bar, ordered
  descending; the focus team is highlighted in red and the league mean
  drawn as an extra orange bar inserted at its sorted position.
- **Per-match plot**: grouped bars of one metric per Barcelona fixture,
  focus team in red, opponent in blue. The xG plots additionally
  annotate the actual goal count inside each bar so the reader can
  separate "good xG that scored" from "good xG that didn't".
- **Spelling drift**: a handful of teams (PSG, Bayern, Monaco,
  Leverkusen, Dortmund) have different CSV vs. event-side names and
  are dropped from the league denominator. Barcelona is unaffected.
