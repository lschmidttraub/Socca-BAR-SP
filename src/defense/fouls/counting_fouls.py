"""
counting_fouls.py

Bar charts comparing foul counts across all CL teams:
  1. Fouls per game — stacked bar (yellow-card fouls dark, rest light).
  2. Yellow card rate — % of fouls that resulted in a yellow card.

Barcelona is highlighted in red.

Usage
-----
    python src/defense/fouls/counting_fouls.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT  = PROJECT_ROOT / "src"
FOULS_DIR = Path(__file__).parent

for _p in (str(SRC_ROOT), str(FOULS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fouls import is_foul_committed, foul_card
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "fouls"
DATA = PROJECT_ROOT / "data" / "statsbomb"
TEAM = "Barcelona"


# ── data collection ───────────────────────────────────────────────────

def _collect(data_dir: Path) -> dict[str, dict]:
    """Count fouls and yellow cards per team across all matches."""
    records: dict[str, dict] = defaultdict(lambda: {
        "matches": 0,
        "fouls":   0,
        "yellows": 0,   # Yellow Card only (not second yellow or straight red)
    })

    for row, events in iter_matches(data_dir):
        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        if not home_csv or not away_csv:
            continue

        home_ev = _team_in_match(home_csv, row, events) or home_csv
        away_ev = _team_in_match(away_csv, row, events) or away_csv

        records[home_csv]["matches"] += 1
        records[away_csv]["matches"] += 1

        for e in events:
            if not is_foul_committed(e):
                continue
            team_ev = e.get("team", {}).get("name", "")
            if team_ev == home_ev:
                team_csv = home_csv
            elif team_ev == away_ev:
                team_csv = away_csv
            else:
                continue

            records[team_csv]["fouls"] += 1
            if foul_card(e) == "Yellow Card":
                records[team_csv]["yellows"] += 1

    return dict(records)


def _fouls_per_game(d: dict) -> float:
    return d["fouls"] / d["matches"] if d["matches"] else 0.0

def _yellows_per_game(d: dict) -> float:
    return d["yellows"] / d["matches"] if d["matches"] else 0.0

def _yellow_rate(d: dict) -> float:
    return 100.0 * d["yellows"] / d["fouls"] if d["fouls"] else 0.0


# ── plots ─────────────────────────────────────────────────────────────

def plot_fouls_per_game(records: dict[str, dict], save: bool = True) -> None:
    """Stacked horizontal bar: fouls/game split by yellow-card fouls vs rest."""
    rows = sorted(
        [(team, _fouls_per_game(d), _yellows_per_game(d)) for team, d in records.items()],
        key=lambda x: x[1],
    )
    teams      = [r[0] for r in rows]
    total_fpg  = [r[1] for r in rows]
    yellow_fpg = [r[2] for r in rows]
    other_fpg  = [t - y for t, y in zip(total_fpg, yellow_fpg)]

    fig, ax = plt.subplots(figsize=(12, max(8, len(teams) * 0.45)))
    fig.patch.set_facecolor("white")

    for i, (team, total, yellow, other) in enumerate(
        zip(teams, total_fpg, yellow_fpg, other_fpg)
    ):
        is_barca = (team == TEAM)
        c_other  = "#e63946" if is_barca else "#4895ef"
        c_yellow = "#c9184a" if is_barca else "#f4a261"

        ax.barh(i, other,  color=c_other,  edgecolor="white", linewidth=0.4)
        ax.barh(i, yellow, left=other, color=c_yellow, edgecolor="white", linewidth=0.4)
        ax.text(
            total + 0.05, i,
            f"{total:.2f}  ({yellow:.2f} yellow)",
            va="center", fontsize=7.5, color="#333333",
        )

    ax.set_yticks(range(len(teams)))
    ax.set_yticklabels(teams, fontsize=9)
    ax.set_xlabel("Fouls per game", fontsize=11)
    ax.set_title(
        "Fouls committed per game — all CL teams\n"
        "Red = Barcelona  ·  dark portion = fouls with a yellow card",
        fontsize=13, fontweight="bold",
    )

    league_avg = sum(total_fpg) / len(total_fpg)
    ax.axvline(league_avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {league_avg:.2f}")

    ax.legend(handles=[
        Patch(facecolor="#4895ef", label="Other teams — no card"),
        Patch(facecolor="#f4a261", label="Other teams — yellow card"),
        Patch(facecolor="#e63946", label="Barcelona — no card"),
        Patch(facecolor="#c9184a", label="Barcelona — yellow card"),
        plt.Line2D([0], [0], color="black", ls="--", lw=1.2,
                   label=f"League avg: {league_avg:.2f} fouls/game"),
    ], fontsize=8, loc="lower right")

    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "fouls_per_game.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


def plot_yellow_rate(records: dict[str, dict], save: bool = True) -> None:
    """Horizontal bar chart of yellow card rate (% of fouls → yellow card)."""
    rows = sorted(
        [(team, _yellow_rate(d), d["fouls"]) for team, d in records.items()],
        key=lambda x: x[1],
    )
    teams  = [r[0] for r in rows]
    rates  = [r[1] for r in rows]
    counts = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(12, max(8, len(teams) * 0.45)))
    fig.patch.set_facecolor("white")

    colors = ["#e63946" if t == TEAM else "steelblue" for t in teams]
    bars = ax.barh(teams, rates, color=colors, edgecolor="white", linewidth=0.4)

    for bar, rate, n in zip(bars, rates, counts):
        ax.text(
            rate + 0.3, bar.get_y() + bar.get_height() / 2,
            f"{rate:.1f}%  (n={n})",
            va="center", fontsize=7.5, color="#333333",
        )

    league_avg = sum(rates) / len(rates)
    ax.axvline(league_avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {league_avg:.1f}%")

    ax.set_xlabel("Yellow cards per 100 fouls (%)", fontsize=11)
    ax.set_title(
        "Yellow card rate per foul — all CL teams\n"
        "Red = Barcelona  ·  dashed = league average",
        fontsize=13, fontweight="bold",
    )
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    ax.tick_params(labelsize=9)

    fig.tight_layout()
    plt.show()

    if save:
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = ASSETS_DIR / "fouls_yellow_rate.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")


# ── entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_theme()
    print("Collecting foul data ...")
    records = _collect(DATA)

    print(f"\n{'Team':30s}  {'Matches':>7}  {'Fouls':>6}  {'F/game':>7}  {'Yellows':>7}  {'Y-rate':>7}")
    for team, d in sorted(records.items()):
        print(
            f"  {team:30s}  {d['matches']:7d}  {d['fouls']:6d}  "
            f"{_fouls_per_game(d):7.2f}  {d['yellows']:7d}  {_yellow_rate(d):6.1f}%"
        )

    plot_fouls_per_game(records)
    plot_yellow_rate(records)
