# Stats Library

Set piece analysis library for UCL 2025-26 StatsBomb event data.

## Quick Start

```python
import json
from pathlib import Path
from src.stats import compare, TOP_16
from src.stats.setpieces.corners import Corners

result = compare(Corners(), Path("data/statsbomb"))
print(json.dumps(result, indent=2))
```

## Defining an Analysis

Subclass `Analysis` and implement `analyze_match` and `summarize`:

```python
from src.stats.models import Analysis

class Corners(Analysis):
    name = "corners"

    def analyze_match(self, events: list[dict], team: str) -> dict:
        """Return raw additive counts for one team in one match.

        All leaf values must be numbers that can be summed across matches.
        """
        total = 0
        for e in events:
            ...
        return {"total_corners": total, ...}

    def summarize(self, totals: dict, n_matches: int) -> dict:
        """Compute derived metrics from the summed totals.

        Must return {"metrics": {...}, "breakdowns": {...}}.
        """
        tc = totals["total_corners"]
        return {
            "metrics": {
                "total_corners": tc,
                "corners_per_match": round(tc / n_matches, 2),
                ...
            },
            "breakdowns": { ... },
        }
```

Place the class in `src/stats/setpieces/` and pass an instance to `compare()`.

## Using `compare()`

```python
from src.stats import compare
```

`compare()` runs an analysis for a focus team and a comparison group, returning a JSON-serialisable dict.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `analysis` | *(required)* | An `Analysis` subclass instance |
| `data_dir` | `Path("data/statsbomb")` | Path to data — a directory containing `.zip` files, a single `.zip`, or extracted JSONs |
| `focus_team` | `"Barcelona"` | The team to analyse |
| `group` | `TOP_16` | Which teams to compare against |
| `per_team` | `False` | If `True`, include full individual results for every team in the group |

```python
from src.stats import compare, BARCELONA_OPPONENTS
from src.stats.setpieces.corners import Corners

result = compare(Corners(), Path("data/statsbomb"), group=BARCELONA_OPPONENTS, per_team=True)
```

## Comparison Groups

| Import | Name | Description |
|--------|------|-------------|
| `ALL` | `all` | Every team in the dataset |
| `TOP_8` | `top_8` | Top 8 by league phase standings (points, then goal difference) |
| `TOP_16` | `top_16` | Top 16 by standings |
| `BARCELONA_OPPONENTS` | `barcelona_opponents` | Teams that played against Barcelona |

## Output Format

Every `compare()` call returns a dict with this structure:

```json
{
  "analysis": "corners",
  "data_source": "data/statsbomb",
  "focus_team": "Barcelona",
  "focus": {
    "team": "Barcelona",
    "matches": 10,
    "metrics": { "total_corners": 47, "completion_rate": 0.595 },
    "breakdowns": { "by_side": { "left": {}, "right": {} } }
  },
  "comparison_group": "top_16",
  "comparison_teams": ["Arsenal", "Liverpool", "..."],
  "group_average": {
    "matches": 8.0,
    "metrics": { "..." : "..." },
    "breakdowns": { "..." : "..." }
  }
}
```

With `per_team=True`, an additional `per_team` dict maps each team name to its full results.

## End-to-End Analyses

The `analyses/` folder contains scripts that run a complete analysis pipeline — computing stats via `compare()`, generating graphics with `viz`, and saving everything to `assets/`.

## Visualization

The `viz` subpackage provides chart and pitch plot functions built on mplsoccer and seaborn.

### Comparison charts

```python
from src.stats.viz import metric_bars, breakdown_bars, metric_radar
from src.stats.viz.charts import team_rank_bars
from src.stats.viz.style import save_fig
```

**`metric_bars`** — grouped bar chart comparing focus team vs group average:

```python
result = compare(Corners(), Path("data/statsbomb"))

fig, ax = metric_bars(
    result,
    metrics=["total_corners", "completed", "shots_from_corners", "xg_from_corners"],
)
save_fig(fig, "assets/corner_bars.png")
```

**`breakdown_bars`** — compare a breakdown category (e.g. by_side, by_pitch_third):

```python
fig, ax = breakdown_bars(result, "by_side", metric_key="total")
```

**`metric_radar`** — radar chart overlaying focus team and group average:

```python
fig, ax = metric_radar(
    result,
    metrics=["total_corners", "completed", "shots_from_corners", "xg_from_corners"],
    labels=["Corners", "Completed", "Shots", "xG"],
)
```

**`team_rank_bars`** — horizontal bar chart ranking all teams (requires `per_team=True`):

```python
result = compare(Corners(), Path("data/statsbomb"), per_team=True)
fig, ax = team_rank_bars(result, "total_corners")
```

### Pitch plots

```python
from src.stats.viz import event_map, heatmap, pass_map
```

These work directly with StatsBomb event lists. Collect events using `data.iter_matches()` and `filters`:

```python
from src.stats.data import iter_matches
from src.stats import filters as f

corner_passes = []
for row, events in iter_matches(Path("data/statsbomb")):
    if "Barcelona" not in (row["home"], row["away"]):
        continue
    for e in events:
        if f.by_team(e, "Barcelona") and f.is_corner_pass(e):
            corner_passes.append(e)
```

**`event_map`** — scatter on pitch (`size_by_xg=True` for shots):

```python
fig, ax = event_map(shots, title="Shots from corners", size_by_xg=True, half=True)
```

**`heatmap`** — kernel density heatmap:

```python
fig, ax = heatmap(corner_passes, title="Corner delivery locations")
```

**`pass_map`** — arrows showing origin and destination:

```python
fig, ax = pass_map(corner_passes, title="Corner deliveries", half=True)
```

All pitch plots accept `vertical=True` for vertical orientation, `half=True` for attacking half only, and an `ax` parameter for composing subplots.

### Styling

```python
from src.stats.viz.style import apply_theme, save_fig, FOCUS_COLOR, AVG_COLOR
```

- `apply_theme()` — sets a clean matplotlib theme
- `save_fig(fig, path)` — saves and closes, creating parent dirs
- `FOCUS_COLOR` / `AVG_COLOR` — the default red/blue palette

## Module Structure

```
src/stats/
  __init__.py          # Public API (compare, Analysis, groups)
  models.py            # Analysis base class, AnalysisResult
  data.py              # Data loading (matches.csv + ZIPs)
  pitch.py             # Pitch geometry (distances, bucketing)
  groups.py            # Team group definitions
  filters.py           # Event filtering predicates
  compare.py           # Comparison engine
  setpieces/           # Analysis class definitions
  analyses/            # End-to-end scripts (stats + graphics → assets/)
  viz/
    style.py           # Theme, colours, save_fig
    pitch_plots.py     # event_map, heatmap, pass_map
    charts.py          # metric_bars, breakdown_bars, metric_radar, team_rank_bars
```
