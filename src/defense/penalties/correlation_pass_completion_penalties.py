"""
correlation_pass_completion_penalties.py

Scatter plot: pass completion % in own defensive third (x) vs penalties conceded
per game (y) for teams that reached the Round of 16.

Barcelona is highlighted in red. A linear regression line and Pearson r are shown.

Usage
-----
    python src/defense/penalties/correlation_pass_completion_penalties.py
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
SRC_ROOT     = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import apply_theme

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "penalties"
DATA       = PROJECT_ROOT / "data" / "statsbomb"
TEAM       = "Barcelona"

DEFENSIVE_THIRD_X = 40.0
TYPE_PASS         = 30
TYPE_PRESSURE     = 17

_R16_DATES = {"2026-03-10", "2026-03-11", "2026-03-17", "2026-03-18"}


# ── helpers ───────────────────────────────────────────────────────────

def _last16_teams(data_dir: Path) -> frozenset[str]:
    csv_path = data_dir.parent / "matches.csv"
    if not csv_path.exists():
        csv_path = data_dir / "matches.csv"
    teams: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("date", "").strip() in _R16_DATES:
                for key in ("home", "away"):
                    t = row.get(key, "").strip()
                    if t:
                        teams.add(t)
    return frozenset(teams)


# ── data collection ───────────────────────────────────────────────────

def _collect(allowed_teams: frozenset[str] | None = None) -> dict[str, dict]:
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":           0,
        "passes":            0,
        "passes_complete":   0,
        "penalties_against": 0,
    })

    for row, events in iter_matches(DATA):
        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        if not home_csv or not away_csv:
            continue
        if allowed_teams is not None:
            if home_csv not in allowed_teams and away_csv not in allowed_teams:
                continue

        home_ev = _team_in_match(home_csv, row, events) or home_csv
        away_ev = _team_in_match(away_csv, row, events) or away_csv

        count_home = allowed_teams is None or home_csv in allowed_teams
        count_away = allowed_teams is None or away_csv in allowed_teams

        if count_home:
            records[home_csv]["matches"] += 1
        if count_away:
            records[away_csv]["matches"] += 1

        for e in events:
            type_id = e.get("type", {}).get("id")
            team_ev = e.get("team", {}).get("name", "")

            if f.is_penalty_shot(e):
                if team_ev == home_ev and count_away:
                    records[away_csv]["penalties_against"] += 1
                elif team_ev == away_ev and count_home:
                    records[home_csv]["penalties_against"] += 1
                continue

            loc = e.get("location")
            if not loc or type_id != TYPE_PASS:
                continue

            x = float(loc[0])
            if x >= DEFENSIVE_THIRD_X:
                continue

            if team_ev == home_ev and count_home:
                records[home_csv]["passes"] += 1
                if e.get("pass", {}).get("outcome") is None:
                    records[home_csv]["passes_complete"] += 1
            elif team_ev == away_ev and count_away:
                records[away_csv]["passes"] += 1
                if e.get("pass", {}).get("outcome") is None:
                    records[away_csv]["passes_complete"] += 1

    return dict(records)


def _completion_pct(d: dict) -> float:
    return 100.0 * d["passes_complete"] / d["passes"] if d["passes"] else 0.0

def _penalties_per_game(d: dict) -> float:
    return d["penalties_against"] / d["matches"] if d["matches"] else 0.0


# ── plots ─────────────────────────────────────────────────────────────

def plot_completion_bar(records: dict[str, dict], save: bool = True) -> None:
    pairs = sorted(
        [(team, _completion_pct(d)) for team, d in records.items() if d["passes"] > 0],
        key=lambda x: x[1], reverse=True,
    )
    teams, values = zip(*pairs)
    colors = ["#e63946" if t == TEAM else "steelblue" for t in teams]

    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("white")
    bars = ax.bar(range(len(teams)), values, color=colors, edgecolor="white", linewidth=0.4)

    top = max(values)
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(i, val + top * 0.012, f"{val:.1f}%",
                ha="center", va="bottom", fontsize=7.5, color="#333333")

    league_avg = float(np.mean(values))
    ax.axhline(league_avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {league_avg:.1f}%")

    ax.set_xticks(range(len(teams)))
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Pass completion % in own defensive third", fontsize=11)
    ax.set_title(
        "Pass completion % in own defensive third — Round of 16 teams\n"
        "Red = Barcelona  ·  dashed = league average",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "pass_completion_own_third.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


def plot_correlation(records: dict[str, dict], save: bool = True) -> None:
    points = [
        (team, _completion_pct(d), _penalties_per_game(d))
        for team, d in records.items()
        if d["matches"] >= 3
    ]

    xs = np.array([p[1] for p in points])
    ys = np.array([p[2] for p in points])

    slope, intercept = np.polyfit(xs, ys, 1)
    r = float(np.corrcoef(xs, ys)[0, 1])
    x_line = np.linspace(xs.min() - 1.5, xs.max() + 1.5, 300)
    y_line = slope * x_line + intercept

    fig, ax = plt.subplots(figsize=(13, 8))
    fig.patch.set_facecolor("white")

    ax.plot(x_line, y_line, color="#888888", lw=1.5, ls="--", zorder=1,
            label=f"Linear fit  (r = {r:+.2f})")

    for team, x, y in points:
        is_barca = team == TEAM
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

    ax.set_xlabel("Pass completion % in own defensive third  →  better passing", fontsize=11)
    ax.set_ylabel("Penalties conceded per game  →  more penalties", fontsize=11)
    ax.set_title(
        "Pass completion % in own third vs penalties conceded — Round of 16 teams\n"
        "Red = Barcelona  ·  dashed = linear trend  ·  Pearson r shown in legend",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "correlation_pass_completion_penalties.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    last16 = _last16_teams(DATA)
    print(f"Round of 16 teams ({len(last16)}): {', '.join(sorted(last16))}")

    print("\nCollecting R16 data ...")
    records = _collect(last16)

    print(f"\n{'Team':30s}  {'Comp%':>6}  {'Pen/game':>9}  {'Matches':>7}")
    for team, d in sorted(records.items()):
        print(
            f"  {team:30s}  {_completion_pct(d):6.1f}%  "
            f"{_penalties_per_game(d):9.3f}  {d['matches']:7d}"
        )

    plot_completion_bar(records)
    plot_correlation(records)
