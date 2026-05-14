"""
fk_animation.py

Pick the clearest Zonal-Marking and Man-Marking defensive free kicks from
``fk_zonal_analysis.collect_marking_rows()`` and render each as a short
GIF using the SkillCorner tracking pipeline that
``src/offense/corner_animation_skillcorner.py`` already provides.

The animation shows the period bracketing the FK delivery:
``PRE_FRAMES`` SC frames before reception → ``POST_FRAMES`` after. The
shot frame (FK delivery instant, ``SHOT_OFFSET_FRAMES`` before reception)
and the reception frame are annotated in the bottom-right corner so the
viewer can visually check the tight-set intersection criterion.

Outputs
-------
``assets/defense/free_kicks/animations/fk_<system>_<sc_id>_<frame>.gif``

Usage
-----
    uv run python src/defense/free_kicks/fk_animation.py
"""

from __future__ import annotations

import io
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from mplsoccer import Pitch

# ── Reuse the corner-animation helpers ───────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "offense"))
from corner_animation_skillcorner import (  # noqa: E402
    BARCA_COLOR, OPPONENT_COLOR, BALL_COLOR, BALL_UNTRACKED_COLOR, PITCH_LINE_COLOR,
    _ball_is_tracked, _find_skillcorner_zip, _load_skillcorner_meta,
    _open_zip_member_by_basename, _player_payload, _safe_float,
    _skillcorner_to_statsbomb, _team_attacks_right,
)

# ── Reuse our analysis ────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fk_zonal_analysis import (  # noqa: E402
    MAN_THRESHOLD_M, OUT_DIR, SHOT_OFFSET_FRAMES, collect_marking_rows,
)

ANIM_DIR = OUT_DIR / "animations"
ANIM_DIR.mkdir(parents=True, exist_ok=True)

# Window around the reception frame (10 fps tracking).
PRE_FRAMES   = 30   # ≈ 3 s before reception (covers the shot frame at -20)
POST_FRAMES  = 60   # ≈ 6 s after reception
FPS          = 10

# How many examples per system.
N_PER_SYSTEM = 2
# Engagement threshold for picking visually interesting examples.
MIN_ENGAGED  = 3

# Colours.
TIGHT_RING_COLOR = "#111111"
HIGHLIGHT_BORDER = "#111111"


# ─────────────────────────────────────────────────────────────────────────────
# Candidate selection
# ─────────────────────────────────────────────────────────────────────────────
def pick_candidates(per_fk: pd.DataFrame) -> pd.DataFrame:
    """Pick the strongest Zonal and Man-Marking exemplars.

    Strongest Zonal = lowest ``man_frac`` (ties broken by most engaged).
    Strongest Man-Marking = highest ``man_frac`` (ties broken by most engaged).
    Requires ``n_engaged >= MIN_ENGAGED`` so the picture has enough defenders
    actually doing something.
    """
    eligible = per_fk[per_fk["n_engaged"] >= MIN_ENGAGED]
    if eligible.empty:
        return pd.DataFrame()
    zonal = (
        eligible[eligible["system"] == "Zonal-Marking"]
        .sort_values(["man_frac", "n_engaged"], ascending=[True, False])
        .head(N_PER_SYSTEM)
    )
    man = (
        eligible[eligible["system"] == "Man-Marking"]
        .sort_values(["man_frac", "n_engaged"], ascending=[False, False])
        .head(N_PER_SYSTEM)
    )
    return pd.concat([zonal, man], ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tracking-window extraction
# ─────────────────────────────────────────────────────────────────────────────
def _extract_windows(
    sc_id: int,
    fk_rows: list[pd.Series],
) -> dict[int, list[dict[str, Any]]]:
    """Stream the SC tracking JSONL once and capture every required window.

    Returns ``{recv_frame: [frame_dict, ...]}``. Each frame_dict has
    ``timestamp``, ``time_sec``, ``t_rel`` (relative to reception),
    ``players`` (list of dicts with ``id``, ``name``, ``team``, ``x``, ``y``,
    ``team_id``) and ``ball`` (or ``None``).
    """
    zip_path = _find_skillcorner_zip(str(sc_id))
    meta, players, barca_tid, _ = _load_skillcorner_meta(zip_path, str(sc_id))
    pitch_length = float(meta["pitch_length"])
    pitch_width  = float(meta["pitch_width"])

    windows: dict[int, list[dict[str, Any]]] = {row.recv_frame: [] for row in fk_rows}
    starts = {row.recv_frame: row.recv_frame - PRE_FRAMES for row in fk_rows}
    ends   = {row.recv_frame: row.recv_frame + POST_FRAMES for row in fk_rows}
    period_of = {row.recv_frame: row.period for row in fk_rows}
    max_end = max(ends.values())

    with zipfile.ZipFile(zip_path) as zf:
        with _open_zip_member_by_basename(zf, f"{sc_id}_tracking_extrapolated.jsonl") as fh:
            for line in io.TextIOWrapper(fh, encoding="utf-8"):
                if not line.strip():
                    continue
                frame = json.loads(line)
                fid = frame.get("frame")
                if fid is None:
                    continue
                if fid > max_end:
                    break
                # Which FKs need this frame?
                hits = [r for r, s in starts.items() if s <= fid <= ends[r]]
                if not hits:
                    continue

                period = int(frame.get("period", 1))
                attack_right = _team_attacks_right(meta, barca_tid, period)

                # Players
                player_rows: list[dict[str, Any]] = []
                for p in frame.get("player_data", []):
                    payload = _player_payload(
                        p, players, barca_team_id=barca_tid, touch_names=set(),
                    )
                    if payload is None:
                        continue
                    x_mpl, y_mpl = _skillcorner_to_statsbomb(
                        payload.pop("x_raw"), payload.pop("y_raw"),
                        pitch_length=pitch_length, pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    payload["x"] = round(x_mpl, 3)
                    payload["y"] = round(y_mpl, 3)
                    payload["x_raw"] = float(p["x"])
                    payload["y_raw"] = float(p["y"])
                    payload["team_id"] = int(players[int(p["player_id"])].team_id)
                    player_rows.append(payload)

                # Ball
                ball_payload = None
                ball = frame.get("ball_data", {}) or {}
                bx = _safe_float(ball.get("x"))
                by = _safe_float(ball.get("y"))
                if bx is not None and by is not None:
                    bx_mpl, by_mpl = _skillcorner_to_statsbomb(
                        bx, by,
                        pitch_length=pitch_length, pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    ball_payload = {
                        "x": round(bx_mpl, 3),
                        "y": round(by_mpl, 3),
                        "tracked": _ball_is_tracked(ball),
                    }

                for rf in hits:
                    if period != period_of[rf]:
                        continue
                    windows[rf].append({
                        "frame":     fid,
                        "t_rel":     (fid - rf) / FPS,
                        "players":   player_rows,
                        "ball":      ball_payload,
                    })

    return windows


# ─────────────────────────────────────────────────────────────────────────────
# Per-frame tight-set computation (in raw SC metres, for accuracy)
# ─────────────────────────────────────────────────────────────────────────────
def _per_frame_tight_pairs(players: list[dict[str, Any]]) -> dict[int, set[int]]:
    """Map ``barca_player_id`` → set of opp ``player_id`` within the tight radius."""
    barca = [p for p in players if p["team"] == "Barcelona"]
    opp   = [p for p in players if p["team"] == "Opponent"]
    out: dict[int, set[int]] = {}
    for b in barca:
        tight: set[int] = set()
        for o in opp:
            d = math.hypot(b["x_raw"] - o["x_raw"], b["y_raw"] - o["y_raw"])
            if d <= MAN_THRESHOLD_M:
                tight.add(int(o["id"]))
        if tight:
            out[int(b["id"])] = tight
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────
def render(
    fk_row: pd.Series,
    frames: list[dict[str, Any]],
    out_path: Path,
) -> None:
    if not frames:
        print(f"  no frames captured for FK at {fk_row.recv_frame}, skipping")
        return

    pitch = Pitch(
        pitch_type="statsbomb", pitch_color="white",
        line_color=PITCH_LINE_COLOR, linewidth=1.2,
    )
    fig, ax = pitch.draw(figsize=(11, 7))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(top=0.88, bottom=0.08)

    title = (
        f"FK vs {fk_row.opponent}  •  {fk_row.system}  "
        f"(man-fraction = {fk_row.man_frac:.0%}, engaged = {int(fk_row.n_engaged)})"
    )
    ax.set_title(title, fontsize=12.5, fontweight="bold", pad=10)
    fig.text(
        0.5, 0.91,
        f"{fk_row.date} • Barcelona in red, opponent in blue • shot frame at t = "
        f"−{SHOT_OFFSET_FRAMES / FPS:.1f} s, reception at t = 0",
        ha="center", fontsize=9.2, color="#444",
    )

    barca_scatter = ax.scatter([], [], s=110, c=BARCA_COLOR, edgecolors="white", linewidth=0.9, zorder=4)
    opp_scatter   = ax.scatter([], [], s=110, c=OPPONENT_COLOR, edgecolors="white", linewidth=0.9, zorder=3)
    ball_scatter  = ax.scatter([], [], s=55,  c=BALL_COLOR, edgecolors="white", linewidth=0.5, zorder=6)

    # Persistent line collection for tight pairings (drawn fresh each frame).
    pair_lines: list = []

    clock = ax.text(
        4, 76, "",
        ha="left", va="center", fontsize=12, fontweight="bold", color="#111",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white",
              "edgecolor": "#ccc", "alpha": 0.9},
        zorder=7,
    )
    moment = ax.text(
        116, 76, "",
        ha="right", va="center", fontsize=11, color="#666",
        zorder=7,
    )

    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BARCA_COLOR,
               markeredgecolor="white", markersize=8, label="Barcelona"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OPPONENT_COLOR,
               markeredgecolor="white", markersize=8, label="Opponent"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BALL_COLOR,
               markeredgecolor="white", markersize=6, label="Ball"),
        Line2D([0], [0], color=TIGHT_RING_COLOR, linewidth=1.4,
               label=f"Tight ≤ {MAN_THRESHOLD_M:.1f} m"),
    ]
    ax.legend(handles=handles, loc="lower center",
              bbox_to_anchor=(0.5, -0.06), ncol=len(handles), frameon=False)

    def update(frame: dict[str, Any]):
        # Remove previous tight-pair lines.
        nonlocal pair_lines
        for ln in pair_lines:
            ln.remove()
        pair_lines = []

        barca = [p for p in frame["players"] if p["team"] == "Barcelona"]
        opp   = [p for p in frame["players"] if p["team"] == "Opponent"]
        barca_scatter.set_offsets([[p["x"], p["y"]] for p in barca] or [[float("nan"), float("nan")]])
        opp_scatter.set_offsets([[p["x"], p["y"]]   for p in opp]   or [[float("nan"), float("nan")]])

        ball = frame.get("ball")
        if ball:
            ball_scatter.set_offsets([[ball["x"], ball["y"]]])
            ball_scatter.set_facecolors([BALL_COLOR if ball.get("tracked", True) else BALL_UNTRACKED_COLOR])
        else:
            ball_scatter.set_offsets([[float("nan"), float("nan")]])

        # Tight-pair lines (drawn in mpl coords).
        pairs = _per_frame_tight_pairs(frame["players"])
        if pairs:
            barca_by_id = {int(p["id"]): p for p in barca}
            opp_by_id   = {int(p["id"]): p for p in opp}
            for bid, attackers in pairs.items():
                b = barca_by_id.get(bid)
                if b is None:
                    continue
                for aid in attackers:
                    o = opp_by_id.get(aid)
                    if o is None:
                        continue
                    ln, = ax.plot(
                        [b["x"], o["x"]], [b["y"], o["y"]],
                        color=TIGHT_RING_COLOR, linewidth=1.2, alpha=0.65, zorder=2,
                    )
                    pair_lines.append(ln)

        clock.set_text(f"t {frame['t_rel']:+.1f} s")
        # Highlight the shot and reception moments.
        t = frame["t_rel"]
        if abs(t + SHOT_OFFSET_FRAMES / FPS) < 0.05:
            moment.set_text("● SHOT")
            moment.set_color(BARCA_COLOR)
        elif abs(t) < 0.05:
            moment.set_text("● RECEPTION")
            moment.set_color(OPPONENT_COLOR)
        else:
            moment.set_text("")

        return barca_scatter, opp_scatter, ball_scatter, clock, moment

    anim = FuncAnimation(fig, update, frames=frames, interval=1000 / FPS, blit=False, repeat=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    anim.save(out_path, writer=PillowWriter(fps=FPS))
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    print("Collecting SkillCorner FK marking rows…")
    per_fk, _, _ = collect_marking_rows()
    print(f"  {len(per_fk)} defensive FKs classified.")

    candidates = pick_candidates(per_fk)
    if candidates.empty:
        print("No candidates met the engagement floor.")
        return

    print("\nChosen examples:")
    for r in candidates.itertuples():
        print(f"  {r.system:14s}  {r.opponent:24s} {r.date}  "
              f"man-fraction={r.man_frac:5.0%}  engaged={int(r.n_engaged)}  recv={r.recv_frame}")

    # Group by match so we read each tracking file at most once.
    by_match: dict[int, list[pd.Series]] = defaultdict(list)
    for r in candidates.itertuples():
        by_match[int(r.match)].append(r)

    for sc_id, rows in by_match.items():
        print(f"\nExtracting tracking windows for match {sc_id} ({len(rows)} FK)…")
        windows = _extract_windows(sc_id, rows)
        for r in rows:
            frames = windows.get(r.recv_frame, [])
            system_tag = r.system.replace("-Marking", "").lower()
            out = ANIM_DIR / f"fk_{system_tag}_{sc_id}_{r.recv_frame}.gif"
            print(f"  rendering {out.name} ({len(frames)} frames)…")
            render(r, frames, out)

    print(f"\nAnimations written to: {ANIM_DIR}")


if __name__ == "__main__":
    main()
