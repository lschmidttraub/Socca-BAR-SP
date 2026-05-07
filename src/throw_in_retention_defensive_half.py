"""
throw_in_retention_defensive_half.py

Retention rate of throw-ins taken in the defensive half within 5 seconds.

Retention is measured using StatsBomb's possession_team field: if possession
transfers to the opponent within WINDOW seconds after the throw-in, the
throw-in is considered "not retained".

Coordinates are normalized so the defensive goal is always at x=120 (right),
allowing all throw-ins to be plotted on a single half-pitch view.

Usage:
    python src/throw_in_retention_defensive_half.py
"""

import sys
import io
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Ensure project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

# Windows terminals may not support all Unicode characters in team names
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.stats import filters as f
from src.stats.data import iter_matches
from src.stats.viz.style import (
    AVG_COLOR,
    FOCUS_COLOR,
    NEUTRAL_COLOR,
    apply_theme,
    save_fig,
)

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "statsbomb"
ASSETS_DIR = ROOT / "assets"
TEAM = "Barcelona"
WINDOW = 5.0  # seconds to scan after the throw-in


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_ts(ts: str) -> float:
    """Convert 'HH:MM:SS.mmm' timestamp to total seconds."""
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def build_attack_dirs(events: list[dict]) -> dict[tuple, str]:
    """
    Return {(period, team): 'right'|'left'} using goal kick locations.

    Goal kicks near x < 60 mean the team defends the x=0 end, so they
    attack toward x=120 ('right'). Falls back to median pass direction.
    """
    gk_xs: dict[tuple, list[float]] = defaultdict(list)
    pass_dxs: dict[tuple, list[float]] = defaultdict(list)

    for ev in events:
        period = ev.get("period")
        team = ev.get("team", {}).get("name", "")
        if not team or period is None:
            continue
        key = (period, team)

        if f.is_goal_kick(ev):
            loc = ev.get("location")
            if loc:
                gk_xs[key].append(loc[0])

        if f.is_pass(ev):
            loc = ev.get("location")
            end = ev.get("pass", {}).get("end_location")
            if loc and end:
                pass_dxs[key].append(end[0] - loc[0])

    result: dict[tuple, str] = {}
    for key in set(gk_xs) | set(pass_dxs):
        if gk_xs[key]:
            med = sorted(gk_xs[key])[len(gk_xs[key]) // 2]
            result[key] = "right" if med < 60 else "left"
        elif pass_dxs[key]:
            med = sorted(pass_dxs[key])[len(pass_dxs[key]) // 2]
            result[key] = "right" if med > 0 else "left"

    return result


def normalize(x: float, y: float, attack_dir: str) -> tuple[float, float]:
    """
    Rotate coordinates so the defensive goal is always at x=120 (right side).

    After normalization the defensive half spans x=60..120, matching
    mplsoccer's Pitch(half=True) view.
    """
    if attack_dir == "right":
        # team attacks toward x=120, defensive end is at x=0 → flip
        return 120 - x, 80 - y
    return x, y


# ── Per-match analysis ────────────────────────────────────────────────────────

def analyze_events(events: list[dict]) -> list[dict]:
    attack_dirs = build_attack_dirs(events)
    rows: list[dict] = []

    for i, ev in enumerate(events):
        if not f.is_throw_in(ev):
            continue

        team = f.event_team(ev)
        period = ev.get("period")
        loc = ev.get("location")
        if not loc or not team or period is None:
            continue

        direction = attack_dirs.get((period, team))
        if direction is None:
            continue

        x, y = loc

        # Keep only throws in the defensive half
        if direction == "right" and x >= 60:
            continue
        if direction == "left" and x <= 60:
            continue

        t0 = parse_ts(ev.get("timestamp", "00:00:00.000"))

        # Scan forward: check if possession_team changes within WINDOW seconds
        retained = True
        for next_ev in events[i + 1:]:
            if next_ev.get("period") != period:
                break
            t1 = parse_ts(next_ev.get("timestamp", "00:00:00.000"))
            if t1 - t0 > WINDOW:
                break
            poss_team = next_ev.get("possession_team", {}).get("name", "")
            if poss_team and poss_team != team:
                retained = False
                break

        nx, ny = normalize(x, y, direction)
        rows.append(
            {
                "team": team,
                "period": period,
                "minute": ev.get("minute"),
                "x": nx,
                "y": ny,
                "retained": retained,
            }
        )

    return rows


# ── Load all matches ──────────────────────────────────────────────────────────
apply_theme()
all_rows: list[dict] = []

for _match_row, events in iter_matches(DATA_DIR):
    all_rows.extend(analyze_events(events))

if not all_rows:
    raise RuntimeError("No defensive-half throw-ins found — check data path.")

df = pd.DataFrame(all_rows)

# ── Summary stats ─────────────────────────────────────────────────────────────
team_stats = (
    df.groupby("team")
    .agg(total=("retained", "count"), retained_n=("retained", "sum"))
    .assign(retention=lambda d: d["retained_n"] / d["total"] * 100)
    .sort_values("retention", ascending=False)
    .reset_index()
)

overall_rate = df["retained"].mean() * 100
barca_row = team_stats[team_stats["team"] == TEAM]
barca_rate = barca_row["retention"].iloc[0] if not barca_row.empty else None

print(f"Overall retention rate: {overall_rate:.1f}%")
print(f"\nRetention rates by team:")
print(team_stats[["team", "total", "retained_n", "retention"]].to_string(index=False))


# ── Figure 1: Retention by pitch zone (distance from own goal) ───────────────
# Throw-ins are on the touchline so x-position is the only meaningful spatial
# dimension. Bin the defensive half into 5-yard zones (x=60..120 normalized,
# where x=120 is own goal and x=60 is midfield).
import numpy as np

bins = np.arange(60, 121, 10)           # 60–70, 70–80, …, 110–120
labels = [f"{int(120-b)}–{int(110-b)}m\nfrom goal" for b in bins[:-1]]
# Friendlier: distance from own goal line (0 = goal, 60 = midfield)
dist_labels = [f"{int(120-b)}–{int(120-(b+10))}" for b in bins[:-1]]

df["zone"] = pd.cut(df["x"], bins=bins, labels=dist_labels, right=False)

zone_stats = (
    df.groupby("zone", observed=True)
    .agg(total=("retained", "count"), retained_n=("retained", "sum"))
    .assign(rate=lambda d: d["retained_n"] / d["total"] * 100)
    .reset_index()
)

barca_zone = (
    df[df["team"] == TEAM].groupby("zone", observed=True)
    .agg(total=("retained", "count"), retained_n=("retained", "sum"))
    .assign(rate=lambda d: d["retained_n"] / d["total"] * 100)
    .reset_index()
)

fig1, ax1 = plt.subplots(figsize=(10, 5))

x_pos = np.arange(len(zone_stats))
width = 0.35

ax1.bar(x_pos - width / 2, zone_stats["rate"], width=width,
        color=AVG_COLOR, alpha=0.8, label="All teams")
ax1.bar(x_pos + width / 2, barca_zone["rate"], width=width,
        color=FOCUS_COLOR, alpha=0.9, label=TEAM)

ax1.axhline(overall_rate, color=NEUTRAL_COLOR, linestyle="--", linewidth=1.2,
            label=f"Overall avg ({overall_rate:.1f}%)")

# Sample size annotations (all teams only)
for i, row in zone_stats.iterrows():
    ax1.text(i - width / 2, row["rate"] + 0.5, f"n={int(row['total'])}",
             ha="center", va="bottom", fontsize=8, color=NEUTRAL_COLOR)

ax1.set_xticks(x_pos)
ax1.set_xticklabels(
    [f"{z}m\nfrom goal" for z in zone_stats["zone"]],
    fontsize=9,
)
ax1.set_ylabel("Retention rate (%)")
ax1.set_ylim(0, 105)
rate_str = f"{barca_rate:.1f}%" if barca_rate is not None else "N/A"
ax1.set_title(
    f"5-Second Retention Rate by Zone — Defensive-Half Throw-Ins\n"
    f"{TEAM}: {rate_str}  |  Overall avg: {overall_rate:.1f}%  "
    f"(left = near midfield, right = near own goal)",
    fontsize=11,
)
ax1.legend()
save_fig(fig1, ASSETS_DIR / "throw_in_retention_by_zone.png")
print(f"\nSaved: {ASSETS_DIR / 'throw_in_retention_by_zone.png'}")


# ── Figure 2: Retention rate bar chart per team ───────────────────────────────
fig2, ax2 = plt.subplots(figsize=(13, 5))

colors = [FOCUS_COLOR if t == TEAM else AVG_COLOR for t in team_stats["team"]]
bars = ax2.bar(team_stats["team"], team_stats["retention"], color=colors, width=0.6)

ax2.axhline(
    overall_rate,
    color=NEUTRAL_COLOR,
    linestyle="--",
    linewidth=1.2,
    label=f"Overall avg ({overall_rate:.1f}%)",
)

for bar, (_, row) in zip(bars, team_stats.iterrows()):
    ax2.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.4,
        f"n={int(row['total'])}",
        ha="center",
        va="bottom",
        fontsize=8,
        color=NEUTRAL_COLOR,
    )

ax2.set_ylabel("Retention rate (%)")
ax2.set_title("Defensive-Half Throw-In Retention Rate (5-Second Window)")
ax2.set_xticklabels(team_stats["team"], rotation=40, ha="right")
ax2.set_ylim(0, min(108, team_stats["retention"].max() + 12))
ax2.legend()
save_fig(fig2, ASSETS_DIR / "throw_in_retention_bars.png")
print(f"Saved: {ASSETS_DIR / 'throw_in_retention_bars.png'}")
