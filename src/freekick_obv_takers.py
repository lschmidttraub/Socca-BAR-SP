"""Free kick OBV comparison for FC Barcelona.

Compares OBV-for-net per free kick (passes + direct shots) for individual
takers (Rashford, Pedro, Lamine Yamal, Raphina) against the
tournament-wide average across all free kick takers.

Run from the project root:
    python src/freekick_obv_takers.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "all_data"
_csv_candidates = [ROOT / "matches.csv", ROOT / "data" / "matches.csv"]
MATCHES_CSV = next((p for p in _csv_candidates if p.exists()), _csv_candidates[0])
OUT = ROOT / "assets" / "offensive_freekicks" / "freekick_obv_takers.png"

# ── Config ───────────────────────────────────────────────────────────────────
TEAM           = "Barcelona"
TARGET_PLAYERS = ["Rashford", "Pedro", "Lamine Yamal", "Raphael Dias"]  # substring match

# ── Colors (project palette) ─────────────────────────────────────────────────
FOCUS_COLOR   = "#4575b4"
AVG_COLOR     = "#d73027"
NEUTRAL_COLOR = "#878787"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_events(match_id: str) -> list[dict] | None:
    path = DATA_DIR / f"{match_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_freekick(ev: dict) -> bool:
    """Free kick pass or direct free kick shot."""
    return (
        ev.get("type", {}).get("id") == 30
        and ev.get("pass", {}).get("type", {}).get("name") == "Free Kick"
    ) or (
        ev.get("type", {}).get("id") == 16
        and ev.get("shot", {}).get("type", {}).get("name") == "Free Kick"
    )


def _obv(ev: dict) -> float | None:
    val = ev.get("obv_for_net")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ── Data collection ──────────────────────────────────────────────────────────

matches_df = pd.read_csv(MATCHES_CSV)

player_obv:        dict[str, list[float]] = {t: [] for t in TARGET_PLAYERS}
player_full_names: dict[str, str]         = {t: t  for t in TARGET_PLAYERS}
all_takers_obv:    list[float]            = []

for _, row in matches_df.iterrows():
    match_id = str(row.get("statsbomb", "")).strip()
    if not match_id:
        continue
    events = _load_events(match_id)
    if events is None:
        continue

    for ev in events:
        if not _is_freekick(ev):
            continue
        v = _obv(ev)
        if v is None:
            continue

        player_name = ev.get("player", {}).get("name", "")
        team_name   = ev.get("team",   {}).get("name", "")

        all_takers_obv.append(v)

        for target in TARGET_PLAYERS:
            if target.lower() in player_name.lower() and team_name == TEAM:
                player_obv[target].append(v)
                player_full_names[target] = player_name

# ── Print summary ─────────────────────────────────────────────────────────────

print(f"Matches loaded : {len(matches_df)}")
for target in TARGET_PLAYERS:
    vals = player_obv[target]
    if vals:
        print(f"  {player_full_names[target]}: {len(vals)} FKs, mean OBV = {np.mean(vals):.4f}")
    else:
        print(f"  {target}: no data found")
print(f"  All takers   : {len(all_takers_obv)} FKs, mean OBV = {np.mean(all_takers_obv):.4f}")

# ── Plot ──────────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(12, 7))

plot_data:   list[list[float]] = []
labels:      list[str]         = []
colors_list: list[str]         = []

blues = cm.Blues(np.linspace(0.40, 0.80, len(TARGET_PLAYERS)))
for i, target in enumerate(TARGET_PLAYERS):
    vals      = player_obv[target]
    full_name = player_full_names[target]
    plot_data.append(vals)
    labels.append(f"{full_name}\n({len(vals)} FKs)")
    colors_list.append(mcolors.to_hex(blues[i]))

plot_data.append(all_takers_obv)
labels.append(f"All takers (tournament)\n({len(all_takers_obv)} FKs)")
colors_list.append(AVG_COLOR)

box = ax.boxplot(
    plot_data,
    tick_labels=labels,
    patch_artist=True,
    notch=False,
    showmeans=True,
    medianprops={"color": "black", "linewidth": 2},
    meanprops={
        "marker": "D",
        "markerfacecolor": "white",
        "markeredgecolor": "black",
        "markersize": 6,
    },
    flierprops={
        "marker": "o",
        "markerfacecolor": NEUTRAL_COLOR,
        "alpha": 0.35,
        "markersize": 4,
        "linestyle": "none",
    },
    whiskerprops={"linewidth": 1.2},
    capprops={"linewidth": 1.2},
)

for patch, color in zip(box["boxes"], colors_list):
    patch.set_facecolor(color)
    patch.set_alpha(0.82)

ax.axhline(0, color=NEUTRAL_COLOR, linestyle="--", linewidth=1.0,
           alpha=0.6, label="Zero baseline")
ax.set_ylim(top=0.2)
ax.set_title(f"{TEAM} — Free Kick OBV by Taker",
             fontsize=15, fontweight="bold", pad=14)
ax.set_ylabel("OBV for Net Change", fontsize=12)
ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)
ax.set_axisbelow(True)
ax.legend(fontsize=9, loc="upper right")

fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSaved to {OUT}")
