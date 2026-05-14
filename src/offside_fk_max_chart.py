"""
offside_fk_max_chart.py - Bar chart of free kicks won by Barcelona due to opponent
offside (10m distance buckets), compared to the best team in each bucket.

The comparison is restricted to the top 8 teams by league phase points.
The name of the best team is annotated above its bar.

Usage:
    python src/offside_fk_max_chart.py
"""

import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

_SB_ROOT   = Path(__file__).parent.parent / "data" / "statsbomb"
LEAGUE_DIR = _SB_ROOT / "league_phase"
DATA_DIRS  = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
ASSETS_DIR = Path(__file__).parent.parent / "assets"
BUCKET = 10  # metres
TOP_K = 16   # compare vs top K teams (change this value)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_topk(k):
    """Return the set of top k teams by league phase points (then GD)."""
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
    ranked = sorted(all_teams, key=lambda t: (points[t], gd[t]), reverse=True)
    return set(ranked[:k])


def offside_fk_buckets(events, team_name):
    """
    Find free kicks won by team_name due to opponent offside.
    Returns a dict of {bucket: count}.
    """
    buckets = defaultdict(int)
    by_index = {e["index"]: e for e in events}
    max_index = max(by_index)

    for e in events:
        if not (e["team"]["name"] != team_name
                and e.get("pass", {}).get("outcome", {}).get("name") == "Pass Offside"):
            continue

        for next_idx in range(e["index"] + 1, min(e["index"] + 10, max_index + 1)):
            nxt = by_index.get(next_idx)
            if nxt is None:
                continue
            if (nxt["team"]["name"] == team_name
                    and nxt["type"]["id"] == 30
                    and nxt.get("pass", {}).get("type", {}).get("name") == "Free Kick"):
                loc = nxt.get("location")
                if loc:
                    dist_m = loc[0] * 0.9144
                    bucket = int(dist_m // BUCKET) * BUCKET
                    buckets[bucket] += 1
                break

    return buckets


def main():
    topk = compute_topk(TOP_K)
    print(f"Top {TOP_K} teams: {sorted(topk)}\n")

    # Accumulate per-team totals across all matches
    team_buckets: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    for lineup_path in sorted(p for d in DATA_DIRS for p in d.glob("*_lineups.json")):
        match_id = lineup_path.stem.replace("_lineups", "")
        lineup = load_json(lineup_path)
        events = load_json(lineup_path.parent / f"{match_id}.json")

        for team in lineup:
            name = team["team_name"]
            b = offside_fk_buckets(events, name)
            for bucket, count in b.items():
                team_buckets[name][bucket] += count

    barca_buckets = team_buckets.get("Barcelona", {})

    # For each bucket, find the top-8 team (excl. Barcelona) with the maximum count
    all_buckets = sorted(
        set(barca_buckets) | {b for tb in team_buckets.values() for b in tb}
    )

    max_team_per_bucket: dict[int, str] = {}
    max_val_per_bucket: dict[int, int] = {}

    for bucket in all_buckets:
        best_team = None
        best_count = 0
        for team, tb in team_buckets.items():
            if team == "Barcelona" or team not in topk:  # noqa: F821
                continue
            c = tb.get(bucket, 0)
            if c > best_count:
                best_count = c
                best_team = team
        max_team_per_bucket[bucket] = best_team or ""
        max_val_per_bucket[bucket] = best_count

    labels = [f"{b}–{b+BUCKET}m" for b in all_buckets]
    barca_vals = [barca_buckets.get(b, 0) for b in all_buckets]
    max_vals   = [max_val_per_bucket[b]    for b in all_buckets]

    x = list(range(len(all_buckets)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))

    bars_barca = ax.bar(
        [i - width / 2 for i in x], barca_vals, width=width,
        label="Barcelona", color="#4575b4",
    )
    bars_max = ax.bar(
        [i + width / 2 for i in x], max_vals, width=width,
        label="Best other team (per bucket)", color="#fc8d59", edgecolor="#d73027", linewidth=0.8,
    )

    # Annotate team name above each max bar
    for i, (bar, bucket) in enumerate(zip(bars_max, all_buckets)):
        team_name = max_team_per_bucket[bucket]
        val = max_val_per_bucket[bucket]
        if team_name and val > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                team_name,
                ha="center", va="bottom",
                fontsize=7, rotation=45, color="#4575b4",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_xlabel("Distance from own baseline")
    ax.set_ylabel("Offside free kicks won")
    ax.set_title(f"Free kicks won due to offside — Barcelona vs best top-{TOP_K} team per bucket")
    ax.legend()
    fig.tight_layout()

    ASSETS_DIR.mkdir(exist_ok=True)
    out = ASSETS_DIR / "offside_fk_max_by_distance.png"
    fig.savefig(out, dpi=150)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()