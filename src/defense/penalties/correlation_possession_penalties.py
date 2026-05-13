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

DEFENSIVE_THIRD_X = 40.0
ATTACKING_THIRD_X = 80.0
_MAX_DT = 15.0  # seconds — cap gaps to exclude stoppages / VAR / half-time


def _parse_ts(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

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

def _collect(data_dir: Path, allowed_teams: frozenset[str] | None = None) -> dict[str, dict]:
    """Single-pass collection using time intervals between consecutive events.

    For each interval (event_i → event_{i+1}), dt seconds are added to
    "opp_poss_own_third_s" when the opponent has possession AND the ball is
    in the team's defensive third.  Intervals longer than _MAX_DT are skipped
    to avoid attributing stoppages / VAR / half-time to the last known state.

    Coordinate convention (StatsBomb): each event's x is in the frame of the
    team performing the event, with that team always attacking toward x=120.
      • ball in T's defensive third when T performs: x < DEFENSIVE_THIRD_X
      • ball in T's defensive third when opponent performs: x > ATTACKING_THIRD_X
    """
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":               0,
        "opp_poss_own_third_s":  0.0,
        "total_s":               0.0,
        "penalties_against":     0,
    })

    for row, events in iter_matches(data_dir):
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

        # Sort by period then timestamp; group by period so dt never spans halves
        timed = [
            e for e in events
            if e.get("timestamp") and e.get("period")
        ]
        timed.sort(key=lambda e: (e["period"], e["timestamp"]))

        current_period: int | None = None
        period_buf: list[dict] = []

        def _flush(buf: list[dict]) -> None:
            for i in range(len(buf) - 1):
                ev  = buf[i]
                nxt = buf[i + 1]
                t0  = _parse_ts(ev["timestamp"])
                t1  = _parse_ts(nxt["timestamp"])
                dt  = t1 - t0
                if dt <= 0 or dt > _MAX_DT:
                    continue

                # Accumulate total time (same cap — keeps ratio consistent)
                if count_home:
                    records[home_csv]["total_s"] += dt
                if count_away:
                    records[away_csv]["total_s"] += dt

                loc = ev.get("location")
                if not loc:
                    continue
                x        = float(loc[0])
                ev_team  = ev.get("team", {}).get("name", "")
                poss     = ev.get("possession_team", {}).get("name", "")

                # home team T: is the away team (opponent) in possession in home's defensive third?
                if count_home and poss == away_ev:
                    if (ev_team == away_ev and x > ATTACKING_THIRD_X) or \
                       (ev_team == home_ev and x < DEFENSIVE_THIRD_X):
                        records[home_csv]["opp_poss_own_third_s"] += dt

                # away team T: is the home team (opponent) in possession in away's defensive third?
                if count_away and poss == home_ev:
                    if (ev_team == home_ev and x > ATTACKING_THIRD_X) or \
                       (ev_team == away_ev and x < DEFENSIVE_THIRD_X):
                        records[away_csv]["opp_poss_own_third_s"] += dt

        for ev in timed:
            p = ev["period"]
            if p != current_period:
                _flush(period_buf)
                current_period = p
                period_buf = [ev]
            else:
                period_buf.append(ev)
        _flush(period_buf)

        # Penalties — attribute to defending team
        for e in events:
            if f.is_penalty_shot(e):
                shooter_ev = f.event_team(e)
                if shooter_ev == home_ev and count_away:
                    records[away_csv]["penalties_against"] += 1
                elif shooter_ev == away_ev and count_home:
                    records[home_csv]["penalties_against"] += 1

    return dict(records)


def _possession_pct(d: dict) -> float:
    """Fraction of match time the opponent had the ball in T's defensive third (%)."""
    return 100.0 * d["opp_poss_own_third_s"] / d["total_s"] if d["total_s"] else 0.0


def _penalties_per_game(d: dict) -> float:
    return d["penalties_against"] / d["matches"] if d["matches"] else 0.0


# ── plot ──────────────────────────────────────────────────────────────

def plot_correlation(records: dict[str, dict], save: bool = True, filename: str = "correlation_possession_penalties.png", subtitle: str = "Round of 16 teams") -> None:
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
        "Opponent poss. in own third (% of match time)  →  higher = more exposure",
        fontsize=11,
    )
    ax.set_ylabel(
        "Penalties conceded per game  →  higher = more penalties",
        fontsize=11,
    )
    ax.set_title(
        f"Opponent possession in own defensive third vs penalties conceded — {subtitle}\n"
        "Red = Barcelona  ·  dashed = linear trend  ·  Pearson r shown in legend",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=10)
    ax.grid(alpha=0.25)

    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / filename
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    last16 = _last16_teams(DATA)
    print(f"Round of 16 teams ({len(last16)}): {', '.join(sorted(last16))}")

    print("\nCollecting R16 data ...")
    records_r16 = _collect(DATA, last16)

    print(f"\n{'Team':30s}  {'OppPoss%':>9}  {'Pen/game':>9}  {'Matches':>7}")
    for team, d in sorted(records_r16.items()):
        print(
            f"  {team:30s}  {_possession_pct(d):8.1f}%  "
            f"{_penalties_per_game(d):9.3f}  {d['matches']:7d}"
        )
    plot_correlation(records_r16, filename="correlation_possession_penalties.png", subtitle="Round of 16 teams")

    print("\nCollecting all-teams data ...")
    records_all = _collect(DATA)

    print(f"\n{'Team':30s}  {'OppPoss%':>9}  {'Pen/game':>9}  {'Matches':>7}")
    for team, d in sorted(records_all.items()):
        print(
            f"  {team:30s}  {_possession_pct(d):8.1f}%  "
            f"{_penalties_per_game(d):9.3f}  {d['matches']:7d}"
        )
    plot_correlation(records_all, filename="correlation_possession_penalties_all_teams.png", subtitle="all teams")
