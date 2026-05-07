"""
throw_in_side_change.py

After a throw-in in the own (defensive) half, how often does the team
switch the side of the pitch within 6 seconds while keeping possession?

Side is determined by y-coordinate: y < 40 = left touchline side,
y >= 40 = right touchline side.

For each throw-in we scan the next 6 seconds:
  - If possession_team changes to the opponent → turnover, stop.
  - Otherwise track locations until the window closes.
  - Side changed = possession kept AND final location is on the opposite
    side from the throw-in.

Coordinates are normalised so the own goal is always at x=120 (right),
matching a half=True mplsoccer view of the defensive half.

Usage:
    python src/throw_in_side_change.py
"""

import sys
import io
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from mplsoccer import Pitch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.stats import filters as f
from src.stats.data import iter_matches
from src.stats.viz.style import (
    AVG_COLOR,
    FOCUS_COLOR,
    NEGATIVE_COLOR,
    NEUTRAL_COLOR,
    POSITIVE_COLOR,
    apply_theme,
    save_fig,
)

# ── Config ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "statsbomb"
ASSETS_DIR = ROOT / "assets"
TEAM = "Barcelona"
WINDOW = 6.0
PITCH_MID_Y = 40.0

# Trajectory plot colours
COLOR_SWITCHED = "#00c853"       # bright green
COLOR_SAME = "#1e88e5"           # bright blue
COLOR_LOST = "#ff5252"           # bright red


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_ts(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def build_attack_dirs(events: list[dict]) -> dict[tuple, str]:
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


def norm(x: float, y: float, attack_dir: str) -> tuple[float, float]:
    """Normalise so own goal is at x=120 while keeping left/right side in y."""
    if attack_dir == "right":
        return 120 - x, y
    return x, y


def side_of(y: float) -> str:
    return "left" if y < PITCH_MID_Y else "right"


def event_ball_location(ev: dict) -> tuple[float, float] | None:
    """Return the most useful on-pitch ball location for path plotting."""
    end = ev.get("pass", {}).get("end_location")
    if end:
        return end[0], end[1]

    end = ev.get("carry", {}).get("end_location")
    if end:
        return end[0], end[1]

    loc = ev.get("location")
    if loc:
        return loc[0], loc[1]

    return None


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

        # Own half only
        if direction == "right" and x >= 60:
            continue
        if direction == "left" and x <= 60:
            continue

        throw_side = side_of(y)
        t0 = parse_ts(ev.get("timestamp", "00:00:00.000"))
        nx0, ny0 = norm(x, y, direction)

        # Scan forward: stop on turnover, collect the on-ball path while in possession
        trajectory: list[tuple[float, float]] = [(nx0, ny0)]
        last_y: float | None = None
        lost_possession = False

        for next_ev in events[i + 1:]:
            if next_ev.get("period") != period:
                break
            t1 = parse_ts(next_ev.get("timestamp", "00:00:00.000"))
            if t1 - t0 > WINDOW:
                break
            poss_team = next_ev.get("possession_team", {}).get("name", "")
            if poss_team and poss_team != team:
                lost_possession = True
                break
            if f.event_team(next_ev) != team:
                continue
            next_loc = event_ball_location(next_ev)
            if next_loc:
                nx1, ny1 = norm(next_loc[0], next_loc[1], direction)
                if (nx1, ny1) != trajectory[-1]:
                    trajectory.append((nx1, ny1))
                last_y = next_loc[1]  # raw y for side comparison

        if lost_possession:
            outcome = "lost"
        elif last_y is None:
            continue  # no located event in window; skip
        elif side_of(last_y) != throw_side:
            outcome = "switched"
        else:
            outcome = "same"

        dist_from_goal = x if direction == "left" else 120 - x

        rows.append({
            "team": team,
            "throw_side": throw_side,
            "dist_from_goal": dist_from_goal,
            "outcome": outcome,
            "side_changed": outcome == "switched",
            "trajectory": trajectory,
        })

    return rows


# ── Load all matches ──────────────────────────────────────────────────────────
apply_theme()
all_rows: list[dict] = []

for _match_row, events in iter_matches(DATA_DIR):
    all_rows.extend(analyze_events(events))

if not all_rows:
    raise RuntimeError("No own-half throw-ins found — check data path.")

df = pd.DataFrame(all_rows)

# ── Summary stats ─────────────────────────────────────────────────────────────
total = len(df)
kept = df[df["outcome"] != "lost"].copy()
n_kept = len(kept)
n_switched = (kept["outcome"] == "switched").sum()
n_same = (kept["outcome"] == "same").sum()
n_lost = total - n_kept
overall_switch_rate = n_switched / n_kept * 100 if n_kept else 0
overall_retention = n_kept / total * 100 if total else 0

team_stats = (
    kept
    .groupby("team")
    .agg(total=("side_changed", "count"), switched_n=("side_changed", "sum"))
    .assign(rate=lambda d: d["switched_n"] / d["total"] * 100)
    .sort_values("rate", ascending=False)
    .reset_index()
)

barca_row = team_stats[team_stats["team"] == TEAM]
barca_rate = barca_row["rate"].iloc[0] if not barca_row.empty else None

print(f"Own-half throw-ins: {total}")
print(f"  Lost possession:        {n_lost} ({n_lost/total*100:.1f}%)")
print(f"  Kept possession:        {n_kept} ({overall_retention:.1f}%)")
print(f"    → Side switched:      {n_switched} ({overall_switch_rate:.1f}% of kept)")
print(f"    → Same side:          {n_same}")
if barca_rate is not None:
    barca_kept = barca_row["total"].iloc[0]
    print(f"\n{TEAM}: {barca_rate:.1f}% side-switch rate ({int(barca_kept)} kept-possession throws)")

side_stats = (
    kept
    .groupby("throw_side")
    .agg(total=("side_changed", "count"), switched_n=("side_changed", "sum"))
    .assign(rate=lambda d: d["switched_n"] / d["total"] * 100)
    .reset_index()
)
print(f"\nSide-switch rate by throw-in side (possession kept only):")
print(side_stats.to_string(index=False))

print(f"\nSide-switch rates by team (possession kept only):")
print(team_stats[["team", "total", "switched_n", "rate"]].to_string(index=False))


# ── Figure 1: Side-switch rate by zone (possession-kept throws only) ──────────
bins = np.arange(0, 61, 10)
dist_labels = [f"{b}–{b + 10}" for b in bins[:-1]]

kept_df = kept.copy()
kept_df["zone"] = pd.cut(kept_df["dist_from_goal"], bins=bins,
                         labels=dist_labels, right=False)

zone_stats = (
    kept_df.groupby("zone", observed=True)
    .agg(total=("side_changed", "count"), switched_n=("side_changed", "sum"))
    .assign(rate=lambda d: d["switched_n"] / d["total"] * 100)
    .reset_index()
)

barca_zone = (
    kept_df[kept_df["team"] == TEAM].groupby("zone", observed=True)
    .agg(total=("side_changed", "count"), switched_n=("side_changed", "sum"))
    .assign(rate=lambda d: d["switched_n"] / d["total"] * 100)
    .reset_index()
)

fig1, ax1 = plt.subplots(figsize=(10, 5))
x_pos = np.arange(len(zone_stats))
width = 0.35

ax1.bar(x_pos - width / 2, zone_stats["rate"], width=width,
        color=AVG_COLOR, alpha=0.8, label="All teams")
ax1.bar(x_pos + width / 2, barca_zone["rate"], width=width,
        color=FOCUS_COLOR, alpha=0.9, label=TEAM)
ax1.axhline(overall_switch_rate, color=NEUTRAL_COLOR, linestyle="--", linewidth=1.2,
            label=f"Overall avg ({overall_switch_rate:.1f}%)")

for idx, row in zone_stats.iterrows():
    ax1.text(idx - width / 2, row["rate"] + 0.5, f"n={int(row['total'])}",
             ha="center", va="bottom", fontsize=8, color=NEUTRAL_COLOR)

ax1.set_xticks(x_pos)
ax1.set_xticklabels([f"{z}m\nfrom goal" for z in zone_stats["zone"]], fontsize=9)
ax1.set_ylabel("Side-switch rate (%)")
ax1.set_ylim(0, 105)
rate_str = f"{barca_rate:.1f}%" if barca_rate is not None else "N/A"
ax1.set_title(
    f"Side-Switch Rate by Zone — Own-Half Throw-Ins, Possession Kept (6s window)\n"
    f"{TEAM}: {rate_str}  |  Overall avg: {overall_switch_rate:.1f}%  "
    f"(left = near goal, right = near midfield)",
    fontsize=11,
)
ax1.legend()
save_fig(fig1, ASSETS_DIR / "throw_in_side_change_by_zone.png")
print(f"\nSaved: {ASSETS_DIR / 'throw_in_side_change_by_zone.png'}")


# ── Figure 2: Side-switch rate per team ───────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(13, 5))
colors = [FOCUS_COLOR if t == TEAM else AVG_COLOR for t in team_stats["team"]]
bars = ax2.bar(team_stats["team"], team_stats["rate"], color=colors, width=0.6)

ax2.axhline(overall_switch_rate, color=NEUTRAL_COLOR, linestyle="--", linewidth=1.2,
            label=f"Overall avg ({overall_switch_rate:.1f}%)")

for bar, (_, row) in zip(bars, team_stats.iterrows()):
    ax2.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.4,
        f"n={int(row['total'])}",
        ha="center", va="bottom", fontsize=8, color=NEUTRAL_COLOR,
    )

ax2.set_ylabel("Side-switch rate (%)")
ax2.set_title("Own-Half Throw-In Side-Switch Rate, Possession Kept (6-Second Window)")
ax2.set_xticklabels(team_stats["team"], rotation=40, ha="right")
ax2.set_ylim(0, min(108, team_stats["rate"].max() + 12))
ax2.legend()
save_fig(fig2, ASSETS_DIR / "throw_in_side_change_bars.png")
print(f"Saved: {ASSETS_DIR / 'throw_in_side_change_bars.png'}")


# ── Figure 3: Trajectory pitch map (all teams, normalised to own goal) ────────
# Coordinates are normalised on the full StatsBomb pitch so the own goal is
# always at x=120. Using a half pitch clips any sequence that crosses midfield
# at x=60, which makes many trajectories appear to funnel through the pitch
# centre even when the underlying path does not.

trajectory_pitch = Pitch(
    pitch_type="statsbomb",
    pitch_color="white",
    line_color="#c7d5cc",
)
fig3, ax3 = trajectory_pitch.draw(figsize=(12, 8))

alpha = max(0.04, min(0.3, 30 / len(df)))  # scale with density

for _, row in df.iterrows():
    traj = row["trajectory"]
    if len(traj) < 2:
        continue
    outcome = row["outcome"]
    color = COLOR_SWITCHED if outcome == "switched" else (
        COLOR_SAME if outcome == "same" else COLOR_LOST
    )
    xs = [p[0] for p in traj]
    ys = [p[1] for p in traj]
    ax3.plot(xs, ys, color=color, alpha=alpha, linewidth=0.8, zorder=2)
    # mark the throw-in start with a small dot
    ax3.scatter(xs[0], ys[0], color=color, s=6, alpha=min(alpha * 3, 0.6),
                zorder=3, linewidths=0)

legend_patches = [
    mpatches.Patch(color=COLOR_SWITCHED, label=f"Kept poss + switched side  (n={n_switched})"),
    mpatches.Patch(color=COLOR_SAME,     label=f"Kept poss + same side      (n={n_same})"),
    mpatches.Patch(color=COLOR_LOST,     label=f"Lost possession             (n={n_lost})"),
]
ax3.legend(handles=legend_patches, loc="upper left", fontsize=9)
rate_str = f"{barca_rate:.1f}%" if barca_rate is not None else "N/A"
ax3.set_title(
    f"Own-Half Throw-In Trajectories (6-Second Window) — All Teams\n"
    f"Side-switch rate (poss kept): {overall_switch_rate:.1f}%  |  {TEAM}: {rate_str}",
    fontsize=12,
)
save_fig(fig3, ASSETS_DIR / "throw_in_side_change_trajectories.png")
print(f"Saved: {ASSETS_DIR / 'throw_in_side_change_trajectories.png'}")


# ── Figure 4: Trajectory map for Barcelona only ───────────────────────────────
barca_df = df[df["team"] == TEAM]
n_barca = len(barca_df)

if n_barca > 0:
    n_b_switched = (barca_df["outcome"] == "switched").sum()
    n_b_same = (barca_df["outcome"] == "same").sum()
    n_b_lost = (barca_df["outcome"] == "lost").sum()

    fig4, ax4 = trajectory_pitch.draw(figsize=(12, 8))
    alpha_b = max(0.08, min(0.5, 50 / n_barca))

    for _, row in barca_df.iterrows():
        traj = row["trajectory"]
        if len(traj) < 2:
            continue
        outcome = row["outcome"]
        color = COLOR_SWITCHED if outcome == "switched" else (
            COLOR_SAME if outcome == "same" else COLOR_LOST
        )
        xs = [p[0] for p in traj]
        ys = [p[1] for p in traj]
        ax4.plot(xs, ys, color=color, alpha=alpha_b, linewidth=1.0, zorder=2)
        ax4.scatter(xs[0], ys[0], color=color, s=8, alpha=min(alpha_b * 3, 0.8),
                    zorder=3, linewidths=0)

    legend_patches_b = [
        mpatches.Patch(color=COLOR_SWITCHED, label=f"Kept poss + switched side  (n={n_b_switched})"),
        mpatches.Patch(color=COLOR_SAME,     label=f"Kept poss + same side      (n={n_b_same})"),
        mpatches.Patch(color=COLOR_LOST,     label=f"Lost possession             (n={n_b_lost})"),
    ]
    ax4.legend(handles=legend_patches_b, loc="upper left", fontsize=9)
    ax4.set_title(
        f"{TEAM} — Own-Half Throw-In Trajectories (6-Second Window)\n"
        f"Side-switch rate (poss kept): {barca_rate:.1f}%",
        fontsize=12,
    )
    save_fig(fig4, ASSETS_DIR / "throw_in_side_change_trajectories_barca.png")
    print(f"Saved: {ASSETS_DIR / 'throw_in_side_change_trajectories_barca.png'}")
