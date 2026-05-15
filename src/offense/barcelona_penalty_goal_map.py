"""Barcelona offensive penalty goal map — one panel per taker, with shot speed.

For each Barcelona player that took a penalty:
  • One panel on the goal frame showing all their shots
    (circle = goal, X = saved / off-target)
  • Each shot annotated with estimated ball speed in km/h
    – Derived from SkillCorner ball tracking when available:
      t_kick = first frame ball moves > 1 m from penalty spot
      t_arrive = first frame ball reaches goal line (x ≥ 118 SB units)
      speed = distance(spot → end_location) / (t_arrive − t_kick)
    – If no SkillCorner file exists for the match the speed label is omitted.

Output
------
  assets/offense/penalties/barca_penalty_goal_map_per_player.png
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())

import sys
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import POSITIVE_COLOR, NEUTRAL_COLOR, apply_theme, save_fig

ASSETS_DIR = PROJECT_ROOT / "assets" / "offense" / "penalties"
DATA = PROJECT_ROOT / "data" / "statsbomb"
SKILLCORNER_ROOT = PROJECT_ROOT / "data" / "skillcorner"
TEAM = "Barcelona"

# Goal frame (StatsBomb shot end_location coords)
GOAL_Y_MIN = 36.0
GOAL_Y_MAX = 44.0
GOAL_HEIGHT = 2.67
GOAL_CENTRE = (GOAL_Y_MIN + GOAL_Y_MAX) / 2

# StatsBomb pitch unit → metres (105 m × 68 m mapped to 120 × 80 units)
SB_X_TO_M = 105.0 / 120.0
SB_Y_TO_M = 68.0 / 80.0
SB_Z_TO_M = 0.9144          # height uses actual yards → metres

PENALTY_SPOT_X = 108.0      # 12 yards from goal in SB coords
PENALTY_SPOT_Y = 40.0

# Speed-estimation window around the StatsBomb event timestamp
# NOTE: StatsBomb logs the shot event ~4-5 s before the actual kick in
# SkillCorner time, so the post-window must be large enough to catch it.
SPEED_WINDOW_PRE = 2.0      # seconds before event to start scanning
SPEED_WINDOW_POST = 12.0    # seconds after (StatsBomb–SC offset can be ~5 s)
KICK_VEL_THRESH_MS = 6.5    # m/s — velocity threshold to identify actual kick.
                              # Must be above typical pre-kick drift velocities (~6 m/s)
                              # but low enough to catch tracking-smoothed kicks (~7 m/s).

GOAL_COLOR = POSITIVE_COLOR
SAVED_COLOR = "#e6821e"
MISSED_COLOR = NEUTRAL_COLOR
DIVE_LATERAL_THRESHOLD_SB = 0.55
DIVE_LATERAL_SPEED_THRESHOLD_SB = 2.2
DIVE_SCAN_PRE = 0.45
DIVE_SCAN_POST = 1.20


# ── data structures ──────────────────────────────────────────────────

@dataclass
class PenaltyShot:
    player: str
    outcome: str        # "Goal" | "Saved" | "Other"
    end_x: float        # shot.end_location[0]
    end_y: float        # shot.end_location[1]  (goal-frame y)
    end_z: float        # shot.end_location[2]  (goal-frame z)
    minute: int
    second: int
    period: int
    speed_kmh: float | None = None
    keeper_dive_direction: str | None = None
    keeper_dive_t_rel: float | None = None


# ── SkillCorner helpers ──────────────────────────────────────────────

def _parse_ts(ts: str) -> float:
    hh, mm, ss = ts.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _load_sc_meta(zip_path: Path, match_id: str) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}.json") as fh:
            return json.load(io.TextIOWrapper(fh, encoding="utf-8"))


def _barca_team_id(meta: dict) -> int:
    if "Barcelona" in meta["home_team"]["name"]:
        return int(meta["home_team"]["id"])
    return int(meta["away_team"]["id"])


def _opponent_team_id(meta: dict) -> int:
    home_id = int(meta["home_team"]["id"])
    away_id = int(meta["away_team"]["id"])
    barca_id = _barca_team_id(meta)
    return away_id if barca_id == home_id else home_id


def _player_index(meta: dict) -> dict[int, dict[str, Any]]:
    players: dict[int, dict[str, Any]] = {}
    for player in meta.get("players", []):
        pid = player.get("id") or player.get("player_id")
        if pid is None:
            continue
        role = player.get("player_role", {}) or {}
        players[int(pid)] = {
            "team_id": int(player["team_id"]),
            "is_goalkeeper": role.get("name") == "Goalkeeper" or role.get("acronym") == "GK",
        }
    return players


def _attack_right(meta: dict, team_id: int, period: int) -> bool:
    sides = meta.get("home_team_side", [])
    home_id = int(meta["home_team"]["id"])
    idx = min(period - 1, len(sides) - 1)
    home_dir = sides[idx] if sides else "left_to_right"
    if team_id == home_id:
        return home_dir == "left_to_right"
    return home_dir == "right_to_left"


def _sc_to_sb(x: float, y: float, *, length: float, width: float, right: bool) -> tuple[float, float]:
    if not right:
        x = -x
    return (x + length / 2) / length * 120.0, (y + width / 2) / width * 80.0


def _estimate_speed(zip_path: Path, match_id: str, shot: PenaltyShot) -> float | None:
    """Estimate ball speed from SkillCorner tracking. Returns km/h or None.

    Strategy: StatsBomb can log the shot event several seconds before the
    actual kick happens in SkillCorner time.  We therefore:
      1. Use a wide post-event window (SPEED_WINDOW_POST).
      2. Detect the kick by a sudden velocity spike (> KICK_VEL_THRESH_MS)
         rather than displacement from the spot (which picks up slow drift).
      3. Find when the ball reaches the goal-line area in raw SC coords.
      4. Compute speed from StatsBomb 3D end_location distance / flight time.
    """
    try:
        meta = _load_sc_meta(zip_path, match_id)
    except Exception:
        return None

    barca_id = _barca_team_id(meta)
    right = _attack_right(meta, barca_id, shot.period)
    length = float(meta["pitch_length"])
    width = float(meta["pitch_width"])

    # Goal line in raw SkillCorner coords (metres from centre)
    goal_x_sc = (length / 2.0 - 0.5) if right else -(length / 2.0 - 0.5)

    t_event = shot.minute * 60 + shot.second
    t_lo = t_event - SPEED_WINDOW_PRE
    t_hi = t_event + SPEED_WINDOW_POST

    # Collect (t, x_raw_sc, y_raw_sc) in window — raw SC metres for velocity
    samples: list[tuple[float, float, float]] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            fname = f"{match_id}_tracking_extrapolated.jsonl"
            if fname not in zf.namelist():
                return None
            with zf.open(fname) as fh:
                for raw in io.TextIOWrapper(fh, encoding="utf-8"):
                    frame = json.loads(raw)
                    if frame.get("period") != shot.period:
                        continue
                    ts = frame.get("timestamp")
                    if ts is None:
                        continue
                    t = _parse_ts(ts)
                    if t > t_hi:
                        break
                    if t < t_lo:
                        continue
                    ball = frame.get("ball_data") or {}
                    bx, by = _safe_float(ball.get("x")), _safe_float(ball.get("y"))
                    if bx is None or by is None:
                        continue
                    samples.append((t, bx, by))
    except Exception:
        return None

    if len(samples) < 4:
        return None

    samples.sort(key=lambda s: s[0])

    # Find t_kick: first frame where frame-to-frame velocity > threshold.
    # This skips slow pre-kick drift and picks up the actual kick.
    t_kick: float | None = None
    for i in range(1, len(samples)):
        t0, x0, y0 = samples[i - 1]
        t1, x1, y1 = samples[i]
        dt = t1 - t0
        if dt <= 0:
            continue
        v = math.hypot(x1 - x0, y1 - y0) / dt  # m/s in raw SC coords
        if v > KICK_VEL_THRESH_MS:
            t_kick = t1
            break

    if t_kick is None:
        return None

    # Find t_arrive: first frame after kick where ball reaches goal-line area
    t_arrive: float | None = None
    x_kick, y_kick = None, None
    for t, x, y in samples:
        if t == t_kick:
            x_kick, y_kick = x, y
        if t <= t_kick:
            continue
        reached = (x >= goal_x_sc) if right else (x <= goal_x_sc)
        if reached:
            t_arrive = t
            break

    if t_arrive is None or x_kick is None:
        return None

    dt = t_arrive - t_kick
    if dt < 0.05:
        return None

    # Use StatsBomb end_location for the 3D flight distance (includes height)
    dx = (shot.end_x - PENALTY_SPOT_X) * SB_X_TO_M
    dy = (shot.end_y - PENALTY_SPOT_Y) * SB_Y_TO_M
    dz = shot.end_z * SB_Z_TO_M
    dist_m = math.sqrt(dx * dx + dy * dy + dz * dz)

    speed = dist_m / dt * 3.6  # km/h
    return round(speed, 1) if 20.0 <= speed <= 200.0 else None


def _detect_keeper_dive(
    keeper_samples: list[tuple[float, float, float]],
    *,
    kick_time: float,
) -> tuple[str | None, float | None]:
    """Return keeper dive direction and first dive time relative to the kick."""
    if len(keeper_samples) < 3:
        return None, None

    keeper_samples = sorted(keeper_samples, key=lambda sample: sample[0])
    pre = [sample for sample in keeper_samples if kick_time - DIVE_SCAN_PRE <= sample[0] <= kick_time]
    if not pre:
        pre = [min(keeper_samples, key=lambda sample: abs(sample[0] - kick_time))]
    baseline_y = sum(sample[2] for sample in pre) / len(pre)

    previous: tuple[float, float, float] | None = None
    for sample in keeper_samples:
        t, _x, y = sample
        if t < kick_time - DIVE_SCAN_PRE or t > kick_time + DIVE_SCAN_POST:
            continue
        lateral = y - baseline_y
        lateral_speed = 0.0
        if previous is not None:
            prev_t, _prev_x, prev_y = previous
            dt = t - prev_t
            if dt > 0:
                lateral_speed = (y - prev_y) / dt
        previous = sample
        if t < kick_time:
            continue
        if abs(lateral) >= DIVE_LATERAL_THRESHOLD_SB or abs(lateral_speed) >= DIVE_LATERAL_SPEED_THRESHOLD_SB:
            return ("R" if lateral > 0 or lateral_speed > 0 else "L"), round(t - kick_time, 2)

    post = [sample for sample in keeper_samples if kick_time <= sample[0] <= kick_time + DIVE_SCAN_POST]
    if not post:
        return None, None
    final_lateral = post[-1][2] - baseline_y
    if abs(final_lateral) < 0.35:
        return "C", None
    return ("R" if final_lateral > 0 else "L"), None


def _tracking_metrics(zip_path: Path, match_id: str, shot: PenaltyShot) -> tuple[float | None, str | None, float | None]:
    """Estimate ball speed plus keeper dive direction/timing from SkillCorner."""
    try:
        meta = _load_sc_meta(zip_path, match_id)
    except Exception:
        return None, None, None

    barca_id = _barca_team_id(meta)
    opponent_id = _opponent_team_id(meta)
    players = _player_index(meta)
    right = _attack_right(meta, barca_id, shot.period)
    length = float(meta["pitch_length"])
    width = float(meta["pitch_width"])
    goal_x_sc = (length / 2.0 - 0.5) if right else -(length / 2.0 - 0.5)

    t_event = shot.minute * 60 + shot.second
    t_lo = t_event - SPEED_WINDOW_PRE
    t_hi = t_event + SPEED_WINDOW_POST

    ball_samples: list[tuple[float, float, float]] = []
    keeper_samples: list[tuple[float, float, float]] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            fname = f"{match_id}_tracking_extrapolated.jsonl"
            if fname not in zf.namelist():
                return None, None, None
            with zf.open(fname) as fh:
                for raw in io.TextIOWrapper(fh, encoding="utf-8"):
                    frame = json.loads(raw)
                    if frame.get("period") != shot.period:
                        continue
                    ts = frame.get("timestamp")
                    if ts is None:
                        continue
                    t = _parse_ts(ts)
                    if t > t_hi:
                        break
                    if t < t_lo:
                        continue

                    ball = frame.get("ball_data") or {}
                    bx, by = _safe_float(ball.get("x")), _safe_float(ball.get("y"))
                    if bx is not None and by is not None:
                        ball_samples.append((t, bx, by))

                    for player in frame.get("player_data", []):
                        pid = player.get("player_id")
                        if pid is None:
                            continue
                        info = players.get(int(pid))
                        if not info or info["team_id"] != opponent_id or not info["is_goalkeeper"]:
                            continue
                        px, py = _safe_float(player.get("x")), _safe_float(player.get("y"))
                        if px is None or py is None:
                            continue
                        sx, sy = _sc_to_sb(px, py, length=length, width=width, right=right)
                        keeper_samples.append((t, sx, sy))
    except Exception:
        return None, None, None

    if len(ball_samples) < 4:
        return None, None, None

    ball_samples.sort(key=lambda sample: sample[0])
    t_kick: float | None = None
    for i in range(1, len(ball_samples)):
        t0, x0, y0 = ball_samples[i - 1]
        t1, x1, y1 = ball_samples[i]
        dt = t1 - t0
        if dt <= 0:
            continue
        if math.hypot(x1 - x0, y1 - y0) / dt > KICK_VEL_THRESH_MS:
            t_kick = t1
            break

    if t_kick is None:
        return None, None, None

    t_arrive: float | None = None
    for t, x, _y in ball_samples:
        if t <= t_kick:
            continue
        reached = (x >= goal_x_sc) if right else (x <= goal_x_sc)
        if reached:
            t_arrive = t
            break

    speed_kmh: float | None = None
    if t_arrive is not None:
        dt = t_arrive - t_kick
        if dt >= 0.05:
            dx = (shot.end_x - PENALTY_SPOT_X) * SB_X_TO_M
            dy = (shot.end_y - PENALTY_SPOT_Y) * SB_Y_TO_M
            dz = shot.end_z * SB_Z_TO_M
            dist_m = math.sqrt(dx * dx + dy * dy + dz * dz)
            speed = dist_m / dt * 3.6
            if 20.0 <= speed <= 200.0:
                speed_kmh = round(speed, 1)

    dive_direction, dive_t_rel = _detect_keeper_dive(keeper_samples, kick_time=t_kick)
    return speed_kmh, dive_direction, dive_t_rel


# ── StatsBomb collection ─────────────────────────────────────────────

def _outcome(e: dict) -> str:
    if f.is_goal(e):
        return "Goal"
    if "Saved" in f.shot_outcome(e):
        return "Saved"
    return "Other"


def _has_3d_end(e: dict) -> bool:
    end = e.get("shot", {}).get("end_location")
    return bool(end and len(end) >= 3)


def _collect(data_dir: Path) -> list[PenaltyShot]:
    shots: list[PenaltyShot] = []

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(TEAM, row, events)
        sc_id = row.get("skillcorner", "").strip() or None

        barca_pens = [
            e for e in events
            if f.is_penalty_shot(e) and _has_3d_end(e)
            and sb_name and f.by_team(e, sb_name)
        ]
        if not barca_pens:
            continue

        zip_path: Path | None = None
        if sc_id:
            candidate = SKILLCORNER_ROOT / f"{sc_id}.zip"
            if candidate.is_file():
                zip_path = candidate

        for e in barca_pens:
            end = e["shot"]["end_location"]
            shot = PenaltyShot(
                player=f.event_player(e),
                outcome=_outcome(e),
                end_x=float(end[0]),
                end_y=float(end[1]),
                end_z=float(end[2]),
                minute=int(e.get("minute", 0)),
                second=int(e.get("second", 0)),
                period=int(e.get("period", 1)),
            )
            if zip_path and sc_id:
                (
                    shot.speed_kmh,
                    shot.keeper_dive_direction,
                    shot.keeper_dive_t_rel,
                ) = _tracking_metrics(zip_path, sc_id, shot)
            shots.append(shot)

    return shots


# ── goal frame drawing ───────────────────────────────────────────────

def _draw_goal_frame(ax: plt.Axes) -> None:
    ax.fill_between([GOAL_Y_MIN, GOAL_Y_MAX], 0, GOAL_HEIGHT, color="#ececec", zorder=0)
    ax.fill_between([GOAL_Y_MIN - 1.2, GOAL_Y_MAX + 1.2], -0.40, 0,
                    color="#9ecf82", zorder=0, alpha=0.8)
    for frac in (1/3, 2/3):
        xv = GOAL_Y_MIN + frac * (GOAL_Y_MAX - GOAL_Y_MIN)
        ax.plot([xv, xv], [0, GOAL_HEIGHT], color="#cccccc", lw=0.6, ls="--", zorder=1)
    ax.plot([GOAL_Y_MIN, GOAL_Y_MAX], [GOAL_HEIGHT / 2, GOAL_HEIGHT / 2],
            color="#cccccc", lw=0.6, ls="--", zorder=1)
    ax.plot(
        [GOAL_Y_MIN, GOAL_Y_MIN, GOAL_Y_MAX, GOAL_Y_MAX],
        [0, GOAL_HEIGHT, GOAL_HEIGHT, 0],
        color="#222222", lw=3.5, zorder=3, solid_capstyle="round",
    )
    ax.set_xlim(GOAL_Y_MIN - 1.2, GOAL_Y_MAX + 1.2)
    ax.set_ylim(-0.40, GOAL_HEIGHT + 0.65)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7.5)
    ax.set_xticks([GOAL_Y_MIN, GOAL_CENTRE, GOAL_Y_MAX])
    ax.set_xticklabels(["L", "C", "R"], fontsize=7.5)
    ax.set_yticks([0, GOAL_HEIGHT / 2, GOAL_HEIGHT])
    ax.set_yticklabels(["0", f"{GOAL_HEIGHT/2:.1f}", f"{GOAL_HEIGHT:.2f}"], fontsize=7.5)


# ── figure ───────────────────────────────────────────────────────────

def _color(outcome: str) -> str:
    return {"Goal": GOAL_COLOR, "Saved": SAVED_COLOR, "Other": MISSED_COLOR}[outcome]


def _marker(outcome: str) -> str:
    return "o" if outcome == "Goal" else "X"


def _keeper_dive_text(direction: str | None, timing: float | None) -> str | None:
    if direction is None:
        return None
    direction_text = {
        "L": "taker's left",
        "R": "taker's right",
        "C": "centre",
    }.get(direction, direction)
    if timing is None:
        return f"Keeper: {direction_text}"
    when = "after kick" if timing >= 0 else "before kick"
    return f"Keeper: {direction_text}\n{abs(timing):.2f}s {when}"


def _draw_keeper_dive_hint(ax: plt.Axes, shot: PenaltyShot) -> None:
    if shot.keeper_dive_direction not in {"L", "R"}:
        return
    direction = -1 if shot.keeper_dive_direction == "L" else 1
    start_y = max(GOAL_Y_MIN + 0.4, min(GOAL_Y_MAX - 0.4, shot.end_y))
    end_y = max(GOAL_Y_MIN + 0.15, min(GOAL_Y_MAX - 0.15, start_y + direction * 0.8))
    y_base = -0.22
    ax.annotate(
        "",
        xy=(end_y, y_base),
        xytext=(start_y, y_base),
        arrowprops={"arrowstyle": "-|>", "color": "#333333", "lw": 1.0, "alpha": 0.85},
        zorder=6,
    )


def _build_figure(shots_by_player: dict[str, list[PenaltyShot]]) -> plt.Figure:
    players = sorted(shots_by_player, key=lambda p: len(shots_by_player[p]), reverse=True)
    n = len(players)
    ncols = min(n, 3)
    nrows = math.ceil(n / ncols)

    fig = plt.figure(figsize=(ncols * 4.0, nrows * 3.8 + 1.2))
    gs = gridspec.GridSpec(
        nrows, ncols, figure=fig,
        top=0.88, bottom=0.10, left=0.06, right=0.97,
        hspace=0.55, wspace=0.40,
    )

    any_speed = any(s.speed_kmh is not None for pl in shots_by_player.values() for s in pl)
    any_dive = any(s.keeper_dive_direction is not None for pl in shots_by_player.values() for s in pl)

    for idx, player in enumerate(players):
        ax = fig.add_subplot(gs[idx // ncols, idx % ncols])
        _draw_goal_frame(ax)

        pshots = shots_by_player[player]
        n_g = sum(1 for s in pshots if s.outcome == "Goal")

        for shot in pshots:
            ax.scatter(
                shot.end_y, shot.end_z,
                s=150 if shot.outcome == "Goal" else 110,
                marker=_marker(shot.outcome),
                color=_color(shot.outcome),
                edgecolors="white" if shot.outcome == "Goal" else _color(shot.outcome),
                linewidth=0.8, zorder=4, alpha=0.93,
            )
            if shot.speed_kmh is not None:
                ax.text(
                    shot.end_y, shot.end_z + 0.13,
                    f"{shot.speed_kmh:.0f}",
                    ha="center", va="bottom", fontsize=6.5,
                    color="#111111", fontweight="bold", zorder=5,
                )
            if shot.keeper_dive_direction is not None:
                _draw_keeper_dive_hint(ax, shot)
                dive_text = _keeper_dive_text(shot.keeper_dive_direction, shot.keeper_dive_t_rel)
                ax.text(
                    shot.end_y,
                    shot.end_z - 0.18,
                    dive_text,
                    ha="center",
                    va="top",
                    fontsize=5.6,
                    color="#333333",
                    fontweight="bold",
                    zorder=5,
                )

        ax.set_title(
            f"{player}  ·  {len(pshots)} pen  ·  {n_g} G",
            fontsize=9, fontweight="bold", pad=5,
        )

    for idx in range(n, nrows * ncols):
        fig.add_subplot(gs[idx // ncols, idx % ncols]).axis("off")

    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=GOAL_COLOR,
               markersize=8, label="Goal"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=SAVED_COLOR,
               markeredgecolor=SAVED_COLOR, markersize=8, label="Saved"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor=MISSED_COLOR,
               markeredgecolor=MISSED_COLOR, markersize=8, label="Off target"),
    ]
    if any_speed:
        legend_handles.append(
            Line2D([0], [0], color="none", label="Numbers = shot speed (km/h)")
        )
    if any_dive:
        legend_handles.append(
            Line2D([0], [0], color="none", label="Keeper labels use the taker's view; timing is relative to the kick")
        )

    fig.legend(handles=legend_handles, loc="lower center", ncol=len(legend_handles),
               fontsize=8, frameon=True, framealpha=0.88, bbox_to_anchor=(0.5, 0.01))

    fig.text(0.5, 0.97,
             "Barcelona penalty takers — goal-face locations, shot speed & keeper dive",
             ha="center", va="top", fontsize=14, fontweight="bold", color="#111111")
    subtitle = (
        "One panel per taker  ·  circle = goal, X = saved / off target"
        + ("  ·  numbers = estimated speed from SkillCorner tracking (km/h)" if any_speed else "")
        + ("  ·  keeper direction is from the taker's point of view; timing says before/after kick" if any_dive else "")
    )
    fig.text(0.5, 0.93, subtitle, ha="center", va="top", fontsize=8.5, color="#555555")

    return fig


# ── entry point ──────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_DIR) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting Barcelona penalties ...")
    shots = _collect(data_dir)

    if not shots:
        print("No Barcelona penalties with 3D end locations found.")
        return

    print(f"  {len(shots)} penalties total")
    for s in shots:
        spd = f"{s.speed_kmh} km/h" if s.speed_kmh is not None else "no speed data"
        dive = (
            f"GK {s.keeper_dive_direction} "
            f"{s.keeper_dive_t_rel:+.2f}s"
            if s.keeper_dive_direction is not None and s.keeper_dive_t_rel is not None
            else f"GK {s.keeper_dive_direction or 'n/a'}"
        )
        print(f"    {s.player:<32s} {s.outcome:<7s} {spd:<14s} {dive}")

    shots_by_player: dict[str, list[PenaltyShot]] = defaultdict(list)
    for s in shots:
        shots_by_player[s.player].append(s)

    print(f"\n  Takers: {list(shots_by_player)}")
    print("Building figure ...")
    fig = _build_figure(dict(shots_by_player))

    out = output_dir / "barca_penalty_goal_map_per_player.png"
    save_fig(fig, out, tight=False)
    print(f"  Saved: {out.relative_to(PROJECT_ROOT)}")
    print("Done.")


if __name__ == "__main__":
    run()
