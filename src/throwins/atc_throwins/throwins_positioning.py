"""
throwins_positioning.py

Player position heatmaps at the moment of Barcelona throw-ins.

SkillCorner tracking data (x, y in metres, origin = pitch centre) gives all
22 player positions at the frame of each throw-in.  Positions are normalized
so that every throw-in appears to come from the same touchline point:

    (dx, dy) where dx > 0 = toward opponent's goal  (along pitch)
              and  dy > 0 = into the pitch            (away from touchline)

Three separate heatmaps per team for Defensive / Middle / Attacking zones.

Attacking direction is inferred from Barcelona's GK position in each frame
rather than from home/away or period metadata, making the logic robust to
any SkillCorner coordinate convention.

Usage:
    python src/throwins/atc_throwins/throwins_positioning.py
"""

import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from scipy.ndimage import gaussian_filter
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    DEFENSIVE_THIRD_MAX,
    ATTACKING_THIRD_MIN,
    _read_matches_df,
)

_PROJECT_ROOT   = Path(__file__).parent.parent.parent.parent
SKILLCORNER_DIR = _PROJECT_ROOT / "data" / "skillcorner"

_HALF_LEN = 52.5   # pitch half-length in metres (x: -52.5 to +52.5)
_HALF_WID = 34.0   # pitch half-width  in metres (y: -34   to +34)

ZONE_ORDER = ["Defensive", "Middle", "Attacking"]

# SkillCorner start_type values that identify a throw-in being taken.
# The script prints available types if none match, aiding discovery.
_TI_START_TYPES = frozenset({
    "throw_in_taken", "throw_in", "throwin", "attacking_throw_in",
})

# Heatmap display range in normalised coordinates (metres)
_DX = (-50, 50)    # along pitch, centred on throw-in
_DY = (-2,  36)    # into pitch; 0 = touchline, ~68 = far touchline
_N_BINS = 40


# ── SkillCorner I/O ───────────────────────────────────────────────────────────

def _zip_path(sc_id: int) -> Path | None:
    p = SKILLCORNER_DIR / f"{sc_id}.zip"
    return p if p.exists() else None


def _read_member(sc_id: int, filename: str) -> bytes | None:
    p = _zip_path(sc_id)
    if p is None:
        return None
    with zipfile.ZipFile(p) as zf:
        return zf.read(filename) if filename in zf.namelist() else None


def read_dynamic_events(sc_id: int) -> pd.DataFrame | None:
    raw = _read_member(sc_id, f"{sc_id}_dynamic_events.csv")
    return pd.read_csv(io.BytesIO(raw)) if raw else None


def read_match_meta(sc_id: int) -> dict:
    raw = _read_member(sc_id, f"{sc_id}.json")
    return json.loads(raw.decode("utf-8")) if raw else {}


def iter_tracking_frames(sc_id: int):
    raw = _read_member(sc_id, f"{sc_id}_tracking_extrapolated.jsonl")
    if raw is None:
        return
    for line in io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"):
        line = line.strip()
        if line:
            yield json.loads(line)


# ── Metadata helpers ──────────────────────────────────────────────────────────

def parse_player_index(meta: dict) -> dict[int, dict]:
    index: dict[int, dict] = {}
    for p in meta.get("players", []):
        pid = p.get("id") or p.get("player_id")
        if pid is None:
            continue
        index[int(pid)] = {
            "team_id": p.get("team_id"),
            "is_gk":   (p.get("position", {}).get("name", "") == "Goalkeeper"
                        if isinstance(p.get("position"), dict) else False),
        }
    return index


def find_barca_tid(meta: dict) -> int | None:
    for key in ("home_team", "away_team", "homeTeam", "awayTeam"):
        val = meta.get(key, {})
        if isinstance(val, dict):
            name = val.get("name", "")
            tid  = val.get("id") or val.get("team_id")
            if BARCELONA.casefold() in name.casefold() and tid is not None:
                return int(tid)
    return None


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _attacks_positive_x(frame: dict, player_index: dict, barca_tid: int) -> bool | None:
    """Infer attacking direction from Barcelona's GK position.

    The GK stands close to their own goal: if GK x < 0, their goal is on the
    left, so Barcelona attacks toward positive x, and vice versa.
    """
    for p in frame.get("player_data", []):
        pid = p.get("player_id")
        if pid is None:
            continue
        m = player_index.get(int(pid), {})
        if m.get("is_gk") and m.get("team_id") == barca_tid:
            x = p.get("x")
            if x is not None:
                return float(x) < 0
    return None


def _sk_zone(x_ti: float, attacks_pos: bool) -> str:
    """Zone of the throw-in location from Barcelona's attacking perspective."""
    # Convert SkillCorner x to StatsBomb-style x (0 = own goal, 120 = opp goal)
    if attacks_pos:
        x_sb = (x_ti + _HALF_LEN) / (2 * _HALF_LEN) * 120
    else:
        x_sb = (_HALF_LEN - x_ti) / (2 * _HALF_LEN) * 120
    if x_sb <= DEFENSIVE_THIRD_MAX:
        return "Defensive"
    if x_sb >= ATTACKING_THIRD_MIN:
        return "Attacking"
    return "Middle"


def _normalize(x: float, y: float,
               x_ti: float, y_ti: float,
               attacks_pos: bool) -> tuple[float, float]:
    """Translate and rotate so throw-in = (0,0), forward = +dx, into-pitch = +dy."""
    x_sign = 1.0 if attacks_pos else -1.0   # forward direction
    y_sign = -1.0 if y_ti > 0 else 1.0     # top touchline → flip y so dy > 0 into pitch
    return (x - x_ti) * x_sign, (y - y_ti) * y_sign


# ── Data collection ───────────────────────────────────────────────────────────

def collect_positions() -> dict[str, dict]:
    """Return per-zone player positions normalised to throw-in origin.

    Structure: {zone: {"barca": [(dx, dy), ...], "opp": [...], "count": int}}
    """
    result = {z: {"barca": [], "opp": [], "count": 0} for z in ZONE_ORDER}
    all_types: set[str] = set()

    for _, row in _read_matches_df().iterrows():
        if pd.isna(row.get("skillcorner")):
            continue
        sc_id = int(row["skillcorner"])
        if _zip_path(sc_id) is None:
            continue

        meta         = read_match_meta(sc_id)
        player_index = parse_player_index(meta)
        barca_tid    = find_barca_tid(meta)
        if barca_tid is None:
            continue

        dyn = read_dynamic_events(sc_id)
        if dyn is None:
            continue

        all_types.update(dyn["start_type"].dropna().astype(str).str.casefold().unique())

        ti_rows = dyn[
            dyn["start_type"].astype(str).str.casefold().isin(_TI_START_TYPES)
            & (dyn["team_id"] == barca_tid)
        ].dropna(subset=["frame_start"])

        if ti_rows.empty:
            continue

        target = {int(f) for f in ti_rows["frame_start"]}

        for frame in iter_tracking_frames(sc_id):
            fid = frame.get("frame")
            if fid not in target:
                continue

            attacks_pos = _attacks_positive_x(frame, player_index, barca_tid)
            if attacks_pos is None:
                target.discard(fid)
                continue

            barca_out, opp_all = [], []
            for p in frame.get("player_data", []):
                pid  = p.get("player_id")
                x, y = p.get("x"), p.get("y")
                if pid is None or x is None or y is None:
                    continue
                m   = player_index.get(int(pid), {})
                tid = m.get("team_id")
                if m.get("is_gk"):
                    pass   # exclude GKs from heatmap but don't add to lists
                elif tid == barca_tid:
                    barca_out.append((float(x), float(y)))
                else:
                    opp_all.append((float(x), float(y)))

            if not barca_out:
                target.discard(fid)
                continue

            # Throw-in taker = Barcelona outfield player furthest from pitch centre (max |y|)
            x_ti, y_ti = max(barca_out, key=lambda p: abs(p[1]))
            zone = _sk_zone(x_ti, attacks_pos)

            result[zone]["count"] += 1
            for x, y in barca_out:
                result[zone]["barca"].append(_normalize(x, y, x_ti, y_ti, attacks_pos))
            for x, y in opp_all:
                result[zone]["opp"].append(_normalize(x, y, x_ti, y_ti, attacks_pos))

            target.discard(fid)
            if not target:
                break

    if not any(result[z]["barca"] for z in ZONE_ORDER):
        print("\nNo throw-in frames found in SkillCorner data.")
        print(f"Available start_types: {sorted(all_types)}")

    return result


# ── Plotting ──────────────────────────────────────────────────────────────────

def _make_heatmap(pts: list[tuple[float, float]]) -> np.ndarray:
    if not pts:
        return np.zeros((_N_BINS, _N_BINS))
    xs = np.clip([p[0] for p in pts], *_DX)
    ys = np.clip([p[1] for p in pts], *_DY)
    h, _, _ = np.histogram2d(xs, ys, bins=_N_BINS, range=[_DX, _DY])
    if _HAS_SCIPY:
        h = gaussian_filter(h, sigma=1.5)
    h = h / h.max() if h.max() > 0 else h
    return h.T   # transpose: rows = y, cols = x (for imshow)


def plot_positioning_heatmaps(
    positions: dict[str, dict],
    save: bool = True,
) -> None:
    """2×3 heatmap grid: rows = Barcelona / Opponent, columns = zone."""
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.set_facecolor("white")

    row_meta = [
        ("Barcelona", "barca", "Reds"),
        ("Opponent",  "opp",   "Blues"),
    ]

    for row, (label, key, cmap) in enumerate(row_meta):
        for col, zone in enumerate(ZONE_ORDER):
            ax    = axes[row][col]
            n     = positions[zone]["count"]
            pts   = positions[zone][key]

            h = _make_heatmap(pts)
            ax.imshow(
                h,
                origin="lower",
                extent=[*_DX, *_DY],
                aspect="auto",
                cmap=cmap,
                vmin=0, vmax=1,
                alpha=0.85,
            )

            # Touchline (dy = 0) and throw-in origin
            ax.axhline(0, color="white", lw=2.0, alpha=0.9)
            ax.axvline(0, color="white", lw=1.0, alpha=0.4, linestyle="--")
            ax.plot(0, 0, "o", color="cyan", markersize=9, zorder=6)

            ax.set_facecolor("#1a1a2e")
            ax.set_xlim(*_DX)
            ax.set_ylim(*_DY)
            ax.set_title(
                f"{label}  —  {zone} zone  (n={n} throw-ins)",
                fontsize=10, pad=6, color="black",
            )
            if col == 0:
                ax.set_ylabel("Into pitch (m) →", fontsize=8)
            if row == 1:
                ax.set_xlabel(
                    "← Own goal  |  Opp goal →\n(metres along pitch, relative to throw-in)",
                    fontsize=8,
                )
            ax.tick_params(labelsize=7)

    fig.suptitle(
        "Player positions at the moment of a Barcelona throw-in  ·  normalized to common origin\n"
        "Cyan dot = throw-in point  ·  white line = touchline  "
        "·  GKs excluded  ·  'Into pitch' = away from touchline",
        fontsize=12, y=1.02, color="black",
    )
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_player_positioning.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


if __name__ == "__main__":
    positions = collect_positions()
    for zone in ZONE_ORDER:
        nb = len(positions[zone]["barca"])
        no = len(positions[zone]["opp"])
        n  = positions[zone]["count"]
        print(f"{zone:12s}: {n} throw-ins  →  {nb} Barça positions, {no} opp positions")
    plot_positioning_heatmaps(positions)
