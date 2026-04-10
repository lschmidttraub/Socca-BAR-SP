"""Mean height of the 6 tallest outfield players — all-team comparison.

Generates the bar chart shown in the *Player Physicality* subsection of
the BAR-SP wiki page.

For every team in ``data/matches.csv`` we:

1. collect the unique set of outfield players that actually took the
   pitch in at least one match (deduplicated by ``player_id``),
2. take the 6 tallest of those players, and
3. average their heights.

The resulting metric is plotted as a bar chart ordered from tallest to
shortest, with Barcelona highlighted in red and the league mean drawn
as an additional bar in orange.

Heights come from the StatsBomb lineup files (``*_lineups.json``)
bundled inside ``data/statsbomb/league_phase.zip`` and
``data/statsbomb/playoffs.zip``. ``last16.zip`` ships without lineup
files and is therefore skipped.

Usage
-----

    python top6_height_comparison.py [team] [output.png]

Both arguments are optional: ``team`` defaults to ``Barcelona`` and
``output.png`` defaults to ``all_teams_top6_height.png`` in the current
working directory.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

STATSBOMB_DIR = Path("data/statsbomb")
MATCHES_CSV = Path("data/matches.csv")
DEFAULT_OUTPUT = Path("all_teams_top6_height.png")

FOCUS_TEAM = "Barcelona"
TOP_N = 6  # tallest N outfield players to average
# last16.zip has no lineup files — drop it.
LINEUP_ZIPS = ("league_phase.zip", "playoffs.zip")

# Styling — matches the repo-wide palette used by src/stats/viz/style.py
FOCUS_COLOR = "#a50026"    # Barcelona
AVG_BAR_COLOR = "#f4a261"  # League average bar
OTHER_COLOR = "#4575b4"    # Other teams
AVG_LABEL = "League Avg"


# ── Lineup loading ────────────────────────────────────────────────────


def _load_lineup(match_id: str) -> list[dict] | None:
    """Return the lineup JSON for *match_id* from whichever ZIP has it."""
    target = f"{match_id}_lineups.json"
    for zname in LINEUP_ZIPS:
        zp = STATSBOMB_DIR / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def _read_matches_csv() -> list[dict]:
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ── Player helpers ────────────────────────────────────────────────────


def _is_goalkeeper(player: dict) -> bool:
    return any(
        "Goalkeeper" in pos.get("position", "")
        for pos in player.get("positions", [])
    )


def _actually_played(player: dict) -> bool:
    """Non-empty ``positions`` list ⇒ player took the pitch."""
    return len(player.get("positions", [])) > 0


def _top_n_mean(heights: list[float], n: int = TOP_N) -> float | None:
    """Mean of the *n* largest heights, or None if fewer than *n* exist."""
    top = sorted(heights, reverse=True)[:n]
    if len(top) < n:
        return None
    return sum(top) / n


# ── Data collection ───────────────────────────────────────────────────


def collect_team_heights() -> dict[str, float]:
    """Return ``{csv_team: mean_top6_height_cm}`` across all matches.

    Players are keyed by StatsBomb ``player_id`` so a single player who
    appears in multiple matches contributes their height exactly once.
    Goalkeepers and unused subs are excluded.
    """
    team_players: dict[str, dict[int, float]] = defaultdict(dict)

    for row in _read_matches_csv():
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        lineup = _load_lineup(match_id)
        if lineup is None:
            continue

        # Lineup entries come keyed by StatsBomb team name; we just use
        # those names directly and don't bother mapping back to CSV.
        for team_entry in lineup:
            sb_name = team_entry.get("team_name", "")
            for p in team_entry.get("lineup", []):
                if not _actually_played(p) or _is_goalkeeper(p):
                    continue
                h = p.get("player_height")
                if h:
                    team_players[sb_name][p["player_id"]] = float(h)

    out: dict[str, float] = {}
    for team, pid_heights in team_players.items():
        m = _top_n_mean(list(pid_heights.values()))
        if m is not None:
            out[team] = m
    return out


# ── Plotting ──────────────────────────────────────────────────────────


def plot(all_team_metric: dict[str, float], focus_team: str, output_path: Path) -> None:
    """Bar chart of mean top-N height per team — wiki version."""
    if not all_team_metric:
        raise SystemExit("No height data collected — check StatsBomb ZIPs.")

    items = sorted(all_team_metric.items(), key=lambda kv: kv[1], reverse=True)
    teams = [t for t, _ in items]
    vals = [v for _, v in items]

    league_avg = float(np.mean(vals))

    # Insert the league-average bar at its sorted position.
    inserted = False
    for i, v in enumerate(vals):
        if league_avg >= v:
            teams.insert(i, AVG_LABEL)
            vals.insert(i, league_avg)
            inserted = True
            break
    if not inserted:
        teams.append(AVG_LABEL)
        vals.append(league_avg)

    colors = [
        AVG_BAR_COLOR if t == AVG_LABEL
        else FOCUS_COLOR if t == focus_team
        else OTHER_COLOR
        for t in teams
    ]

    n = len(teams)
    fig, ax = plt.subplots(figsize=(max(14.0, n * 0.56), 7))
    x = np.arange(n)
    bars = ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.5, width=0.72)

    y_min = min(vals) - 2.0
    y_max = max(vals)
    span = y_max - y_min if y_max > y_min else 1.0
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + span * 0.01,
            f"{val:.1f}",
            ha="center", va="bottom", fontsize=8,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Mean height (cm)")
    ax.set_title(
        f"Mean Height of {TOP_N} Tallest Outfield Players per Team\n"
        "(unique players who appeared in at least one match)",
        fontsize=14, fontweight="bold",
    )
    ax.set_ylim(y_min, y_max + span * 0.22)
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(
        handles=[
            Patch(facecolor=FOCUS_COLOR, label=focus_team),
            Patch(facecolor=AVG_BAR_COLOR, label=AVG_LABEL),
            Patch(facecolor=OTHER_COLOR, label="Other teams"),
        ],
        loc="upper right", frameon=True, fontsize=9,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Plot saved to {output_path}")


# ── Entry point ───────────────────────────────────────────────────────


def main(focus_team: str = FOCUS_TEAM, output_path: Path = DEFAULT_OUTPUT) -> None:
    all_team = collect_team_heights()
    if focus_team not in all_team:
        print(f"Warning: {focus_team!r} not found in height data.")

    league_avg = statistics.mean(all_team.values())
    print(f"Teams with height data : {len(all_team)}")
    if focus_team in all_team:
        print(f"{focus_team:22s}: {all_team[focus_team]:5.1f} cm")
    print(f"{'League average':22s}: {league_avg:5.1f} cm")

    plot(all_team, focus_team, output_path)


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    main(team, out)
