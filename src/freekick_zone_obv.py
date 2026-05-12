"""Free kick delivery zone & OBV impact maps for FC Barcelona takers.

Generates one plot per player (Raphinha, Rashford, Lamine Yamal):
  - Dot/square = delivery end-location (normalised to attacking direction)
  - Shape: square = aerial pass, circle = ground pass / direct shot
  - Color: red = possession ended in shot, grey = no shot
  - Size: proportional to |OBV|
  - Zones: Near post, Far post, Central six-yard, Penalty spot, Edge of box

Run from the project root:
    python src/freekick_zone_obv.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from mplsoccer import VerticalPitch

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "all_data"
_csv_candidates = [ROOT / "matches.csv", ROOT / "data" / "matches.csv"]
MATCHES_CSV = next((p for p in _csv_candidates if p.exists()), _csv_candidates[0])
OUT_DIR = ROOT / "assets" / "offensive_freekicks"

# ── Config ───────────────────────────────────────────────────────────────────
TEAM           = "Barcelona"
TARGET_PLAYERS = ["Raphael Dias", "Rashford", "Lamine Yamal"]
PLAYER_LABELS  = {"Raphael Dias": "Raphinha", "Rashford": "Rashford", "Lamine Yamal": "Lamine Yamal"}

# ── Colors (project palette) ─────────────────────────────────────────────────
SHOT_COLOR    = "#d73027"   # red — possession led to shot
NO_SHOT_COLOR = "#878787"   # grey — no shot
TEXT_COLOR    = "#222222"

# ── Delivery zones (StatsBomb coords, attack toward x=120) ───────────────────
ZONES = {
    "Near Post":      {"x": (114, 120), "y": (18, 33), "label_pos": (25, 85)},
    "Far Post":       {"x": (114, 120), "y": (47, 62), "label_pos": (55, 85)},
    "Central 6-yard": {"x": (114, 120), "y": (33, 47), "label_pos": (40, 92)},
    "Penalty Spot":   {"x": (102, 114), "y": (28, 52), "label_pos": (40, 85)},
    "Edge of Box":    {"x": (96,  102), "y": (18, 62), "label_pos": (40, 78)},
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_events(match_id: str) -> list[dict] | None:
    path = DATA_DIR / f"{match_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_fk_pass(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == 30
        and ev.get("pass", {}).get("type", {}).get("name") == "Free Kick"
    )


def _is_fk_shot(ev: dict) -> bool:
    return (
        ev.get("type", {}).get("id") == 16
        and ev.get("shot", {}).get("type", {}).get("name") == "Free Kick"
    )


def _obv(ev: dict) -> float:
    try:
        return float(ev.get("obv_for_net") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize(x: float, y: float, start_x: float) -> tuple[float, float]:
    """Flip coordinates so attack always goes toward x=120."""
    if start_x < 60:   # attacking left → flip
        return 120 - x, 80 - y
    return x, y


def _collect(player_substr: str) -> tuple[str, pd.DataFrame]:
    """Return (full_name, dataframe) of FK events for the player."""
    rows: list[dict] = []
    full_name = player_substr
    matches_df = pd.read_csv(MATCHES_CSV)

    for _, match_row in matches_df.iterrows():
        match_id = str(match_row.get("statsbomb", "")).strip()
        if not match_id:
            continue
        events = _load_events(match_id)
        if events is None:
            continue

        df = pd.json_normalize(events, sep=".")

        # Possessions with a shot (non-penalty)
        xg_by_possession: dict[int, float] = {}
        if "type.name" in df.columns and "possession" in df.columns:
            shots = df[
                (df["type.name"] == "Shot") &
                (df.get("shot.type.name", pd.Series(dtype=str)) != "Penalty")
            ]
            for poss, grp in shots.groupby("possession"):
                xg_by_possession[int(poss)] = float(
                    grp["shot.statsbomb_xg"].fillna(0).sum()
                )
        shot_possessions = set(xg_by_possession.keys())

        for ev in events:
            is_pass = _is_fk_pass(ev)
            is_shot = _is_fk_shot(ev)
            if not (is_pass or is_shot):
                continue

            player_name = ev.get("player", {}).get("name", "")
            team_name   = ev.get("team",   {}).get("name", "")
            if player_substr.lower() not in player_name.lower() or team_name != TEAM:
                continue

            full_name = player_name
            start_loc = ev.get("location") or []
            if len(start_loc) < 2:
                continue
            start_x, start_y = start_loc[0], start_loc[1]

            if is_pass:
                end_loc = ev.get("pass", {}).get("end_location") or []
                height  = ev.get("pass", {}).get("height", {}).get("name", "")
                is_aerial = 1 if "High" in str(height) else 0
            else:  # direct shot
                end_loc = ev.get("location") or []  # shot from FK spot
                is_aerial = 0

            if len(end_loc) < 2:
                continue
            end_x, end_y = end_loc[0], end_loc[1]
            t_x, t_y = _normalize(end_x, end_y, start_x)

            poss = ev.get("possession")
            ended_in_shot = int(poss) in shot_possessions if poss is not None else False
            poss_xg = xg_by_possession.get(int(poss), 0.0) if poss is not None else 0.0

            rows.append({
                "t_x": t_x,
                "t_y": t_y,
                "is_aerial": is_aerial,
                "obv": _obv(ev),
                "ended_in_shot": ended_in_shot,
                "possession_xg": poss_xg,
                "is_shot": int(is_shot),
            })

    return full_name, pd.DataFrame(rows)


def _plot(player_substr: str) -> None:
    print(f"Processing {player_substr}...")
    full_name, df = _collect(player_substr)

    if df.empty:
        print(f"  No FK data found for {player_substr!r}")
        return

    print(f"  {full_name}: {len(df)} FKs")

    total_xg = df["possession_xg"].sum()
    avg_xg   = df["possession_xg"].mean()

    pitch = VerticalPitch(
        pitch_type="statsbomb",
        line_color="#777777",
        half=True,
        goal_type="box",
        pitch_color="white",
    )
    fig, ax = pitch.draw(figsize=(10, 13))
    fig.patch.set_facecolor("white")

    # Scatter: shape = aerial vs ground/shot, color = shot outcome
    for is_aerial, marker in [(1, "s"), (0, "o")]:
        sub = df[df["is_aerial"] == is_aerial]
        if sub.empty:
            continue
        dot_colors = sub["ended_in_shot"].map({True: SHOT_COLOR, False: NO_SHOT_COLOR})
        dot_sizes  = (sub["obv"].abs() * 5000) + 25
        ax.scatter(
            sub["t_y"], sub["t_x"],
            s=dot_sizes, c=dot_colors, marker=marker,
            alpha=0.82, edgecolors="white", linewidth=0.6, zorder=4,
        )

    # Zone rectangles + labels
    for zone_name, bounds in ZONES.items():
        in_zone = df[
            (df["t_x"] >= bounds["x"][0]) & (df["t_x"] <= bounds["x"][1]) &
            (df["t_y"] >= bounds["y"][0]) & (df["t_y"] <= bounds["y"][1])
        ]
        rect = plt.Rectangle(
            (bounds["y"][0], bounds["x"][0]),
            bounds["y"][1] - bounds["y"][0],
            bounds["x"][1] - bounds["x"][0],
            facecolor="#f0f0f0", alpha=0.15,
            edgecolor="#444444", lw=0.8, linestyle="--", zorder=1,
        )
        ax.add_patch(rect)

        if not in_zone.empty:
            label = (
                f"{zone_name}\n"
                f"{len(in_zone)} deliveries\n"
                f"Avg OBV: {in_zone['obv'].mean():.4f}"
            )
            lbl_y, lbl_x = bounds["label_pos"]
            ax.text(
                lbl_y, lbl_x, label,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color=TEXT_COLOR, zorder=5,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="#cccccc",
                          boxstyle="round,pad=0.4"),
            )

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=10, label="Aerial pass"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=10, label="Ground pass / direct shot"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=SHOT_COLOR,
               markersize=10, label="Possession -> shot"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=5,  label="Small OBV"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=15, label="Large OBV"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper center", bbox_to_anchor=(0.5, -0.05),
        ncol=3, frameon=False, fontsize=9,
    )

    label = PLAYER_LABELS.get(player_substr, full_name)
    ax.set_title(
        f"{full_name}\nFree Kick Delivery Zone & OBV Impact\n"
        f"Total xG from FKs: {total_xg:.2f}   |   Avg xG per FK: {avg_xg:.3f}",
        fontsize=13, fontweight="bold", pad=20, color=TEXT_COLOR,
    )

    slug = player_substr.lower().replace(" ", "_")
    out = OUT_DIR / f"freekick_zone_obv_{slug}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved to {out}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for player in TARGET_PLAYERS:
        _plot(player)
