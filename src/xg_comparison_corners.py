"""
corner_xg_barca_vs_avg.py

Bar chart only:
    - short corner xG: Barcelona vs average team
    - crossed corner xG: Barcelona vs average team

Logic:
    1) find every corner kick
    2) classify opener as short/cross by pass length
    3) assign each shot with play_pattern == "From Corner"
       to the most recent same-team corner before it
    4) sum xG by opener type

Usage:
    python src/corner_xg_barca_vs_avg.py
"""

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data" / "statsbomb" / "league_phase"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_corner_kick(ev):
    return (
        ev.get("type", {}).get("id") == 30
        and ev.get("pass", {}).get("type", {}).get("name") == "Corner"
    )


def pass_length(start, end):
    return math.hypot(end[0] - start[0], end[1] - start[1])


def classify_corner(ev, short_threshold=15.0):
    """
    Robust split:
      - short: opener pass length <= 15
      - cross: opener pass length > 15

    This is safer here than relying on pass.cross.
    """
    start = ev.get("location")
    end = ev.get("pass", {}).get("end_location")

    if start is None or end is None:
        return None

    return "short" if pass_length(start, end) <= short_threshold else "cross"


def is_from_corner_shot(ev):
    return (
        ev.get("type", {}).get("id") == 16
        and ev.get("shot", {}).get("type", {}).get("name") != "Penalty"
        and ev.get("play_pattern", {}).get("name") == "From Corner"
    )


def shot_xg(ev):
    return float(ev.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)


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
                    "xg": 0.0,
                }
            )

    if not corners:
        continue

    # Assign each From Corner shot to the most recent same-team corner before it
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

        opener["xg"] += shot_xg(shot)

    corner_rows.extend(corners)

if not corner_rows:
    raise RuntimeError("No usable corner data found.")

df = pd.DataFrame(corner_rows)

# total xG by team and corner type
team_xg = (
    df.groupby(["team", "corner_type"], as_index=False)
    .agg(xg=("xg", "sum"))
)

# ensure all teams have both short/cross rows
teams = sorted(team_xg["team"].unique())
full_idx = pd.MultiIndex.from_product(
    [teams, ["short", "cross"]],
    names=["team", "corner_type"]
)

team_xg = (
    team_xg.set_index(["team", "corner_type"])
    .reindex(full_idx, fill_value=0.0)
    .reset_index()
)

barca = team_xg[team_xg["team"] == "Barcelona"]
if barca.empty:
    raise RuntimeError("Barcelona not found in dataset.")

barca_xg = barca.set_index("corner_type")["xg"].to_dict()
avg_xg = team_xg.groupby("corner_type")["xg"].mean().to_dict()

categories = ["short", "cross"]
barca_vals = [barca_xg.get(c, 0.0) for c in categories]
avg_vals = [avg_xg.get(c, 0.0) for c in categories]

# Plot
x = range(len(categories))
width = 0.35

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar([i - width / 2 for i in x], barca_vals, width=width, label="Barcelona")
ax.bar([i + width / 2 for i in x], avg_vals, width=width, label="Average team")

ax.set_xticks(list(x))
ax.set_xticklabels(["Short corners", "Crossed corners"])
ax.set_ylabel("Total xG")
ax.set_title("Corner xG: Barcelona vs Average Team")
ax.legend()
ax.grid(axis="y", alpha=0.25)

plt.tight_layout()
plt.show()