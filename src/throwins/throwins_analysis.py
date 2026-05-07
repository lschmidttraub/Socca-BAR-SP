"""
throwins_analysis.py

Three charts comparing Barcelona throw-ins to the rest of the league:
  1. Total throw-ins per team vs. league average
  2. Barcelona's throw-in direction breakdown (Forward / Lateral / Backward)
  3. % of lateral + backward throw-ins — all teams ranked

All games are read exactly once; both teams are processed per game.

Usage:
    python src/throwins_analysis.py
"""

import matplotlib.pyplot as plt
import pandas as pd

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    _read_matches_df,
    read_statsbomb,
    team_throw_ins,
    throw_in_direction,
)

DIRECTION_COLORS = {
    "Forward":  "#4895ef",
    "Lateral":  "#f9c74f",
    "Backward": "#e63946",
}


# ── Data collection ───────────────────────────────────────────────────────────

def collect_stats() -> dict[str, dict]:
    """Single pass over all matches; returns per-team throw-in counts by direction.

    Each game is read once and both teams are processed, avoiding duplicate
    ZIP reads that would result from calling build_records() per team.

    Returns
    -------
    {team_name: {"total": int, "games": int, "Forward": int,
                 "Lateral": int, "Backward": int}}
    """
    df    = _read_matches_df()
    stats: dict[str, dict] = {}

    for _, row in df.iterrows():
        if pd.isna(row["statsbomb"]):
            continue
        game_id = int(row["statsbomb"])

        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing events for game {game_id}, skipping.")
            continue

        team_names = {
            ev.get("team", {}).get("name", "")
            for ev in events
            if ev.get("team", {}).get("name")
        }

        for team_name in team_names:
            if team_name not in stats:
                stats[team_name] = {
                    "total": 0, "games": 0,
                    "Forward": 0, "Lateral": 0, "Backward": 0,
                }
            stats[team_name]["games"] += 1
            for ev in team_throw_ins(events, team_name):
                stats[team_name]["total"] += 1
                d = throw_in_direction(ev)
                if d in stats[team_name]:
                    stats[team_name][d] += 1

    return stats


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_count_comparison(stats: dict[str, dict], save: bool = True) -> None:
    """Horizontal bar chart of throw-ins per match per team, Barcelona highlighted."""
    df = pd.DataFrame([
        {"team": name, "per_match": d["total"] / d["games"] if d["games"] else 0}
        for name, d in stats.items()
        if d["games"] > 0
    ]).sort_values("per_match")

    avg = df["per_match"].mean()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.5)))
    fig.set_facecolor("white")
    bars = ax.barh(df["team"], df["per_match"], color="steelblue", edgecolor="white")

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    for bar, val in zip(bars, df["per_match"]):
        ax.text(val + 0.2, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", fontsize=7.5)

    ax.axvline(avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {avg:.1f}")
    ax.set_xlabel("Throw-ins per match")
    ax.set_title("Throw-ins per match per team  (red = Barcelona)")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_count_comparison.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")

    plt.show()


def plot_barca_direction(barca: dict, save: bool = True) -> None:
    """Single stacked bar showing Barcelona's direction breakdown as percentages."""
    total = barca["total"]
    if not total:
        print("No Barcelona throw-in data found.")
        return

    directions = ["Forward", "Lateral", "Backward"]
    pcts       = [barca.get(d, 0) / total * 100 for d in directions]
    counts     = [barca.get(d, 0) for d in directions]

    fig, ax = plt.subplots(figsize=(8, 2.5))
    fig.set_facecolor("white")

    left = 0.0
    for d, pct, count in zip(directions, pcts, counts):
        ax.barh("Barcelona", pct, left=left,
                color=DIRECTION_COLORS[d], edgecolor="white", label=d)
        if pct > 4:
            ax.text(left + pct / 2, 0,
                    f"{pct:.1f}%\n({count})",
                    ha="center", va="center", fontsize=9, color="black")
        left += pct

    ax.set_xlim(0, 100)
    ax.set_xlabel("% of throw-ins")
    ax.set_title(f"Barcelona throw-in direction breakdown  (N={total})")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_barca_direction.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")

    plt.show()


def plot_direction_comparison(stats: dict[str, dict], save: bool = True) -> None:
    """Horizontal bar chart: % lateral + backward throw-ins per team."""
    rows = []
    for name, d in stats.items():
        total = d["total"]
        if not total:
            continue
        nonfwd = d.get("Lateral", 0) + d.get("Backward", 0)
        rows.append({"team": name, "nonfwd_pct": nonfwd / total * 100, "total": total})

    df  = pd.DataFrame(rows).sort_values("nonfwd_pct")
    avg = df["nonfwd_pct"].mean()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.5)))
    fig.set_facecolor("white")
    bars = ax.barh(df["team"], df["nonfwd_pct"], color="steelblue", edgecolor="white")

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    for bar, val in zip(bars, df["nonfwd_pct"]):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=7.5)

    ax.axvline(avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {avg:.1f}%")
    ax.set_xlabel("% lateral + backward throw-ins")
    ax.set_title("Non-forward throw-ins per team  (red = Barcelona)")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_direction_comparison.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    stats = collect_stats()

    barca = next(
        (d for name, d in stats.items() if BARCELONA.casefold() in name.casefold()),
        None,
    )
    if barca is None:
        raise RuntimeError("No Barcelona data found — check matches.csv and event ZIPs.")

    avg_total = sum(d["total"] for d in stats.values()) / len(stats)

    print(f"\nTeams analysed       : {len(stats)}")
    print(f"Barcelona throw-ins  : {barca['total']}  (league avg: {avg_total:.1f})")
    print("\nBarcelona direction breakdown:")
    for d in ("Forward", "Lateral", "Backward"):
        n   = barca.get(d, 0)
        pct = n / barca["total"] * 100 if barca["total"] else 0
        print(f"  {d:<10}  {n:>4}  ({pct:.1f}%)")

    plot_count_comparison(stats)
    plot_barca_direction(barca)
    plot_direction_comparison(stats)
