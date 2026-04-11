# Corner Player Roles — Top Takers & First Receivers (FC Barcelona)

## What it does

Re-computes the two player-role rankings embedded in the *Offensive Corners* subsection of the [BAR-SP wiki page](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP): who takes Barcelona's corners, and who ends up on the receiving end of the meaningful delivery once any short-corner manipulation phase is stripped away. The result is the pair of horizontal bar charts that back the wiki's "Raphinha clearly dominates as the corner taker … receivers are more widely distributed" observation.

The snippet ships a single runnable script plus a shared loader:

| Wiki subsection          | Script                         | Plots produced                                           |
|--------------------------|--------------------------------|----------------------------------------------------------|
| Offensive Corners        | `top_takers_and_receivers.py`  | `corner_takers_single.png`, `delivery_receivers_single.png` |

- `_loader.py` parses `data/matches.csv`, streams StatsBomb JSONs out of the three ZIP archives in `data/statsbomb/` without unpacking them, extracts each Barcelona corner's possession sequence (capped at 20 seconds), and walks short-corner sequences forward to find the first meaningful delivery and its receiver. It has no dependency on the project's `src/stats` library — the whole `corner_player_roles` folder can be dropped into another repo that follows the same data layout.

## Inputs

- **Team name** (first positional CLI arg, default: `"Barcelona"`)
- **Output directory** (second positional CLI arg, default: `./corner_player_plots/`)
- **Data sources**: StatsBomb event data (`data/statsbomb/league_phase.zip`, `last16.zip`, `playoffs.zip`) and `data/matches.csv` as the match lookup.

## Output

The script does two things:

1. **Stdout** — a plain-text report listing how many corners were tracked, the top 8 corner takers and the top 8 first-delivery receivers with per-player counts.
2. **PNG plots** — two files saved into the output directory: `corner_takers_single.png` and `delivery_receivers_single.png`. Horizontal bars in Barcelona red with value labels, ordered by count descending.

![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/corner_takers_single.png)
![](https://gitlab.ethz.ch/socceranalytics/uefa-cl-2025-2026/-/wikis/BAR-SP/assets/upload/offensive/corners/delivery_receivers_single.png)

## Example outputs

### `top_takers_and_receivers.py`

```
Corner player roles — Barcelona
------------------------------------------------------------
  Corners taken (with a known taker): 47
  Total corners tracked             : 47

Top 8 corner takers — Barcelona
------------------------------------------------------------
  Raphael Dias Belloli          20
  Marcus Rashford               15
  Lamine Yamal Nasraoui Ebana    6
  Daniel Olmo Carvajal           3
  João Pedro Cavaco Cancelo      2
  Fermin Lopez Marin             1

Top 8 first-delivery receivers — Barcelona
------------------------------------------------------------
  Fermin Lopez Marin                 5
  Ronald Federico Araújo da Silva    4
  Marcus Rashford                    4
  Pedro González López               4
  Lamine Yamal Nasraoui Ebana        4
  Robert Lewandowski                 4
  Gerard Martín Langreo              3
  Raphael Dias Belloli               2

Saving plots to corner_player_plots/ ...
  saved corner_player_plots/corner_takers_single.png
  saved corner_player_plots/delivery_receivers_single.png
```

## Definitions

- **Corner taker**: the player who plays the corner restart pass (the `pass.type.name == "Corner"` event).
- **First receiver**: the `pass.recipient.name` of the corner restart pass — the player the corner is initially played to, whether short or direct.
- **Delivery receiver**: for direct corners, identical to the first receiver. For short corners, the player who eventually receives the *meaningful delivery* — the first follow-up event that is either a shot, or a pass with end-x ≥ 96, start-x ≥ 105, or length ≥ 12 yards (i.e. a real ball into the box after the short-corner manipulation phase). If no such event is found, the snippet falls back to the original corner pass.
- **Sequence**: contiguous events sharing the corner's `possession` and `period`, capped at 20 seconds after the corner pass.
- **Spelling drift**: teams whose `matches.csv` name differs from the StatsBomb event-side name (PSG, Bayern, Monaco, Leverkusen, Dortmund) are skipped because this snippet only uses exact-match name resolution. Barcelona is spelled identically in both sources, so the rankings above are unaffected.

## Disclaimer

Generative AI was used in the creation of both the code and documentation for this snippet.
