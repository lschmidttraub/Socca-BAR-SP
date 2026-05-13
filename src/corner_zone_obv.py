"""Corner delivery zone & OBV impact maps for FC Barcelona takers.

Generates one plot per player (Raphael Dias, Rashford, Lamine Yamal):
  - Dot/square = delivery end-location (normalised to one side)
  - Shape: square = aerial, circle = ground
  - Color: red = possession ended in shot, grey = no shot
  - Size: proportional to |OBV|

Run from the project root:
    python src/corner_zone_obv.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from mplsoccer import Pitch

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
_SB_ROOT  = ROOT / "data" / "statsbomb"
DATA_DIRS = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
_csv_candidates = [ROOT / "data" / "matches.csv", ROOT / "matches.csv"]
MATCHES_CSV = next((p for p in _csv_candidates if p.exists()), _csv_candidates[0])
OUT_DIR = ROOT / "assets" / "corner_analysis"

# ── Config ───────────────────────────────────────────────────────────────────
TEAM = "Barcelona"
TARGET_PLAYERS = ["Raphael Dias", "Rashford", "Lamine Yamal"]  # substring match

# ── Colors (project palette) ─────────────────────────────────────────────────
AERIAL_COLOR  = "#4575b4"   # Barcelona blue — aerial pass
GROUND_COLOR  = "#4575b4"   # same blue for ground (shape distinguishes)
SHOT_COLOR    = "#d73027"   # red — possession led to shot
NO_SHOT_COLOR = "#878787"   # grey — no shot
TEXT_COLOR    = "#222222"

# ── Delivery zones ───────────────────────────────────────────────────────────
ZONES = {
    "Near Post":    {"x": (96, 120), "y": (18, 30)},
    "Far Post":     {"x": (96, 120), "y": (50, 62)},
    "Short Corner": {"x": (96, 120), "y": (0,  18)},
    "Central Zone": {"x": (96, 120), "y": (30, 50)},
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_events(match_id: str) -> list[dict] | None:
    for data_dir in DATA_DIRS:
        path = data_dir / f"{match_id}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return None


def _collect(player_substr: str) -> tuple[str, pd.DataFrame]:
    """Return (full_name, dataframe) for all corners taken by the player.

    Each row includes ``ended_in_shot`` and ``possession_xg`` (total xG
    from non-penalty shots in the same possession).
    """
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
        if "pass.type.name" not in df.columns:
            continue

        # Build possession → total xG mapping (non-penalty shots only)
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

        corners = df[df["pass.type.name"] == "Corner"].copy()
        if corners.empty:
            continue

        name_mask = corners.get("player.name", pd.Series(dtype=str)).str.contains(
            player_substr, case=False, na=False
        )
        team_mask = corners.get("team.name", pd.Series(dtype=str)) == TEAM
        corners = corners[name_mask & team_mask]
        if corners.empty:
            continue

        full_name = corners["player.name"].iloc[0]
        corners = corners.copy()
        corners["ended_in_shot"] = corners["possession"].isin(shot_possessions)
        corners["possession_xg"] = corners["possession"].map(
            lambda p: xg_by_possession.get(int(p), 0.0)
        )
        rows.append(corners)

    if not rows:
        return full_name, pd.DataFrame()

    df_all = pd.concat(rows, ignore_index=True)
    return full_name, df_all


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize all corners so the attack goes left to right (toward x=120)."""
    records = []
    for _, row in df.iterrows():
        loc = row.get("location")
        end = row.get("pass.end_location")
        if not isinstance(loc, list) or not isinstance(end, list):
            continue
        start_y = loc[1]
        end_x, end_y = end[0], end[1]
        # Flip so all corners come from the bottom-right corner
        t_y = 80 - end_y if start_y > 40 else end_y
        t_x = end_x
        is_aerial = 1 if "High" in str(row.get("pass.height.name", "")) else 0
        obv = float(row.get("obv_for_net", 0) or 0)
        records.append({
            "t_x": t_x,
            "t_y": t_y,
            "is_aerial": is_aerial,
            "obv": obv,
            "ended_in_shot": bool(row.get("ended_in_shot", False)),
            "possession_xg": float(row.get("possession_xg", 0.0) or 0.0),
        })
    return pd.DataFrame(records)


def _plot(player_substr: str) -> None:
    print(f"Processing {player_substr}...")
    full_name, df_raw = _collect(player_substr)

    if df_raw.empty:
        print(f"  No corners found for {player_substr!r}")
        return

    df = _normalize(df_raw)
    print(f"  {full_name}: {len(df)} corners")

    pitch = Pitch(
        pitch_type="statsbomb",
        line_color="#777777",
        half=True,
        goal_type="box",
        pitch_color="white",
    )
    fig, ax = pitch.draw(figsize=(13, 10))
    fig.patch.set_facecolor("white")

    # Scatter: shape = aerial vs ground, color = shot outcome
    for is_aerial, marker in [(1, "s"), (0, "o")]:
        sub = df[df["is_aerial"] == is_aerial]
        if sub.empty:
            continue
        dot_colors = sub["ended_in_shot"].map({True: SHOT_COLOR, False: NO_SHOT_COLOR})
        dot_sizes  = (sub["obv"].abs() * 5000) + 25
        ax.scatter(
            sub["t_x"], sub["t_y"],
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
            (bounds["x"][0], bounds["y"][0]),
            bounds["x"][1] - bounds["x"][0],
            bounds["y"][1] - bounds["y"][0],
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
            # Labels in the open midfield area to the left of the zones
            ax.text(
                75,
                (bounds["y"][0] + bounds["y"][1]) / 2,
                label,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color=TEXT_COLOR, zorder=5,
                bbox=dict(facecolor="white", alpha=0.85, edgecolor="#cccccc",
                          boxstyle="round,pad=0.4"),
            )

    # Corner origin star
    ax.scatter(120, 0, color="gold", s=300, marker="*", zorder=6, edgecolor="black")

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=10, label="Aerial pass"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=10, label="Ground pass"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=SHOT_COLOR,
               markersize=10, label="Possession → shot"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=5,  label="Small OBV"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=NO_SHOT_COLOR,
               markersize=15, label="Large OBV"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="gold",
               markersize=15, markeredgecolor="black", label="Corner origin"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper center", bbox_to_anchor=(0.5, -0.05),
        ncol=3, frameon=False, fontsize=9,
    )

    total_xg = df["possession_xg"].sum()
    avg_xg   = df["possession_xg"].mean()
    ax.set_title(
        f"{full_name}\nCorner Delivery Zone & OBV Impact\n"
        f"Total xG from corners: {total_xg:.2f}   |   Avg xG per corner: {avg_xg:.3f}",
        fontsize=13, fontweight="bold", pad=20, color=TEXT_COLOR,
    )

    slug = player_substr.lower().replace(" ", "_")
    out = OUT_DIR / f"corner_zone_obv_{slug}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved to {out}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for player in TARGET_PLAYERS:
        _plot(player)
