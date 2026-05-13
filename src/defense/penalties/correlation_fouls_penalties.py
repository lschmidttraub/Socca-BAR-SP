"""
correlation_fouls_penalties.py

Scatter plot: fouls committed per game (x) vs penalties conceded per game (y)
for teams that reached the Round of 16.

Barcelona is highlighted in red.  A linear regression line and Pearson r are shown.

Usage
-----
    python src/defense/penalties/correlation_fouls_penalties.py
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
SRC_ROOT   = PROJECT_ROOT / "src"
FOULS_DIR  = PROJECT_ROOT / "src" / "defense" / "fouls"

for _p in (str(SRC_ROOT), str(FOULS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fouls import is_foul_committed, foul_card
from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "penalties"
_SB_ROOT   = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS  = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
DATA       = _SB_ROOT
TEAM = "Barcelona"

# Round of 16 first and second legs (Mar 10-11 and Mar 17-18, 2026)
_R16_DATES = {"2026-03-10", "2026-03-11", "2026-03-17", "2026-03-18"}


# ── helpers ───────────────────────────────────────────────────────────

def _last16_teams(data_dir: Path) -> frozenset[str]:
    """Return team names (as in matches.csv) that played in the Round of 16."""
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
    """Single-pass collection of fouls committed and penalties conceded per team."""
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":           0,
        "fouls":             0,
        "penalties_against": 0,
    })

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
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
                if f.is_penalty_shot(e):
                    shooter_ev = f.event_team(e)
                    if shooter_ev == home_ev and away_csv in allowed_teams:
                        records[away_csv]["penalties_against"] += 1
                    elif shooter_ev == away_ev and home_csv in allowed_teams:
                        records[home_csv]["penalties_against"] += 1
                    continue

                if not is_foul_committed(e):
                    continue
                team_ev = e.get("team", {}).get("name", "")
                if team_ev == home_ev and home_csv in allowed_teams:
                    records[home_csv]["fouls"] += 1
                elif team_ev == away_ev and away_csv in allowed_teams:
                    records[away_csv]["fouls"] += 1

    return dict(records)


def _fouls_per_game(d: dict) -> float:
    return d["fouls"] / d["matches"] if d["matches"] else 0.0

def _penalties_per_game(d: dict) -> float:
    return d["penalties_against"] / d["matches"] if d["matches"] else 0.0


# ── plot ──────────────────────────────────────────────────────────────

def plot_correlation(records: dict[str, dict], save: bool = True) -> None:
    points = [
        (team, _fouls_per_game(d), _penalties_per_game(d))
        for team, d in records.items()
        if d["matches"] >= 1
    ]

    teams = [p[0] for p in points]
    xs    = np.array([p[1] for p in points])
    ys    = np.array([p[2] for p in points])

    slope, intercept = np.polyfit(xs, ys, 1)
    r = float(np.corrcoef(xs, ys)[0, 1])
    x_line = np.linspace(xs.min() - 0.5, xs.max() + 0.5, 300)
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
        "Fouls committed per game  →  more fouls",
        fontsize=11,
    )
    ax.set_ylabel(
        "Penalties conceded per game  →  more penalties",
        fontsize=11,
    )
    ax.set_title(
        "Fouls committed vs penalties conceded — Round of 16 teams\n"
        "Red = Barcelona  ·  dashed = linear trend  ·  Pearson r shown in legend",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "correlation_fouls_penalties.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    last16 = _last16_teams(DATA)
    print(f"Round of 16 teams ({len(last16)}): {', '.join(sorted(last16))}")

    print("\nCollecting data ...")
    records = _collect(DATA, last16)

    print(f"\n{'Team':30s}  {'Matches':>7}  {'F/game':>7}  {'Pen/game':>9}")
    for team, d in sorted(records.items()):
        print(
            f"  {team:30s}  {d['matches']:7d}  "
            f"{_fouls_per_game(d):7.2f}  {_penalties_per_game(d):9.3f}"
        )

    plot_correlation(records)
