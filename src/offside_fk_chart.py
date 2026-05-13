"""
offside_fk_chart.py - Bar chart of free kicks won by Barcelona (and avg team) due to
opponent offside, bucketed by distance from own baseline in 5m intervals.

In StatsBomb, an opponent offside is recorded as a pass with pass.offside == True.
The next free kick by the benefitting team is the offside free kick.
Distance from own baseline = x-coordinate of the free kick * 0.9144 m
(assumes Barcelona attacks toward x=120 throughout).

Usage:
    python src/offside_fk_chart.py           # compare vs all teams
    python src/offside_fk_chart.py --top 8   # compare vs top 8 (league phase points)
    python src/offside_fk_chart.py --top 16  # compare vs top 16
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

_SB_ROOT   = Path(__file__).parent.parent / "data" / "statsbomb"
LEAGUE_DIR = _SB_ROOT / "league_phase"
DATA_DIRS  = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
ASSETS_DIR = Path(__file__).parent.parent / "assets"
BUCKET = 10  # metres


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_standings():
    """Return teams sorted by league phase points (desc), then goal difference (desc)."""
    points = defaultdict(int)
    gd = defaultdict(int)

    for lineup_path in sorted(LEAGUE_DIR.glob("*_lineups.json")):
        match_id = lineup_path.stem.replace("_lineups", "")
        lineup = load_json(lineup_path)
        events = load_json(LEAGUE_DIR / f"{match_id}.json")
        team_names = [t["team_name"] for t in lineup]
        if len(team_names) != 2:
            continue
        t1, t2 = team_names
        goals = {t1: 0, t2: 0}
        for e in events:
            if (e["type"]["id"] == 16
                    and e.get("shot", {}).get("outcome", {}).get("name") == "Goal"):
                goals[e["team"]["name"]] += 1
        g1, g2 = goals[t1], goals[t2]
        gd[t1] += g1 - g2
        gd[t2] += g2 - g1
        if g1 > g2:   points[t1] += 3
        elif g2 > g1: points[t2] += 3
        else:         points[t1] += 1; points[t2] += 1

    all_teams = set(points) | set(gd)
    return sorted(all_teams, key=lambda t: (points[t], gd[t]), reverse=True)


def offside_fk_buckets(events, team_name):
    """
    Find free kicks won by team_name due to opponent offside.
    Returns a dict of {bucket: count}.
    """
    buckets = defaultdict(int)

    # Index events for quick lookup
    by_index = {e["index"]: e for e in events}
    max_index = max(by_index)

    for e in events:
        # Opponent committed an offside (pass outcome == "Pass Offside", team != team_name)
        if not (e["team"]["name"] != team_name
                and e.get("pass", {}).get("outcome", {}).get("name") == "Pass Offside"):
            continue

        # Scan forward for the next free kick pass by team_name
        for next_idx in range(e["index"] + 1, min(e["index"] + 10, max_index + 1)):
            nxt = by_index.get(next_idx)
            if nxt is None:
                continue
            if (nxt["team"]["name"] == team_name
                    and nxt["type"]["id"] == 30
                    and nxt.get("pass", {}).get("type", {}).get("name") == "Free Kick"):
                loc = nxt.get("location")
                if loc:
                    dist_m = loc[0] * 0.9144  # x yards → metres from own baseline
                    bucket = int(dist_m // BUCKET) * BUCKET
                    buckets[bucket] += 1
                break  # only count the first free kick per offside

    return buckets


def main(top_n):
    standings = compute_standings()
    comparison_teams = set(standings[:top_n]) if top_n else set(standings)
    group_label = f"top {top_n}" if top_n else "all teams"
    print(f"Comparison group ({group_label}): {sorted(comparison_teams)}\n")

    barca_buckets = defaultdict(int)
    grp_buckets = defaultdict(int)

    for lineup_path in sorted(p for d in DATA_DIRS for p in d.glob("*_lineups.json")):
        match_id = lineup_path.stem.replace("_lineups", "")
        lineup = load_json(lineup_path)
        events = load_json(lineup_path.parent / f"{match_id}.json")

        for team in lineup:
            name = team["team_name"]
            b = offside_fk_buckets(events, name)
            if name == "Barcelona":
                for bucket, count in b.items():
                    barca_buckets[bucket] += count
            if name in comparison_teams:
                for bucket, count in b.items():
                    grp_buckets[bucket] += count

    n = len(comparison_teams)
    all_buckets = sorted(set(barca_buckets) | set(grp_buckets))
    labels = [f"{b}–{b+BUCKET}m" for b in all_buckets]

    barca_vals = [barca_buckets[b] for b in all_buckets]
    avg_vals   = [grp_buckets[b] / n for b in all_buckets]

    x = list(range(len(all_buckets)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar([i - width/2 for i in x], barca_vals, width=width,
           label="Barcelona", color="#4575b4")
    ax.bar([i + width/2 for i in x], avg_vals, width=width,
           label=f"Avg per team ({group_label})", color="#fc8d59", edgecolor="#d73027", linewidth=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_xlabel("Distance from own baseline")
    ax.set_ylabel("Offside free kicks won")
    ax.set_title(f"Free kicks won due to offside — Barcelona vs avg ({group_label})")
    ax.legend()
    fig.tight_layout()

    ASSETS_DIR.mkdir(exist_ok=True)
    out = ASSETS_DIR / "offside_fk_by_distance.png"
    fig.savefig(out, dpi=150)
    print(f"Saved to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, choices=[8, 16], default=None,
                        help="Compare vs top N teams by league phase points (8 or 16)")
    args = parser.parse_args()
    main(16)
