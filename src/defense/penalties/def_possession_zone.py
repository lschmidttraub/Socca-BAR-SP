"""
def_possession_zone.py

Compares how all CL teams handle possession in their own defensive third
(x < 40 in the acting team's attacking frame — own goal at x = 0).

Metrics per team (normalised by games played)
---------------------------------------------
  - Pass completion rate (%)  in defensive zone
  - Ball losses / game        (dispossessed + miscontrol) in defensive zone
  - Clearances / game         in defensive zone

Plots produced
--------------
  def_possession_completion.png  — bar chart, pass completion %
  def_possession_losses.png      — bar chart, ball losses / game
  def_possession_scatter.png     — scatter: completion % vs losses / game

Usage
-----
    python src/defense/penalties/def_possession_zone.py
"""

from __future__ import annotations

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
from stats.viz.style import FOCUS_COLOR, AVG_COLOR, NEUTRAL_COLOR, apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "penalties"
DATA = PROJECT_ROOT / "data" / "statsbomb"
TEAM = "Barcelona"

# StatsBomb type IDs
TYPE_PASS         = 30
TYPE_CLEARANCE    = 9
TYPE_DISPOSSESSED = 3
TYPE_MISCONTROL   = 38
TYPE_PRESSURE     = 17   # off-ball — excluded from possession counts

DEFENSIVE_THIRD_X      = 40.0   # x <  40 in team's frame = own defensive third
ATTACKING_THIRD_X      = 80.0   # x >  80 in team's frame = opponent's defensive third


# ── data collection ───────────────────────────────────────────────────

def _collect(data_dir: Path) -> dict[str, dict]:
    """Return per-team possession stats in their own defensive third.

    Possession % logic
    ------------------
    Events are stored in the acting team's attacking frame (they attack
    toward x = 120).  So:
      - team acts at x < 40  → team has the ball in their OWN defensive zone
      - team acts at x > 80  → team is in the OPPONENT's defensive zone
                               (same physical area, opposite frame)

    Pressure events (type 17) are off-ball and excluded from possession counts.
    """
    records: dict[str, dict] = defaultdict(lambda: {
        "matches":          0,
        "passes":           0,
        "passes_complete":  0,
        "ball_losses":      0,
        "clearances":       0,
        "def_own_touches":  0,   # acting team touches in own defensive zone
        "def_opp_touches":  0,   # opponent touches in this team's defensive zone
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
            loc = e.get("location")
            if not loc:
                continue

            type_id = e.get("type", {}).get("id")
            if type_id == TYPE_PRESSURE:
                continue  # off-ball event, skip for possession

            x = float(loc[0])
            team_ev = f.event_team(e)

            if team_ev == home_ev:
                team_csv, opp_csv = home_csv, away_csv
            elif team_ev == away_ev:
                team_csv, opp_csv = away_csv, home_csv
            else:
                continue

            # Possession zone counts
            if x < DEFENSIVE_THIRD_X:
                # Team has ball in their own defensive zone
                records[team_csv]["def_own_touches"] += 1
            elif x > ATTACKING_THIRD_X:
                # Team is in the opponent's defensive zone → attribute to opponent
                records[opp_csv]["def_opp_touches"] += 1

            # Per-zone detailed stats (only for own defensive third)
            if x < DEFENSIVE_THIRD_X:
                if type_id == TYPE_PASS:
                    records[team_csv]["passes"] += 1
                    if e.get("pass", {}).get("outcome") is None:
                        records[team_csv]["passes_complete"] += 1
                elif type_id in (TYPE_DISPOSSESSED, TYPE_MISCONTROL):
                    records[team_csv]["ball_losses"] += 1
                elif type_id == TYPE_CLEARANCE:
                    records[team_csv]["clearances"] += 1

    return dict(records)


# ── helpers ───────────────────────────────────────────────────────────

def _completion_rate(d: dict) -> float:
    return 100.0 * d["passes_complete"] / d["passes"] if d["passes"] else 0.0

def _losses_per_game(d: dict) -> float:
    return d["ball_losses"] / d["matches"] if d["matches"] else 0.0

def _clearances_per_game(d: dict) -> float:
    return d["clearances"] / d["matches"] if d["matches"] else 0.0

def _possession_pct(d: dict) -> float:
    total = d["def_own_touches"] + d["def_opp_touches"]
    return 100.0 * d["def_own_touches"] / total if total else 0.0


# ── plots ─────────────────────────────────────────────────────────────

def _bar_chart(
    records: dict[str, dict],
    metric_fn,
    title: str,
    ylabel: str,
    out_path: Path,
    ascending: bool = False,
    fmt: str = ".1f",
) -> None:
    """Generic bar chart for a single metric across all teams."""
    from matplotlib.patches import Patch

    pairs = sorted(
        [(team, metric_fn(d)) for team, d in records.items()],
        key=lambda x: x[1],
        reverse=not ascending,
    )
    teams, values = zip(*pairs)
    colors = [AVG_COLOR if t == TEAM else FOCUS_COLOR for t in teams]

    fig, ax = plt.subplots(figsize=(14, 6))
    bars = ax.bar(range(len(teams)), values, color=colors, edgecolor="white", linewidth=0.4)

    top = max(values)
    for i, (bar, val) in enumerate(zip(bars, values)):
        ax.text(i, val + top * 0.012, f"{val:{fmt}}",
                ha="center", va="bottom", fontsize=7.5, color="#333333")

    ax.set_xticks(range(len(teams)))
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlim(-0.6, len(teams) - 0.4)

    ax.legend(handles=[
        Patch(facecolor=AVG_COLOR,   label="Barcelona"),
        Patch(facecolor=FOCUS_COLOR, label="Other teams"),
    ], fontsize=9)

    fig.tight_layout()
    plt.show()
    save_fig(fig, out_path, tight=False)
    print(f"  Saved: {out_path.name}")


def _scatter_plot(records: dict[str, dict], out_path: Path) -> None:
    """Scatter: pass completion % (x) vs ball losses/game (y).

    Bottom-right quadrant = best (high completion, low losses).
    Median lines divide the chart into four quadrants.
    """
    points = []
    for team, d in records.items():
        if d["matches"] == 0 or d["passes"] == 0:
            continue
        points.append((team, _completion_rate(d), _losses_per_game(d)))

    comps   = [p[1] for p in points]
    losses  = [p[2] for p in points]
    med_comp   = float(np.median(comps))
    med_losses = float(np.median(losses))

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor("white")

    # Quadrant shading
    xlim = (min(comps) - 1.5, max(comps) + 1.5)
    ylim = (max(0, min(losses) - 0.3), max(losses) + 0.5)
    ax.fill_between([med_comp, xlim[1]], med_losses, ylim[1],
                    color="#fdecea", alpha=0.45, zorder=0)   # high comp, high loss
    ax.fill_between([xlim[0], med_comp], ylim[0], med_losses,
                    color="#fdecea", alpha=0.45, zorder=0)   # low comp, low loss
    ax.fill_between([med_comp, xlim[1]], ylim[0], med_losses,
                    color="#e8f5e9", alpha=0.55, zorder=0)   # ideal: high comp, low loss
    ax.fill_between([xlim[0], med_comp], med_losses, ylim[1],
                    color="#ffebee", alpha=0.55, zorder=0)   # worst: low comp, high loss

    ax.axvline(med_comp,   color="#bbbbbb", lw=0.9, ls="--", zorder=1)
    ax.axhline(med_losses, color="#bbbbbb", lw=0.9, ls="--", zorder=1)

    for team, comp, loss in points:
        is_barca = team == TEAM
        color  = AVG_COLOR if is_barca else FOCUS_COLOR
        size   = 220 if is_barca else 70
        zorder = 6 if is_barca else 4
        ax.scatter(comp, loss, color=color, s=size, zorder=zorder,
                   edgecolors="white", linewidth=0.7)
        ax.annotate(
            team, (comp, loss),
            xytext=(6, 4), textcoords="offset points",
            fontsize=8.5 if is_barca else 7.5,
            fontweight="bold" if is_barca else "normal",
            color=color, zorder=zorder,
        )

    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_xlabel("Pass completion % in defensive third  →  better", fontsize=11)
    ax.set_ylabel("Ball losses per game in defensive third  →  worse", fontsize=11)
    ax.set_title(
        "Defensive zone possession quality — all CL teams",
        fontsize=14, fontweight="bold",
    )

    # Quadrant labels
    kw = dict(fontsize=8, color="#999999", ha="center", va="center", style="italic")
    ax.text((med_comp + xlim[1]) / 2, (med_losses + ylim[1]) / 2, "risky\n(complete but lose often)", **kw)
    ax.text((xlim[0] + med_comp) / 2, (ylim[0] + med_losses) / 2, "safe\n(few losses, lower completion)", **kw)
    ax.text((med_comp + xlim[1]) / 2, (ylim[0] + med_losses) / 2, "ideal\n(high completion, few losses)", **kw)
    ax.text((xlim[0] + med_comp) / 2, (med_losses + ylim[1]) / 2, "vulnerable\n(poor completion, many losses)", **kw)

    fig.tight_layout()
    plt.show()
    save_fig(fig, out_path, tight=False)
    print(f"  Saved: {out_path.name}")


# ── entry point ───────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_DIR) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting defensive zone possession data ...")
    records = _collect(data_dir)

    print("\nPer-team summary (defensive third):")
    for team, d in sorted(records.items()):
        print(
            f"  {team:30s}  "
            f"poss%={_possession_pct(d):.1f}%  "
            f"completion={_completion_rate(d):.1f}%  "
            f"losses/game={_losses_per_game(d):.2f}  "
            f"clearances/game={_clearances_per_game(d):.2f}  "
            f"({d['matches']} games)"
        )

    print("\nBuilding bar chart: possession % in own defensive third ...")
    _bar_chart(
        records, _possession_pct,
        title="Possession % in own defensive third — all CL teams",
        ylabel="Possession % in own defensive third",
        out_path=output_dir / "def_possession_pct.png",
        ascending=False,
        fmt=".1f",
    )

    print("Building bar chart: pass completion rate ...")
    _bar_chart(
        records, _completion_rate,
        title="Pass completion % in own defensive third — all CL teams",
        ylabel="Pass completion (%)",
        out_path=output_dir / "def_possession_completion.png",
        ascending=False,
        fmt=".1f",
    )

    print("Building bar chart: ball losses per game ...")
    _bar_chart(
        records, _losses_per_game,
        title="Ball losses per game in own defensive third — all CL teams",
        ylabel="Ball losses / game  (dispossessed + miscontrol)",
        out_path=output_dir / "def_possession_losses.png",
        ascending=True,   # fewer = better, sort ascending (least = best)
        fmt=".2f",
    )

    print("Building scatter plot ...")
    _scatter_plot(records, output_dir / "def_possession_scatter.png")

    print("\nDone.")


if __name__ == "__main__":
    run()
