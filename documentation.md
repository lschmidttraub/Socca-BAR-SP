# Data Sources Documentation

This project uses three professional data providers for analyzing FC Barcelona's set pieces in the UEFA Champions League 2025-2026. All data is proprietary and stored in `data/`. The central lookup file `data/matches.csv` links match IDs across all three providers.

## matches.csv

Each row represents one match with the following columns:

| Column | Description |
|--------|-------------|
| `date` | Match date (YYYY-MM-DD) |
| `utc` | Kick-off time (UTC) |
| `statsbomb` | StatsBomb match ID |
| `skillcorner` | SkillCorner match ID |
| `home` / `away` | Team names |
| `score` | Final score (e.g. `2-1`) |
| `wyscout` | Wyscout match ID |
| `videooffset` | Second-half video timestamp offset (seconds) |

---

## StatsBomb — Event Data

**Source:** `data/statsbomb/league_phase.zip` (and `last16.zip`, `playoffs.zip`)
**Format:** One JSON file per match (~5 MB each, ~1500-2000 events)
**Docs:** [StatsBomb Data Glossary](https://support.hudl.com/s/topic/0TOVY000000BO8g4AG/hudl-statsbomb?language=en_US), also available as `data/statsbomb/documentation.pdf`

Each file is a JSON array of event objects representing every on-ball action in the match.

### Key event fields

| Field | Description |
|-------|-------------|
| `type.id` / `type.name` | Event type (`30` = Pass, `16` = Shot, `35` = Starting XI, etc.) |
| `period` | Match period (1 = first half, 2 = second half, 3/4 = extra time) |
| `timestamp` | Elapsed time since period start (`"HH:MM:SS.mmm"`) |
| `team.name` / `player.name` | Who performed the action |
| `position.name` | Player's tactical position |
| `location` | `[x, y]` on a 120x80 yard pitch |
| `play_pattern.name` | How the possession started (e.g. `"From Corner"`, `"From Free Kick"`) |
| `obv_total_net` | On-Ball Value — net change in expected goal probability |

### Pass events (`type.id == 30`)

| Field | Description |
|-------|-------------|
| `pass.recipient` | Receiving player |
| `pass.length` / `pass.angle` | Pass distance and direction |
| `pass.end_location` | `[x, y]` destination |
| `pass.height.name` | `"Ground Pass"`, `"High Pass"`, `"Low Pass"` |
| `pass.body_part.name` | `"Right Foot"`, `"Left Foot"`, `"Head"` |
| `pass.type.name` | `"Corner"`, `"Free Kick"`, `"Kick Off"`, etc. |
| `pass.outcome` | Absent if completed; present (e.g. `"Incomplete"`, `"Out"`) if failed |
| `pass.pass_success_probability` | StatsBomb's predicted completion probability |

### Shot events (`type.id == 16`)

| Field | Description |
|-------|-------------|
| `shot.outcome.name` | `"Goal"`, `"Saved"`, `"Off T"`, `"Blocked"`, etc. |
| `shot.statsbomb_xg` | Expected goals value |

### Starting XI (`type.id == 35`)

Contains `tactics.formation` (e.g. `433`) and `tactics.lineup` with player, position, and jersey number.

### Loading example

```python
import json

with open("data/statsbomb/league_phase/4028847.json") as f:
    events = json.load(f)

# Count Barcelona passes
passes = [e for e in events if e["type"]["id"] == 30 and e["team"]["name"] == "Barcelona"]
```

---

## SkillCorner — Tracking Data

**Source:** `data/skillcorner.zip`
**Format:** Zipped archives containing ~8 files per match
**Docs:** [SkillCorner Documentation](https://skillcorner.crunch.help/en)

SkillCorner provides frame-by-frame tracking data derived from broadcast video via computer vision. This captures the position and movement of all 22 players and the ball throughout the match.

### Files per match

| File | Description |
|------|-------------|
| Tracking data (main) | ~80 MB; x/y positions of all players + ball at high frequency |
| Match information | Match metadata |
| Passes | Derived pass events from tracking |
| Runs | Off-ball run detection |
| Pressures | Pressing events |
| Physical performance | Speed, distance, acceleration per player |

### Useful for

- Player positioning and movement during set pieces (corners, free kicks)
- Physical metrics (distance covered, sprints, top speed)
- Off-ball runs and movement patterns
- Pressing intensity
- Pitch control and spatial dominance models

---

## Wyscout — Video Clips

**Source:** `data/wyscout.zip` — a Python CLI tool (not raw data)
**Format:** Downloads 10-second MP4 clips from the Wyscout video API

This tool lets you retrieve short video clips of specific match moments, useful for visually verifying set-piece situations identified through StatsBomb events.

### Usage

```bash
python eventvideo.py <wyscout_id> <video_timestamp> output.mp4
```

- `wyscout_id`: from the `wyscout` column in `matches.csv`
- `video_timestamp`: computed from the StatsBomb event's `period` and `timestamp`:
  - Convert `timestamp` to seconds (rounded to integer)
  - Add offset: period 1 → `+1`, period 2 → `+ videooffset` from `matches.csv`
- Add `-hq` for high-quality video (~6 MB instead of ~2 MB)

Clips start 4 seconds before and end 6 seconds after the specified timestamp.

### Example

Barcelona vs Newcastle (`wyscout = 5769762`, `videooffset = 2903`). A second-half event at `timestamp = "00:05:30.000"`:

```bash
# video_timestamp = 2903 + 330 = 3233
python eventvideo.py 5769762 3233 clip.mp4
```
