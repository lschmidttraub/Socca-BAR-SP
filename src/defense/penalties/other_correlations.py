"""
other_correlations.py

Explores alternative predictors for defensive penalties conceded.
Collects, in a single pass, both the penalty count and several
defensive-third possession metrics for every team, then produces a
multi-panel scatter plot (one panel per candidate predictor).

Candidate predictors (all per game, own defensive third):
  - Ball losses / game       (dispossessed + miscontrol)
  - Pass completion %
  - Clearances / game
  - Touch-based possession % (own touches / total touches in own third)

Usage
-----
    python src/defense/penalties/other_correlations.py
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
ATTACKING_THIRD_X = 80.0

TYPE_PASS         = 30
TYPE_CLEARANCE    = 9
TYPE_DISPOSSESSED = 3
TYPE_MISCONTROL   = 38
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
    """Single-pass collection of defensive-zone metrics + penalties for all teams."""
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":           0,
        "penalties_against": 0,
        "ball_losses":       0,
        "passes":            0,
        "passes_complete":   0,
        "clearances":        0,
        "own_touches":       0,
        "opp_touches":       0,
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
            loc = e.get("location")
            type_id = e.get("type", {}).get("id")
            team_ev = e.get("team", {}).get("name", "")

            # Penalties — attribute to defending team
            if f.is_penalty_shot(e):
                if team_ev == home_ev and count_away:
                    records[away_csv]["penalties_against"] += 1
                elif team_ev == away_ev and count_home:
                    records[home_csv]["penalties_against"] += 1
                continue

            if not loc or type_id == TYPE_PRESSURE:
                continue

            x = float(loc[0])

            if team_ev == home_ev:
                team_csv, opp_csv = home_csv, away_csv
                count_team, count_opp = count_home, count_away
            elif team_ev == away_ev:
                team_csv, opp_csv = away_csv, home_csv
                count_team, count_opp = count_away, count_home
            else:
                continue

            # Touch-based possession (acting team's own third = x < 40)
            if count_team and x < DEFENSIVE_THIRD_X:
                records[team_csv]["own_touches"] += 1
            if count_opp and x > ATTACKING_THIRD_X:
                records[opp_csv]["opp_touches"] += 1

            # Defensive-zone events (own third only)
            if x < DEFENSIVE_THIRD_X and count_team:
                if type_id == TYPE_PASS:
                    records[team_csv]["passes"] += 1
                    if e.get("pass", {}).get("outcome") is None:
                        records[team_csv]["passes_complete"] += 1
                elif type_id in (TYPE_DISPOSSESSED, TYPE_MISCONTROL):
                    records[team_csv]["ball_losses"] += 1
                elif type_id == TYPE_CLEARANCE:
                    records[team_csv]["clearances"] += 1

    return dict(records)


# ── derived metrics ───────────────────────────────────────────────────

def _penalties_per_game(d: dict) -> float:
    return d["penalties_against"] / d["matches"] if d["matches"] else 0.0

def _losses_per_game(d: dict) -> float:
    return d["ball_losses"] / d["matches"] if d["matches"] else 0.0

def _completion_pct(d: dict) -> float:
    return 100.0 * d["passes_complete"] / d["passes"] if d["passes"] else 0.0

def _clearances_per_game(d: dict) -> float:
    return d["clearances"] / d["matches"] if d["matches"] else 0.0

def _touch_possession_pct(d: dict) -> float:
    total = d["own_touches"] + d["opp_touches"]
    return 100.0 * d["own_touches"] / total if total else 0.0


# ── plot ──────────────────────────────────────────────────────────────

def plot_correlations(records: dict[str, dict], save: bool = True, suffix: str = "") -> None:
    predictors = [
        (_losses_per_game,       "Ball losses / game in own third",        "→  more losses"),
        (_completion_pct,        "Pass completion % in own third",          "→  better passing"),
        (_clearances_per_game,   "Clearances / game in own third",          "→  more clearances"),
        (_touch_possession_pct,  "Touch-based possession % in own third",   "→  more possession"),
    ]

    points_base = [
        (team, _penalties_per_game(d), d)
        for team, d in records.items()
        if d["matches"] >= 3
    ]

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.set_facecolor("white")
    fig.suptitle(
        f"Alternative predictors for penalties conceded{' — ' + suffix if suffix else ''}\n"
        "Red = Barcelona  ·  dashed = linear trend  ·  Pearson r in legend",
        fontsize=14, fontweight="bold", y=1.01,
    )

    for ax, (metric_fn, xlabel, xlabel_suffix) in zip(axes.flat, predictors):
        pts = [(team, metric_fn(d), pen_pg) for team, pen_pg, d in points_base]
        xs  = np.array([p[1] for p in pts])
        ys  = np.array([p[2] for p in pts])

        slope, intercept = np.polyfit(xs, ys, 1)
        r = float(np.corrcoef(xs, ys)[0, 1])
        x_line = np.linspace(xs.min() - (xs.max() - xs.min()) * 0.05,
                             xs.max() + (xs.max() - xs.min()) * 0.05, 300)
        y_line = slope * x_line + intercept

        ax.plot(x_line, y_line, color="#888888", lw=1.5, ls="--", zorder=1,
                label=f"r = {r:+.2f}")

        for team, x, y in pts:
            is_barca = team == TEAM
            color  = "#e63946" if is_barca else "steelblue"
            size   = 220 if is_barca else 60
            zorder = 6 if is_barca else 4
            ax.scatter(x, y, color=color, s=size, zorder=zorder,
                       edgecolors="white", linewidth=0.7)
            ax.annotate(
                team, (x, y),
                xytext=(5, 3), textcoords="offset points",
                fontsize=9 if is_barca else 7,
                fontweight="bold" if is_barca else "normal",
                color=color, zorder=zorder,
            )

        ax.set_xlabel(f"{xlabel}  {xlabel_suffix}", fontsize=10)
        ax.set_ylabel("Penalties conceded / game", fontsize=10)
        ax.set_title(xlabel, fontsize=11, fontweight="bold")
        ax.legend(fontsize=10)
        ax.grid(alpha=0.25)

        print(f"  {xlabel:<45s}  r = {r:+.3f}")

    plt.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"correlation_other_penalties{'_' + suffix.replace(' ', '_') if suffix else ''}.png"
        out = ASSETS_DIR / fname
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"\nSaved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    last16 = _last16_teams(DATA)
    print(f"Round of 16 teams ({len(last16)}): {', '.join(sorted(last16))}")

    print("\nCollecting R16 data ...")
    records_r16 = _collect(last16)

    print(f"\n{'Team':30s}  {'Pen/g':>6}  {'Loss/g':>6}  {'Comp%':>6}  {'Clr/g':>6}  {'Poss%':>6}  {'G':>4}")
    for team, d in sorted(records_r16.items()):
        print(
            f"  {team:30s}  {_penalties_per_game(d):6.3f}  {_losses_per_game(d):6.2f}"
            f"  {_completion_pct(d):6.1f}  {_clearances_per_game(d):6.2f}"
            f"  {_touch_possession_pct(d):6.1f}  {d['matches']:4d}"
        )

    print("\nPearson r values (R16 teams):")
    plot_correlations(records_r16, suffix="R16 teams")

    print("\nCollecting all-teams data ...")
    records_all = _collect()
    print("\nPearson r values (all teams):")
    plot_correlations(records_all, suffix="all teams")
