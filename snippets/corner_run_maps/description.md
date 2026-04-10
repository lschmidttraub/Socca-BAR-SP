# Corner Run Maps — Attacking Player Movement During Barcelona Corners

## What it does

Generates per-corner three-panel figures showing the movement of
Barcelona's attacking outfield players during every offensive corner
that has SkillCorner tracking data. Each figure captures a 5-second
window (t-2.5 s to t+2.5 s) around the corner kick and shows:

| Panel     | Content                                                     |
|-----------|-------------------------------------------------------------|
| 01 Starts | Player start positions 2.5 s before the kick               |
| 02 Paths  | Interpolated movement paths with gradient-fade and arrows   |
| 03 Ends   | Player end positions 2.5 s after the kick                   |

These are the movement-analysis maps embedded in the *Movement of
Attacking Players* subsection of the [BAR-SP wiki page](). Four
specific corners are shown in the wiki (vs Sparta Praha, Copenhagen,
Newcastle, Frankfurt), but the script generates maps for all 41 tracked
corners across the campaign.

The script also writes a CSV summary table with per-player start/end
coordinates and displacement for every corner, useful for downstream
aggregation.

| File                | Role                                                    |
|---------------------|---------------------------------------------------------|
| `_loader.py`        | Data loading, track extraction, path processing         |
| `corner_runs.py`    | Three-panel plotting, CSV summary, CLI entry point      |

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default:
  `./corner_run_maps/`)
- **Data sources**:
  - `data/matches.csv` — match lookup with `statsbomb` and
    `skillcorner` columns
  - StatsBomb event ZIPs (`data/statsbomb/league_phase.zip`,
    `last16.zip`, `playoffs.zip`) — identifies corner passes and
    shot/goal outcomes
  - SkillCorner per-match ZIPs
    (`data/skillcorner/{skillcorner_id}.zip`) — frame-by-frame player
    and ball tracking (JSONL) plus match metadata (JSON)

## Output

1. **One PNG per corner** in `corner_run_maps/corner_run_maps/`,
   named `corner_{skillcorner_id}_{index:02d}_{side}_{clock}_{result}.png`.
2. **Summary CSV** at `corner_run_maps/corner_run_summary.csv` — one
   row per tracked player per corner, with start/end coordinates and
   displacement.
3. **Stdout** — corner count and side/shot/goal breakdown.

## Example outputs

### `corner_runs.py`

```
Collecting Barcelona corner tracking windows from SkillCorner...
  Tracked corners : 41
    top (right)   : 16
    bottom (left) : 25
    Shots         : 15
    Goals         : 2

Outputs saved to corner_run_maps/
  41 corner maps  → corner_run_maps/corner_run_maps/
  summary CSV     → corner_run_maps/corner_run_summary.csv
```

Selected filenames matching the wiki figures:

```
corner_2050711_01_right_2848_shot.png     (vs Sparta Praha — shot)
corner_2051683_04_right_1452_shot.png     (vs Copenhagen — shot)
corner_2059201_05_right_3957_no_shot.png  (vs Newcastle — no shot)
corner_2047362_03_left_5217_goal.png      (vs Frankfurt — goal)
```

### CSV summary (first rows)

```
skillcorner_match_id,statsbomb_match_id,opponent,corner_index,...,start_x,start_y,end_x,end_y,delta_x,delta_y
2031733,4028847,Newcastle United,1,...,109.95,52.39,116.82,50.51,6.87,-1.88
2031733,4028847,Newcastle United,1,...,113.93,45.01,113.38,40.4,-0.55,-4.61
...
```

## Definitions

- **Tracking window**: the 5-second interval from t-2.5 s to t+2.5 s
  around the StatsBomb corner-pass timestamp, aligned to the
  SkillCorner tracking clock via period and elapsed seconds.
- **Tracked attacker**: a non-goalkeeper Barcelona player whose
  tracking data exists at all three reference times (t-2.5 s, t=0,
  t+2.5 s) and whose maximum x-coordinate exceeds 72.0 (past the
  halfway line on the StatsBomb 120x80 pitch). The corner kicker is
  excluded.
- **Corner side**: inferred from the ball's y-coordinate at kick time.
  `y >= 40` = top (right-side corner in StatsBomb convention);
  `y < 40` = bottom (left-side corner).
- **Result**: determined by scanning the same-possession, same-period
  events after the corner pass for Barcelona shots. `"Goal"` if any
  shot has outcome `"Goal"`, `"Shot"` if any shot exists, `"No shot"`
  otherwise.
- **Attempt player**: marked with a gold star on the figure. Matched
  by normalised name against the StatsBomb shooter(s) within the
  corner possession.
- **Coordinate system**: SkillCorner tracking (metres, origin at pitch
  centre) is converted to StatsBomb 120x80 coordinates for plotting
  via `mplsoccer`. Attacking direction is always normalised to the
  right.
- **SkillCorner data**: requires per-match ZIP files in
  `data/skillcorner/` containing `{match_id}.json` (metadata),
  `{match_id}_tracking_extrapolated.jsonl` (frame-by-frame positions).
  Matches without SkillCorner tracking are silently skipped.
