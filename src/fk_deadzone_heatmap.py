"""Dead-zone free-kick arrow maps for FC Barcelona players.

One PNG per player. Each arrow represents one FK pass:
  - Arrow goes from origin to delivery endpoint
  - Colour   = OBV (red = negative, yellow = neutral, green = positive)
  - Thickness = scales with |OBV| so impactful passes stand out

Run from the project root:
    python src/fk_deadzone_heatmap.py
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from mplsoccer import Pitch

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "all_data"
_csv_candidates = [ROOT / "matches.csv", ROOT / "data" / "matches.csv"]
MATCHES_CSV = next((p for p in _csv_candidates if p.exists()), _csv_candidates[0])
OUT_DIR = ROOT / "assets" / "offensive_freekicks"

# ── Config ───────────────────────────────────────────────────────────────────
TEAM           = "Barcelona"
TARGET_PLAYERS = [
    "de Jong",
    "Pedro Gonzalez",
    "Joan Garcia",
    "Gerard Martin",
    "Araujo",
    "Eric Garcia",
]

# ── Colors ───────────────────────────────────────────────────────────────────
OBV_CMAP   = "RdYlGn"
PITCH_LINE = "#888888"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Strip accents and lowercase for accent-insensitive matching."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


def _load_events(match_id: str) -> list[dict] | None:
    path = DATA_DIR / f"{match_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _obv(ev: dict) -> float:
    try:
        return float(ev.get("obv_for_net") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _collect(player_substr: str) -> tuple[str, pd.DataFrame]:
    """Return (full_name, df) with FK start/end locations and OBV."""
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

        for ev in events:
            if not (
                ev.get("type", {}).get("id") == 30
                and ev.get("pass", {}).get("type", {}).get("name") == "Free Kick"
            ):
                continue

            player_name = ev.get("player", {}).get("name", "")
            team_name   = ev.get("team",   {}).get("name", "")
            if _normalize(player_substr) not in _normalize(player_name) or team_name != TEAM:
                continue

            full_name = player_name
            start = ev.get("location") or []
            end   = ev.get("pass", {}).get("end_location") or []
            if len(start) < 2 or len(end) < 2:
                continue

            rows.append({
                "start_x": start[0],
                "start_y": start[1],
                "end_x":   end[0],
                "end_y":   end[1],
                "obv":     _obv(ev),
            })

    return full_name, pd.DataFrame(rows)


# ── Plotting ──────────────────────────────────────────────────────────────────

def _plot_player(player_substr: str) -> None:
    print(f"Processing {player_substr}...")
    full_name, df = _collect(player_substr)

    if df.empty:
        print(f"  No FK data found for {player_substr!r}")
        return

    print(f"  Found {len(df)} FK passes")

    obv_vals  = df["obv"].values
    OBV_LIMIT = 0.02
    norm      = TwoSlopeNorm(vmin=-OBV_LIMIT, vcenter=0.0, vmax=OBV_LIMIT)
    cmap      = plt.colormaps[OBV_CMAP]
    obv_clipped = np.clip(obv_vals, -OBV_LIMIT, OBV_LIMIT)

    # Arrow width: base + extra for high-impact passes (use actual OBV for thickness)
    base_w    = 1.5
    max_extra = 3.0
    abs_max   = max(float(np.abs(obv_vals).max()), 1e-6)
    widths    = base_w + max_extra * (np.abs(obv_vals) / abs_max)

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="#f8f8f8",
        line_color=PITCH_LINE,
        linewidth=1.2,
    )

    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("white")
    pitch.draw(ax=ax)

    # Draw one arrow per FK pass
    for i, row in df.iterrows():
        color = cmap(norm(obv_clipped[df.index.get_loc(i)]))
        w     = widths[df.index.get_loc(i)]
        pitch.arrows(
            row["start_x"], row["start_y"],
            row["end_x"],   row["end_y"],
            ax=ax,
            color=color,
            width=w,
            headwidth=w * 2.5,
            headlength=w * 2.0,
            alpha=0.82,
            zorder=4,
        )

    # ── Colorbar ─────────────────────────────────────────────────────────────
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.02, label="OBV (net change)")
    cbar.ax.axhline(0, color="black", linewidth=0.9, linestyle="--")
    cbar.set_ticks([-OBV_LIMIT, -0.01, 0, 0.01, OBV_LIMIT])
    cbar.set_ticklabels([f"<= {-OBV_LIMIT:.2f}", "-0.01", "0", "+0.01", f">= +{OBV_LIMIT:.2f}"])

    # ── Legend (width guide) ──────────────────────────────────────────────────
    legend_handles = [
        Line2D([0], [0], color="#555555", linewidth=base_w,            label="Low |OBV|"),
        Line2D([0], [0], color="#555555", linewidth=base_w + max_extra, label="High |OBV|"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=9,
              title="Arrow thickness", title_fontsize=8, framealpha=0.7)

    # ── Labels ───────────────────────────────────────────────────────────────
    n      = len(df)
    mean_o = obv_vals.mean()
    n_pos  = int((obv_vals > 0).sum())
    n_neg  = int((obv_vals < 0).sum())

    ax.set_title(
        f"{full_name}  —  Free Kick Passes\n"
        f"{n} passes  |  Mean OBV: {mean_o:+.4f}  |  "
        f"Positive: {n_pos}  |  Negative: {n_neg}",
        fontsize=13, fontweight="bold", pad=12,
    )

    slug = "".join(
        c if c.isascii() and (c.isalnum() or c == "_") else "_"
        for c in player_substr.lower().replace(" ", "_")
    )
    out = OUT_DIR / f"fk_deadzone_{slug}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved -> {out}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for player in TARGET_PLAYERS:
        _plot_player(player)
