"""
def_throwins_winback_viewer.py

Interactive viewer: player positions at the moment of opponent throw-ins
where Barcelona won the ball back.

Display coordinate system (normalised — same as positioning heatmaps)
-----------------------------------------------------------------------
  Origin (0, 0)  = throw-in taker position
  +x             = toward opponent's goal
  -x             = toward Barcelona's goal
  +y             = into the pitch (away from touchline)
  y = 0          = touchline

This avoids any SkillCorner ↔ StatsBomb coordinate conversion: player
positions use the same _normalize() logic as def_throwins_positioning.py,
and the throw-in arrow is computed from StatsBomb dx/dy in metres
(same formula as plot_combined_defense_heatmap in throwins_defense.py).

Navigation: ← → arrow keys or on-screen Prev / Next buttons.

Individual PNGs are saved to:
    assets/throwins/throwins_defense_players_winback/

Usage:
    python src/throwins/def_throwins/def_throwins_winback_viewer.py
"""

import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.widgets import Button

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    DEFENSIVE_THIRD_MAX,
    ATTACKING_THIRD_MIN,
    _read_matches_df,
    opponent_throw_ins,
    read_statsbomb,
    throw_in_possession_won,
)

_PROJECT_ROOT   = Path(__file__).parent.parent.parent.parent
SKILLCORNER_DIR = _PROJECT_ROOT / "data" / "skillcorner"
OUT_DIR = THROWINS_ASSETS_DIR / "throwins_defense_players_winback"

_HALF_LEN  = 52.5           # SkillCorner pitch half-length (metres)
_HALF_WID  = 34.0           # SkillCorner pitch half-width  (metres)
_PITCH_LEN = 120            # StatsBomb pitch length
_PITCH_WID = 80             # StatsBomb pitch width
_SB_X_TO_M = 105 / 120     # StatsBomb units → metres (longitudinal)
_SB_Y_TO_M = 68  / 80      # StatsBomb units → metres (lateral)

TIME_TOL = 5.0              # max seconds difference for StatsBomb↔SkillCorner match

# Normalised display range (metres, same as positioning heatmaps)
_DX = (-50, 50)
_DY = (-2,  70)

_TI_START_TYPES = frozenset({
    "throw_in_reception",
    "throw_in_interception",
})


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
        role = p.get("player_role", {})
        is_gk = isinstance(role, dict) and (
            "goalkeeper" in role.get("name", "").lower()
            or "goalkeeper" in role.get("position_group", "").lower()
        )
        entry = {"team_id": p.get("team_id"), "is_gk": is_gk}
        index[int(pid)] = entry
        to = p.get("trackable_object")
        if to is not None:
            index[int(to)] = entry
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


def find_opp_tid(meta: dict, barca_tid: int) -> int | None:
    for key in ("home_team", "away_team", "homeTeam", "awayTeam"):
        val = meta.get(key, {})
        if isinstance(val, dict):
            tid = val.get("id") or val.get("team_id")
            if tid is not None and int(tid) != barca_tid:
                return int(tid)
    return None


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _barca_attacks_positive_x(
    frame: dict, player_index: dict, barca_tid: int
) -> bool | None:
    """True if Barcelona's GK is at negative x (Barça attacks toward +x)."""
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


def _normalize(
    x: float, y: float,
    x_ti: float, y_ti: float,
    barca_attacks_pos: bool,
) -> tuple[float, float]:
    """Normalise SkillCorner position to throw-in-origin frame.

    Same logic as def_throwins_positioning.py:
      dx < 0 = toward Barça's goal
      dy > 0 = into the pitch
    """
    x_sign = 1.0 if barca_attacks_pos else -1.0
    y_sign = -1.0 if y_ti > 0 else 1.0
    return (x - x_ti) * x_sign, (y - y_ti) * y_sign


def _flip_x(x: float) -> float:
    return _PITCH_LEN - x


def _def_zone(x_barca: float) -> str:
    if x_barca <= DEFENSIVE_THIRD_MAX:
        return "Defensive"
    if x_barca >= ATTACKING_THIRD_MIN:
        return "Attacking"
    return "Middle"


def _event_seconds(ev: dict) -> float:
    """Seconds within period from StatsBomb timestamp."""
    ts = ev.get("timestamp", "")
    if ts:
        try:
            h, m, s = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, AttributeError):
            pass
    return ev.get("minute", 0) * 60 + ev.get("second", 0)


def _parse_sk_time(t) -> float:
    """Parse SkillCorner time_start (e.g. '06:15.7' or '1:06:15.7') to seconds."""
    try:
        parts = str(t).strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, AttributeError):
        pass
    try:
        return float(t)
    except (ValueError, TypeError):
        return float("nan")


# ── Data collection ───────────────────────────────────────────────────────────

def collect_winback_situations() -> list[dict]:
    """Match StatsBomb winback throw-in events to SkillCorner tracking frames.

    All positions are stored in normalised SkillCorner metres:
        (dx, dy) relative to throw-in origin, dy > 0 into pitch.

    The throw-in arrow (from StatsBomb) is also pre-computed in metres
    using the same formula as plot_combined_defense_heatmap.
    """
    df_matches = _read_matches_df()
    situations: list[dict] = []

    for _, row in df_matches.iterrows():
        sb_id = int(row["statsbomb"]) if not pd.isna(row.get("statsbomb")) else None
        sc_id = int(row["skillcorner"]) if not pd.isna(row.get("skillcorner")) else None
        if sb_id is None or sc_id is None or _zip_path(sc_id) is None:
            continue

        # ── StatsBomb: collect winback throw-in events ────────────────────────
        try:
            events = read_statsbomb(sb_id)
        except FileNotFoundError:
            continue

        barca_in_game = any(
            BARCELONA.casefold() in ev.get("team", {}).get("name", "").casefold()
            for ev in events
        )
        if not barca_in_game:
            continue

        sorted_events = sorted(events, key=lambda e: e.get("index", -1))
        match_label = (
            f"{row.get('home', '')} {row.get('score', '')} {row.get('away', '')}"
        ).strip()

        sb_winbacks: list[dict] = []
        for ev in opponent_throw_ins(sorted_events, BARCELONA):
            won_by_opp = throw_in_possession_won(ev, sorted_events)
            if won_by_opp is not False:   # False = opp lost ball = Barça won it back
                continue

            loc     = ev.get("location") or [None, None]
            end_loc = ev.get("pass", {}).get("end_location") or [None, None]
            if loc[0] is None or end_loc[0] is None:
                continue

            x_b     = _flip_x(loc[0])
            end_x_b = _flip_x(end_loc[0])
            y_b     = loc[1]
            end_y_b = end_loc[1]

            # Arrow in metres (same formula as plot_combined_defense_heatmap)
            dx_m = (end_x_b - x_b) * _SB_X_TO_M
            dy_m = (
                (end_y_b - y_b) * _SB_Y_TO_M if y_b < 40
                else (y_b - end_y_b) * _SB_Y_TO_M
            )

            sb_winbacks.append({
                "period":      ev.get("period", 0),
                "time_sec":    _event_seconds(ev),
                "minute":      ev.get("minute", 0),
                "zone":        _def_zone(x_b),
                "arrow_dx_m":  dx_m,
                "arrow_dy_m":  dy_m,
            })

        if not sb_winbacks:
            continue

        # ── SkillCorner: get opponent throw-in frames with timing ─────────────
        meta         = read_match_meta(sc_id)
        player_index = parse_player_index(meta)
        barca_tid    = find_barca_tid(meta)
        if barca_tid is None:
            continue
        opp_tid = find_opp_tid(meta, barca_tid)
        if opp_tid is None:
            continue

        dyn = read_dynamic_events(sc_id)
        if dyn is None:
            continue

        dyn_copy = dyn.copy()
        dyn_copy["team_id"] = pd.to_numeric(dyn_copy["team_id"], errors="coerce")

        ti_rows = dyn_copy[
            dyn_copy["start_type"].astype(str).str.casefold().isin(_TI_START_TYPES)
            & (dyn_copy["team_id"] == opp_tid)
        ].dropna(subset=["frame_start", "period", "time_start"])

        if ti_rows.empty:
            continue

        # ── Match by period + time ────────────────────────────────────────────
        matched: dict[int, dict] = {}
        for sbe in sb_winbacks:
            period_rows = ti_rows[ti_rows["period"] == sbe["period"]]
            if period_rows.empty:
                continue
            times = period_rows["time_start"].apply(_parse_sk_time)
            diffs = (times - sbe["time_sec"]).abs()
            best_idx = diffs.idxmin()
            if diffs[best_idx] <= TIME_TOL:
                fid = int(period_rows.loc[best_idx, "frame_start"])
                if fid not in matched:
                    matched[fid] = sbe

        if not matched:
            continue

        # ── Read tracking frames and normalise player positions ───────────────
        target = set(matched)
        for frame in iter_tracking_frames(sc_id):
            fid = frame.get("frame")
            if fid not in target:
                continue

            barca_attacks_pos = _barca_attacks_positive_x(
                frame, player_index, barca_tid
            )
            if barca_attacks_pos is None:
                target.discard(fid)
                continue

            # Separate players into teams (raw SkillCorner coords)
            throwing_pos: list[tuple] = []
            barca_raw:    list[tuple] = []
            opp_raw:      list[tuple] = []

            for p in frame.get("player_data", []):
                pid = p.get("player_id")
                x, y = p.get("x"), p.get("y")
                if pid is None or x is None or y is None:
                    continue
                m   = player_index.get(int(pid), {})
                tid = m.get("team_id")
                is_gk = m.get("is_gk", False)
                if tid == opp_tid:
                    throwing_pos.append((float(x), float(y), is_gk))
                elif tid == barca_tid:
                    barca_raw.append((float(x), float(y), is_gk))

            if not throwing_pos:
                target.discard(fid)
                continue

            # Throw-in taker = opponent outfield player with max |y|
            x_ti, y_ti, _ = max(
                (p for p in throwing_pos if not p[2]),   # exclude GK
                key=lambda p: abs(p[1]),
                default=max(throwing_pos, key=lambda p: abs(p[1])),
            )

            # Normalise all positions to throw-in origin
            def norm(players):
                result = []
                for x, y, is_gk in players:
                    dx, dy = _normalize(x, y, x_ti, y_ti, barca_attacks_pos)
                    result.append((dx, dy, is_gk))
                return result

            sbe = matched[fid]
            situations.append({
                **sbe,
                "sc_id":         sc_id,
                "game_id":       sb_id,
                "frame_id":      fid,
                "barca_players": norm(barca_raw),
                "opp_players":   norm(throwing_pos),
                "match_label":   match_label,
            })

            target.discard(fid)
            if not target:
                break

    return situations


# ── Drawing ───────────────────────────────────────────────────────────────────

_LEGEND_HANDLES = [
    mpatches.Patch(color="#e63946", label="Barcelona outfield"),
    mpatches.Patch(color="#4895ef", label="Opponent outfield"),
    plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#e63946",
               markersize=9, label="Barcelona GK"),
    plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#4895ef",
               markersize=9, label="Opponent GK"),
    plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#f4a261",
               markersize=9, label="Throw-in origin (0, 0)"),
]


def draw_situation(ax, sit: dict, idx: int, total: int) -> None:
    ax.set_facecolor("#1a1a2e")
    ax.set_xlim(*_DX)
    ax.set_ylim(*_DY)

    # Pitch reference lines
    ax.axhline(0, color="white", lw=2.0, alpha=0.9)          # touchline
    ax.axvline(0, color="white", lw=0.8, alpha=0.35, ls="--") # throw-in x ref

    # Barcelona players
    for dx, dy, is_gk in sit["barca_players"]:
        ax.plot(
            dx, dy,
            "D" if is_gk else "o",
            color="#e63946",
            markersize=10 if is_gk else 8,
            markeredgecolor="white", markeredgewidth=0.7,
            zorder=5,
        )

    # Opponent players
    for dx, dy, is_gk in sit["opp_players"]:
        ax.plot(
            dx, dy,
            "D" if is_gk else "s",
            color="#4895ef",
            markersize=10 if is_gk else 8,
            markeredgecolor="white", markeredgewidth=0.7,
            zorder=5,
        )

    # Throw-in origin
    ax.plot(0, 0, "o", color="#f4a261", markersize=11,
            markeredgecolor="white", markeredgewidth=0.8, zorder=7)

    # Throw-in arrow (StatsBomb direction, converted to metres)
    adx = sit["arrow_dx_m"]
    ady = sit["arrow_dy_m"]
    if abs(adx) > 0.1 or abs(ady) > 0.1:
        ax.annotate(
            "",
            xy=(adx, ady),
            xytext=(0, 0),
            arrowprops=dict(
                arrowstyle="-|>",
                color="#f4a261",
                lw=2.2,
                mutation_scale=18,
            ),
            zorder=6,
        )

    ax.set_xlabel(
        "← Barça goal  |  Opp goal →  (metres from throw-in)",
        fontsize=9, color="black",
    )
    ax.set_ylabel("Into pitch (metres)", fontsize=9, color="black")
    ax.tick_params(labelsize=8)
    ax.set_title(
        f"Situation {idx + 1}/{total}  ·  {sit['zone']} zone  ·  "
        f"{sit['match_label']}  ·  Min {sit['minute']}",
        fontsize=10, pad=8, color="black",
    )


# ── Save PNGs ─────────────────────────────────────────────────────────────────

def save_all(situations: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(situations)

    for i, sit in enumerate(situations):
        fig, ax = plt.subplots(figsize=(10, 8))
        fig.set_facecolor("white")
        draw_situation(ax, sit, i, total)
        ax.legend(handles=_LEGEND_HANDLES, loc="upper right",
                  fontsize=9, framealpha=0.85)

        safe_label = (
            sit["match_label"].replace(" ", "_").replace("/", "-")
        )
        fname = f"{i + 1:03d}_{sit['zone']}_min{sit['minute']}_{safe_label}.png"
        fig.savefig(OUT_DIR / fname, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"  Saved {fname}")

    print(f"\nAll {total} PNGs saved to {OUT_DIR}")


# ── Interactive viewer ────────────────────────────────────────────────────────

def launch_viewer(situations: list[dict]) -> None:
    if not situations:
        print("No winback situations to display.")
        return

    total = len(situations)
    state = {"idx": 0}

    fig = plt.figure(figsize=(10, 9))
    fig.set_facecolor("white")
    fig.suptitle(
        "Opponent throw-ins → Barcelona won the ball back  ·  normalised to throw-in origin\n"
        "← → keys or buttons to navigate  "
        "·  ○ = Barça outfield  ·  □ = Opp outfield  ·  ◇ = GK",
        fontsize=10, y=0.99,
    )

    ax_pitch = fig.add_axes([0.08, 0.11, 0.88, 0.83])
    ax_prev  = fig.add_axes([0.10, 0.01, 0.13, 0.06])
    ax_next  = fig.add_axes([0.77, 0.01, 0.13, 0.06])

    def refresh():
        ax_pitch.cla()
        draw_situation(ax_pitch, situations[state["idx"]], state["idx"], total)
        ax_pitch.legend(
            handles=_LEGEND_HANDLES,
            loc="upper right", fontsize=9, framealpha=0.85,
        )
        fig.canvas.draw_idle()

    def on_prev(_):
        state["idx"] = (state["idx"] - 1) % total
        refresh()

    def on_next(_):
        state["idx"] = (state["idx"] + 1) % total
        refresh()

    def on_key(event):
        if event.key == "left":
            on_prev(None)
        elif event.key == "right":
            on_next(None)

    btn_prev = Button(ax_prev, "← Prev", color="#dddddd", hovercolor="#bbbbbb")
    btn_next = Button(ax_next, "Next →", color="#dddddd", hovercolor="#bbbbbb")
    btn_prev.on_clicked(on_prev)
    btn_next.on_clicked(on_next)
    fig.canvas.mpl_connect("key_press_event", on_key)

    refresh()
    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Collecting winback situations from StatsBomb + SkillCorner ...")
    situations = collect_winback_situations()
    print(f"Found {len(situations)} matched situations.")

    if not situations:
        print(
            "No situations found. Check SkillCorner zips are present and "
            f"TIME_TOL ({TIME_TOL}s) is wide enough."
        )
    else:
        by_zone: dict[str, int] = {}
        for s in situations:
            by_zone[s["zone"]] = by_zone.get(s["zone"], 0) + 1
        for zone, n in by_zone.items():
            print(f"  {zone}: {n}")

        print("\nSaving individual PNGs ...")
        save_all(situations)

        print("\nLaunching interactive viewer ...")
        launch_viewer(situations)
