"""Single-pitch overlay of all Barcelona FK passes from the defensive 2/3.

All passes from all players overlaid on one pitch, coloured by OBV.
Useful for spotting spatial patterns in dead-zone free-kick delivery.

Run from the project root:
    python src/fk_deadzone_all_overlay.py
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from mplsoccer import Pitch

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "all_data"
_csv_candidates = [ROOT / "matches.csv", ROOT / "data" / "matches.csv"]
MATCHES_CSV = next((p for p in _csv_candidates if p.exists()), _csv_candidates[0])
OUT_DIR  = ROOT / "assets" / "offensive_freekicks"

# ── Config ───────────────────────────────────────────────────────────────────
TEAM            = "Barcelona"
DEF2THIRD_MAX_X = 80.0   # x <= 80 = own defensive 2/3 on StatsBomb pitch
OBV_LIMIT       = 0.02
OBV_CMAP        = "RdYlGn"
PITCH_LINE      = "#888888"


# ── Helpers ──────────────────────────────────────────────────────────────────

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


def collect() -> pd.DataFrame:
    rows: list[dict] = []
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
            if ev.get("team", {}).get("name") != TEAM:
                continue

            start = ev.get("location") or []
            end   = ev.get("pass", {}).get("end_location") or []
            if len(start) < 2 or len(end) < 2:
                continue
            if start[0] > DEF2THIRD_MAX_X:
                continue

            rows.append({
                "start_x": start[0],
                "start_y": start[1],
                "end_x":   end[0],
                "end_y":   end[1],
                "obv":     _obv(ev),
            })

    return pd.DataFrame(rows)


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot(df: pd.DataFrame) -> None:
    obv_vals    = df["obv"].values
    norm        = TwoSlopeNorm(vmin=-OBV_LIMIT, vcenter=0.0, vmax=OBV_LIMIT)
    cmap        = plt.colormaps[OBV_CMAP]
    obv_clipped = np.clip(obv_vals, -OBV_LIMIT, OBV_LIMIT)

    # Thinner arrows since many passes overlap — width fixed, alpha reduced
    width = 1.8

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="#f8f8f8",
        line_color=PITCH_LINE,
        linewidth=1.2,
    )
    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("white")
    pitch.draw(ax=ax)

    for idx, (_, row) in enumerate(df.iterrows()):
        color = cmap(norm(obv_clipped[idx]))
        pitch.arrows(
            row["start_x"], row["start_y"],
            row["end_x"],   row["end_y"],
            ax=ax, color=color,
            width=width, headwidth=width * 2.5, headlength=width * 2.0,
            alpha=0.45, zorder=4,
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.02, label="OBV (net change)")
    cbar.ax.axhline(0, color="black", linewidth=0.9, linestyle="--")
    cbar.set_ticks([-OBV_LIMIT, -0.01, 0, 0.01, OBV_LIMIT])
    cbar.set_ticklabels([f"<= {-OBV_LIMIT:.2f}", "-0.01", "0", "+0.01", f">= +{OBV_LIMIT:.2f}"])

    n      = len(df)
    mean_o = float(obv_vals.mean())
    n_pos  = int((obv_vals > 0).sum())
    n_neg  = int((obv_vals < 0).sum())

    ax.set_title(
        f"FC Barcelona — All Dead-Zone Free Kick Passes (x \u2264 80)\n"
        f"{n} passes  |  Mean OBV: {mean_o:+.4f}  |  "
        f"Positive: {n_pos}  |  Negative: {n_neg}",
        fontsize=13, fontweight="bold", pad=12,
    )

    out = OUT_DIR / "fk_deadzone_all_overlay.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Collecting all Barcelona FK passes from defensive 2/3...")
    df = collect()
    print(f"Found {len(df)} passes across all players")
    plot(df)
