# Stats Library

Set piece analysis library for UCL 2025-26 StatsBomb event data.

## Quick Start

```bash
# Run from the Socca-BAR-SP directory

# Single analysis
uv run python -m src.stats corners --team Barcelona --compare top16

# All analyses at once
uv run python -m src.stats all --team Barcelona --compare top16 --output results.json

# List available analyses
uv run python -m src.stats --list
```

## CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `analysis` | *(required)* | `corners`, `free_kicks`, `penalties`, `throw_ins`, `goal_kicks`, `defensive`, or `all` |
| `--team` | `Barcelona` | Focus team |
| `--compare` | `top16` | Comparison group: `all`, `top8`, `top16`, `barcelona_opponents` |
| `--per-team` | off | Include full individual team results in output |
| `--data-dir` | `data/statsbomb` | Path to data (directory of `.zip` files, a single `.zip`, or extracted JSONs) |
| `--output` | stdout | Write JSON to file instead of printing |

## Analyses

| Module | What it measures |
|--------|-----------------|
| **corners** | Delivery type (short/long), completion rate, shots/goals/xG from corners, by-side and by-delivery breakdowns |
| **free_kicks** | Direct shots vs crosses, distance-to-goal bucketing (5m), offside-won FKs (10m from baseline), conversion rates |
| **penalties** | Conversion rate, xG, per-taker breakdown |
| **throw_ins** | Completion, territory gained, long throws (>25 yd), by-pitch-third breakdown |
| **goal_kicks** | Short vs long distribution, completion rates, target zone breakdown |
| **defensive** | Opponent corners/FKs/penalties faced, goals and xG conceded per set piece type |

## Output Format

Every analysis produces JSON with this structure:

```json
{
  "analysis": "corners",
  "generated_at": "2026-04-01T16:06:43+00:00",
  "data_source": "data/statsbomb/league_phase.zip",
  "focus_team": "Barcelona",
  "focus": {
    "team": "Barcelona",
    "matches": 8,
    "metrics": { "total_corners": 37, "completion_rate": 0.595, "..." : "..." },
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

With `--per-team`, an additional `per_team` dict is included with full results for every team in the comparison group.

## Comparison Groups

| Group | Description |
|-------|-------------|
| `all` | Every team in the dataset |
| `top8` | Top 8 by league phase standings (points, then goal difference) |
| `top16` | Top 16 by standings |
| `barcelona_opponents` | Teams that played against Barcelona |

## Python API

```python
from pathlib import Path
from src.stats import compare, TOP_16
from src.stats.analyses import corners

result = compare(
    analysis_module=corners,
    data_dir=Path("data/statsbomb/"),
    focus_team="Barcelona",
    group=TOP_16,
    per_team=False,
)
```

## Module Structure

```
src/stats/
  __init__.py          # Public API
  __main__.py          # CLI entry point
  models.py            # AnalysisResult dataclass
  data.py              # Data loading (directory + ZIP)
  pitch.py             # Pitch geometry (distances, bucketing)
  groups.py            # Team group definitions
  filters.py           # Event filtering predicates
  compare.py           # Comparison engine
  analyses/
    __init__.py        # Registry of all analyses
    corners.py
    free_kicks.py
    penalties.py
    throw_ins.py
    goal_kicks.py
    defensive.py
```

### Adding a New Analysis

Create a module in `analyses/` that exposes:

- `name: str` — analysis identifier
- `analyze_match(events, team) -> dict` — raw additive counts from one match for one team (all values must be numbers that can be summed across matches)
- `summarize(totals, n_matches) -> dict` — returns `{"metrics": {...}, "breakdowns": {...}}` with derived rates computed from the summed totals

Then register it in `analyses/__init__.py`.
