"""
corner_attempts_per_corner_barca_vs_avg.py

Bar chart only:
    - short corner attempts/corner: Barcelona vs average team
    - crossed corner attempts/corner: Barcelona vs average team

Corner classification:
    - cross if the opening corner pass ends inside the penalty box
    - otherwise cross if pass length > 15
    - otherwise short

Shots are assigned to the most recent same-team corner before the shot,
provided the shot has play_pattern == "From Corner".

Usage:
    python src/corner_attempts_per_corner_barca_vs_avg.py
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "all_data"
ASSETS_DIR = Path(__file__).parent.parent / "assets"
out = ASSETS_DIR / "corner_analysis" / "attempts_per_corner_bars.png"

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_corner_kick(ev):
    return (
        ev.get("type", {}).get("id") == 30
        and ev.get("pass", {}).get("type", {}).get("name") == "Corner"
    )


def is_from_corner_shot(ev):
    return (
        ev.get("type", {}).get("id") == 16
        and ev.get("shot", {}).get("type", {}).get("name") != "Penalty"
        and ev.get("play_pattern", {}).get("name") == "From Corner"
    )


def pass_length(start, end):
    return math.hypot(end[0] - start[0], end[1] - start[1])


def normalize_to_attacking_right(start_xy, xy):
    """
    Normalize coordinates so the attacking goal is always at x=120.
    Infer attack direction from the corner start location.
    """
    sx, sy = start_xy
    x, y = xy

    attacking_right = sx > 60
    if attacking_right:
        return x, y
    return 120 - x, 80 - y


def in_penalty_box_normalized(x, y):
    """
    StatsBomb pitch: 120 x 80
    Penalty box in attacking-right frame:
        x >= 102
        18 <= y <= 62
    """
    return x >= 102 and 18 <= y <= 62


def classify_corner(ev, short_threshold=15.0):
    """
    Cross if:
      1) end location is in the box
      2) OR pass length > short_threshold
    Else short.
    """
    start = ev.get("location")
    end = ev.get("pass", {}).get("end_location")

    if start is None or end is None:
        return None

    end_norm_x, end_norm_y = normalize_to_attacking_right(start, end)

    if in_penalty_box_normalized(end_norm_x, end_norm_y):
        return "cross"

    return "cross" if pass_length(start, end) > short_threshold else "short"


corner_rows = []

for event_path in sorted(DATA_DIR.glob("*.json")):
    if event_path.stem.endswith("_lineups"):
        continue

    events = sorted(load_json(event_path), key=lambda e: e.get("index", -1))
    if not events:
        continue

    corners = []
    for ev in events:
        if is_corner_kick(ev):
            ctype = classify_corner(ev)
            if ctype is None:
                continue

            corners.append(
                {
                    "corner_index": ev["index"],
                    "team": ev["team"]["name"],
                    "corner_type": ctype,
                    "attempts": 0,
                }
            )

    if not corners:
        continue

    # assign each From Corner shot to the most recent same-team corner before it
    for shot in events:
        if not is_from_corner_shot(shot):
            continue

        shot_team = shot["team"]["name"]
        shot_idx = shot["index"]

        opener = None
        for c in reversed(corners):
            if c["corner_index"] < shot_idx and c["team"] == shot_team:
                opener = c
                break

        if opener is None:
            continue

        opener["attempts"] += 1

    corner_rows.extend(corners)

if not corner_rows:
    raise RuntimeError("No usable corner data found.")

df = pd.DataFrame(corner_rows)

# team totals by corner type
team_summary = (
    df.groupby(["team", "corner_type"], as_index=False)
    .agg(
        corners=("corner_index", "count"),
        attempts=("attempts", "sum"),
    )
)

# ensure every team has both rows
teams = sorted(team_summary["team"].unique())
full_idx = pd.MultiIndex.from_product(
    [teams, ["short", "cross"]],
    names=["team", "corner_type"]
)

team_summary = (
    team_summary.set_index(["team", "corner_type"])
    .reindex(full_idx, fill_value=0.0)
    .reset_index()
)

team_summary["attempts_per_corner"] = team_summary.apply(
    lambda r: (r["attempts"] / r["corners"]) if r["corners"] else 0.0,
    axis=1,
)

barca = team_summary[team_summary["team"] == "Barcelona"]
if barca.empty:
    raise RuntimeError("Barcelona not found in dataset.")

barca_rates = barca.set_index("corner_type")["attempts_per_corner"].to_dict()
avg_rates = team_summary.groupby("corner_type")["attempts_per_corner"].mean().to_dict()

categories = ["short", "cross"]
barca_vals = [barca_rates.get(c, 0.0) for c in categories]
avg_vals = [avg_rates.get(c, 0.0) for c in categories]

# plot
x = range(len(categories))
width = 0.35

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar([i - width / 2 for i in x], barca_vals, width=width, label="Barcelona")
ax.bar([i + width / 2 for i in x], avg_vals, width=width, label="Average team")

ax.set_xticks(list(x))
ax.set_xticklabels(["Short corners", "Crossed corners"])
ax.set_ylabel("Attempts per corner")
ax.set_title("Corner Attempts per Corner: Barcelona vs Average Team")
ax.legend()
ax.grid(axis="y", alpha=0.25)
fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.tight_layout()
plt.show()