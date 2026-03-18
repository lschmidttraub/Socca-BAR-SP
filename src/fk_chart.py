"""
fk_chart.py - Bar chart of Barcelona free kicks (shots vs passes) by distance to goal,
compared to the per-team average across a selected group.

Usage:
    python src/fk_chart.py           # compare vs all teams
    python src/fk_chart.py --top 8   # compare vs top 8 teams (by league phase points)
    python src/fk_chart.py --top 16  # compare vs top 16 teams
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).parent.parent / "data" / "statsbomb" / "league_phase"
ASSETS_DIR = Path(__file__).parent.parent / "assets"
BUCKET = 5  # metres


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fk_distance_m(event):
    loc = event.get("location")
    if not loc:
        return None
    x, y = loc[0], loc[1]
    dist_yards = ((120 - x) ** 2 + (40 - y) ** 2) ** 0.5
    return dist_yards * 0.9144


def compute_standings():
    """Return list of (team, points, gd) sorted by points desc, gd desc."""
    points = defaultdict(int)
    gd = defaultdict(int)

    for lineup_path in sorted(DATA_DIR.glob("*_lineups.json")):
        match_id = lineup_path.stem.replace("_lineups", "")
        lineup = load_json(lineup_path)
        events = load_json(DATA_DIR / f"{match_id}.json")

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
        if g1 > g2:
            points[t1] += 3
        elif g2 > g1:
            points[t2] += 3
        else:
            points[t1] += 1
            points[t2] += 1

    all_teams = set(points) | set(gd)
    return sorted(all_teams, key=lambda t: (points[t], gd[t]), reverse=True)


def collect_fk_counts(events, team_name):
    shots = defaultdict(int)
    passes = defaultdict(int)
    for e in events:
        if e["team"]["name"] != team_name:
            continue
        is_fk_pass = (
            e["type"]["id"] == 30
            and e.get("pass", {}).get("type", {}).get("name") == "Free Kick"
        )
        is_fk_shot = (
            e["type"]["id"] == 16
            and e.get("shot", {}).get("type", {}).get("name") == "Free Kick"
        )
        if not (is_fk_pass or is_fk_shot):
            continue
        dist = fk_distance_m(e)
        if dist is None:
            continue
        bucket = int(dist // BUCKET) * BUCKET
        if is_fk_shot:
            shots[bucket] += 1
        else:
            passes[bucket] += 1
    return shots, passes


def main(top_n = 16):
    standings = compute_standings()

    if top_n:
        comparison_teams = set(standings[:top_n])
        group_label = f"top {top_n}"
    else:
        comparison_teams = set(standings)
        group_label = "all teams"

    print(f"Comparison group ({group_label}): {sorted(comparison_teams)}\n")

    barca_shots = defaultdict(int)
    barca_passes = defaultdict(int)
    grp_shots = defaultdict(int)
    grp_passes = defaultdict(int)

    for lineup_path in sorted(DATA_DIR.glob("*_lineups.json")):
        match_id = lineup_path.stem.replace("_lineups", "")
        lineup = load_json(lineup_path)
        events = load_json(DATA_DIR / f"{match_id}.json")

        for team in lineup:
            name = team["team_name"]
            s, p = collect_fk_counts(events, name)
            if name == "Barcelona":
                for b, c in s.items(): barca_shots[b] += c
                for b, c in p.items(): barca_passes[b] += c
            if name in comparison_teams:
                for b, c in s.items(): grp_shots[b] += c
                for b, c in p.items(): grp_passes[b] += c

    n = len(comparison_teams)
    all_buckets = sorted(set(barca_shots) | set(barca_passes) | set(grp_shots) | set(grp_passes))
    labels = [f"{b}–{b+BUCKET}m" for b in all_buckets]

    barca_sv = [barca_shots[b] for b in all_buckets]
    barca_pv = [barca_passes[b] for b in all_buckets]
    avg_sv   = [grp_shots[b] / n for b in all_buckets]
    avg_pv   = [grp_passes[b] / n for b in all_buckets]

    x = list(range(len(all_buckets)))
    width = 0.2

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar([i - 1.5*width for i in x], barca_sv, width=width, label="Barcelona shots",          color="#a50026")
    ax.bar([i - 0.5*width for i in x], barca_pv, width=width, label="Barcelona passes",         color="#4575b4")
    ax.bar([i + 0.5*width for i in x], avg_sv,   width=width, label=f"Avg shots ({group_label})",  color="#f4a582", edgecolor="#a50026", linewidth=0.8)
    ax.bar([i + 1.5*width for i in x], avg_pv,   width=width, label=f"Avg passes ({group_label})", color="#92c5de", edgecolor="#4575b4", linewidth=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_xlabel("Distance to goal")
    ax.set_ylabel("Free kicks")
    ax.set_title(f"Barcelona free kicks vs avg ({group_label}) — shots & passes by distance")
    ax.legend()
    fig.tight_layout()

    ASSETS_DIR.mkdir(exist_ok=True)
    out = ASSETS_DIR / "fk_by_distance.png"
    fig.savefig(out, dpi=150)
    print(f"Saved to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, choices=[8, 16], default=None,
                        help="Compare vs top N teams by league phase points (8 or 16)")
    args = parser.parse_args()
    main(8)
