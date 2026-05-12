"""
correlation_possession_penalties.py

Scatter plot: possession % in own defensive third (x) vs penalties conceded per game (y)
for teams that reached the Round of 16.  Tests the hypothesis that teams with higher
defensive-third possession face fewer penalties.

Barcelona is highlighted in red.  A linear regression line and Pearson r are shown.

Usage
-----
    python src/defense/penalties/correlation_possession_penalties.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "penalties"
DATA = PROJECT_ROOT / "data" / "statsbomb"
TEAM = "Barcelona"

TYPE_PRESSURE     = 17
DEFENSIVE_THIRD_X = 40.0
ATTACKING_THIRD_X = 80.0

# Round of 16 first and second legs (Mar 10-11 and Mar 17-18, 2026)
_R16_DATES = {"2026-03-10", "2026-03-11", "2026-03-17", "2026-03-18"}


# ── helpers ───────────────────────────────────────────────────────────

def _last16_teams(data_dir: Path) -> frozenset[str]:
    """Return the set of team names (as they appear in matches.csv) that played in the R16."""
    csv_path = data_dir.parent / "matches.csv"
    if not csv_path.exists():
        csv_path = data_dir / "matches.csv"
    teams: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("date", "").strip() in _R16_DATES:
                home = row.get("home", "").strip()
                away = row.get("away", "").strip()
                if home:
                    teams.add(home)
                if away:
                    teams.add(away)
    return frozenset(teams)


# ── data collection ───────────────────────────────────────────────────

def _collect(data_dir: Path, allowed_teams: frozenset[str]) -> dict[str, dict]:
    """Single-pass collection of defensive-third possession and penalty concessions per team.

    Only teams in *allowed_teams* are counted; matches where neither team is in the
    set are skipped entirely.
    """
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":           0,
        "def_own_touches":   0,
        "def_opp_touches":   0,
        "penalties_against": 0,
    })

    for row, events in iter_matches(data_dir):
        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        if not home_csv or not away_csv:
            continue
        if home_csv not in allowed_teams and away_csv not in allowed_teams:
            continue

        home_ev = _team_in_match(home_csv, row, events) or home_csv
        away_ev = _team_in_match(away_csv, row, events) or away_csv

        if home_csv in allowed_teams:
            records[home_csv]["matches"] += 1
        if away_csv in allowed_teams:
            records[away_csv]["matches"] += 1

        for e in events:
            # Penalty shots — attribute to the defending team
            if f.is_penalty_shot(e):
                shooter_ev = f.event_team(e)
                if shooter_ev == home_ev and away_csv in allowed_teams:
                    records[away_csv]["penalties_against"] += 1
                elif shooter_ev == away_ev and home_csv in allowed_teams:
                    records[home_csv]["penalties_against"] += 1
                continue

            loc = e.get("location")
            type_id = e.get("type", {}).get("id")
            if not loc or type_id == TYPE_PRESSURE:
                continue

            x = float(loc[0])
            team_ev = f.event_team(e)

            if team_ev == home_ev:
                team_csv, opp_csv = home_csv, away_csv
            elif team_ev == away_ev:
                team_csv, opp_csv = away_csv, home_csv
            else:
                continue

            # x < 40 → team touches in their own defensive third
            # x > 80 → team is in the opponent's defensive third (attribute to opponent)
            if x < DEFENSIVE_THIRD_X and team_csv in allowed_teams:
                records[team_csv]["def_own_touches"] += 1
            elif x > ATTACKING_THIRD_X and opp_csv in allowed_teams:
                records[opp_csv]["def_opp_touches"] += 1

    return dict(records)


def _possession_pct(d: dict) -> float:
    total = d["def_own_touches"] + d["def_opp_touches"]
    return 100.0 * d["def_own_touches"] / total if total else 0.0


def _penalties_per_game(d: dict) -> float:
    return d["penalties_against"] / d["matches"] if d["matches"] else 0.0


# ── plot ──────────────────────────────────────────────────────────────

def plot_correlation(records: dict[str, dict], save: bool = True) -> None:
    points = [
        (team, _possession_pct(d), _penalties_per_game(d))
        for team, d in records.items()
        if d["matches"] >= 3
    ]

    teams = [p[0] for p in points]
    xs    = np.array([p[1] for p in points])
    ys    = np.array([p[2] for p in points])

    slope, intercept = np.polyfit(xs, ys, 1)
    r = float(np.corrcoef(xs, ys)[0, 1])
    x_line = np.linspace(xs.min() - 1.5, xs.max() + 1.5, 300)
    y_line = slope * x_line + intercept

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_facecolor("white")

    ax.plot(
        x_line, y_line,
        color="#888888", lw=1.5, ls="--", zorder=1,
        label=f"Linear fit  (r = {r:+.2f})",
    )

    for team, x, y in points:
        is_barca = (team == TEAM)
        color  = "#e63946" if is_barca else "steelblue"
        size   = 240 if is_barca else 80
        zorder = 6 if is_barca else 4
        ax.scatter(x, y, color=color, s=size, zorder=zorder,
                   edgecolors="white", linewidth=0.8)
        ax.annotate(
            team, (x, y),
            xytext=(6, 4), textcoords="offset points",
            fontsize=9.5 if is_barca else 7.5,
            fontweight="bold" if is_barca else "normal",
            color=color, zorder=zorder,
        )

    ax.set_xlabel(
        "Possession % in own defensive third  →  higher = more possession",
        fontsize=11,
    )
    ax.set_ylabel(
        "Penalties conceded per game  →  higher = more penalties",
        fontsize=11,
    )
    ax.set_title(
        "Defensive-third possession vs penalties conceded — Round of 16 teams\n"
        "Red = Barcelona  ·  dashed = linear trend  ·  Pearson r shown in legend",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "correlation_possession_penalties.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    last16 = _last16_teams(DATA)
    print(f"Round of 16 teams ({len(last16)}): {', '.join(sorted(last16))}")

    print("\nCollecting data ...")
    records = _collect(DATA, last16)

    print(f"\n{'Team':30s}  {'Poss%':>6}  {'Pen/game':>9}  {'Matches':>7}")
    for team, d in sorted(records.items()):
        print(
            f"  {team:30s}  {_possession_pct(d):6.1f}%  "
            f"{_penalties_per_game(d):9.3f}  {d['matches']:7d}"
        )

    plot_correlation(records)
