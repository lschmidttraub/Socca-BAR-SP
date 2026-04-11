# Corner Spatial Maps — FC Barcelona Offensive Corners

## What it does

Re-creates the three spatial maps embedded in the *Offensive Corners* subsection of the [BAR-SP wiki page](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP): the half-pitch **Spatial Profile** (delivery routes, endpoint zones and first-shot locations), the dark-themed **Delivery Endpoints by Side** and the **First Touch Map**. Together they describe *where* Barcelona deliver their corners, which target zones they favour on each side and what the receiving player does with the first touch — the three questions that frame the wiki's "controlled second-phase construction" reading of Barcelona's corner routine.

Each plot is built from the same corner-sequence extraction: identifying every `Corner`-type pass, walking forward in the possession to find the *meaningful delivery* (direct pass itself for long corners; the first long pass or shot after a short corner), classifying its endpoint into one of six target zones, and recording the first tracked team touch afterwards.

| Wiki plot                          | Script                             |
|------------------------------------|------------------------------------|
| `spatial_profile.png`              | `spatial_profile.py`               |
| `delivery_endpoints_by_side.png`   | `delivery_endpoints_by_side.py`    |
| `corner_first_touch_map.png`       | `first_touch_map.py`               |

All three scripts share `_loader.py`, which streams StatsBomb match JSONs out of the three ZIPs in `data/statsbomb/` (without unpacking them) and returns one rich dict per Barcelona corner.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default: `./corner_spatial_plots/`)
- **Data sources**: StatsBomb event data (`data/statsbomb/league_phase.zip`, `last16.zip`, `playoffs.zip`) and `data/matches.csv` as the match lookup.

## Output

Each script does two things:

1. **Stdout** — a compact report of the corner count plus the breakdown relevant to that plot (routine mix for `spatial_profile.py`, side split + zone mix for `delivery_endpoints_by_side.py`, first-touch kind tally for `first_touch_map.py`).
2. **One PNG file** written into the output directory:
   - `corner_spatial_plots/spatial_profile.png`
   - `corner_spatial_plots/delivery_endpoints_by_side.png`
   - `corner_spatial_plots/corner_first_touch_map.png`

![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/spatial_profile.png)
![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/delivery_endpoints_by_side.png)
![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/corner_first_touch_map.png)

## Example outputs

### `spatial_profile.py`

```
Corner spatial profile - Barcelona
------------------------------------------------------------
Collecting corner sequences from StatsBomb events ...
  Corners processed          : 47
  First-shot attempts        : 17
    Direct inswing    :  31
    Direct outswing   :   1
    Direct other      :   4
    Short corner      :  11

Saving plot to corner_spatial_plots/ ...
  saved corner_spatial_plots/spatial_profile.png
```

### `delivery_endpoints_by_side.py`

```
Corner delivery endpoints (by side) - Barcelona
------------------------------------------------------------
Collecting corner sequences from StatsBomb events ...
  Corners processed   : 47
    Left-side corners : 23
    Right-side corners: 24
    Near post         :  10
    Central six-yard  :  16
    Far post          :   5
    Penalty spot      :   2
    Edge of box       :  10
    Wide recycle      :   4

Saving plot to corner_spatial_plots/ ...
  saved corner_spatial_plots/delivery_endpoints_by_side.png
```

### `first_touch_map.py`

```
Corner first-touch map - Barcelona
------------------------------------------------------------
Collecting corner sequences from StatsBomb events ...
  Corners processed        : 47
  First touches (tracked)  : 35
    Shot  :  11
    Pass  :  11
    Carry :  13
  No tracked first touch   : 12

Saving plot to corner_spatial_plots/ ...
  saved corner_spatial_plots/corner_first_touch_map.png
```

## Definitions

- **Routine type**: *Direct inswing* / *Direct outswing* / *Direct other* / *Short corner*. Determined by the opener pass length (≤ 15 yd → Short corner) and, for longer corners, by `pass.technique.name` (or the explicit `pass.inswinging` flag).
- **Target zone**: six-zone classification of the meaningful-delivery endpoint — *Near post* (`x ≥ 114, y < 33`), *Central six-yard* (`x ≥ 114, 33 ≤ y ≤ 47`), *Far post* (`x ≥ 114, y > 47`), *Penalty spot* (`x ≥ 102, 28 ≤ y ≤ 52`), *Edge of box* (`x ≥ 96`) and, for anything else, *Wide recycle*.
- **Meaningful delivery**: for direct corners, the corner pass itself. For short corners, the first subsequent team pass that's long enough to actually deliver the ball into the box (`pass.length ≥ 12`, end `x ≥ 96`, or start `x ≥ 105`), or a shot — whichever comes first. Falls back to the corner pass when no such follow-up exists.
- **First touch**: the first team event after the corner pass whose type is in `{Ball Receipt*, Ball Recovery, Carry, Dribble, Duel, Pass, Shot}` and which has a location. Its *kind* is the kind of the first actionable (`Pass` / `Shot` / `Carry`) event from that touch onwards — if the first touch is itself a `Ball Receipt*`, the next actionable event in the sequence provides the arrow.
- **Side normalisation**: `_loader.py` y-flips every corner so all of them live on the same side of the pitch — used by `spatial_profile.py`. The two dark-themed by-side scripts call `display_point` to mirror the y-flipped coordinates back onto each corner's original side, so left- and right-side corners can be compared directly.
- **Spelling drift**: team-name resolution is exact-match only. A handful of UCL teams (PSG, Bayern München, Monaco, Leverkusen, Dortmund) are spelled differently in `matches.csv` vs. the StatsBomb events and would be skipped if used as the focus team. Barcelona's own spelling is stable, so every Barcelona corner is picked up.

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
