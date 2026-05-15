"""Average Barcelona influence map at goal kicks.

This script reuses the spatial influence implementation from
``assets/pitch_control/spatial_inference.py`` / ``soccer_space.core``.

For every Barcelona goal-kick pass in StatsBomb, it:
  - maps the event time to the matching SkillCorner tracking frame,
  - computes per-player influence surfaces,
  - sums Barcelona player influence into a team influence map,
  - normalises all frames so Barcelona attacks left-to-right,
  - averages the maps separately for short and long goal kicks,
  - overlays dots at the StatsBomb pass end locations.

Run from the project root:
    python assets/pitch_control/barcelona_goal_kick_influence.py
"""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, Rectangle


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = next(
    p for p in [SCRIPT_DIR, *SCRIPT_DIR.parents]
    if (p / "pyproject.toml").is_file()
)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from soccer_space.core import PITCH_LEN, PITCH_WID, influence_grid, make_grid
from soccer_space.data import compute_velocity_buffer, load_match_meta


TEAM = "Barcelona"
VEL_HALF_WINDOW = 3
GRID_NX = 105
GRID_NY = 68
MAX_FRAME_TIME_DELTA = 0.15
SAMPLE_HZ = 10.0
VALID_FRAME_SEARCH_RADIUS = 100
SHORT_FROM_OWN_GOAL_LINE_M = 35.0

DATA_DIR = PROJECT_ROOT / "data"
STATSBOMB_DIR = DATA_DIR / "statsbomb"
SKILLCORNER_DIR = DATA_DIR / "skillcorner"
MATCHES_CSV = DATA_DIR / "matches.csv"
OUT_DIR = PROJECT_ROOT / "assets" / "pitch_control"
OUT_PATH = OUT_DIR / "barcelona_goal_kick_average_influence.png"


def _read_matches() -> list[dict[str, str]]:
    with MATCHES_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_statsbomb_events(match_id: str) -> list[dict[str, Any]] | None:
    target = f"{match_id}.json"
    for path in [
        STATSBOMB_DIR / target,
        *(STATSBOMB_DIR / phase / target for phase in (
            "league_phase", "last16", "playoffs", "quarterfinals"
        )),
    ]:
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return json.load(f)

    for zip_path in sorted(STATSBOMB_DIR.glob("*.zip")):
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.rsplit("/", 1)[-1] == target:
                    with zf.open(name) as f:
                        return json.load(f)
    return None


def _skillcorner_zip(skillcorner_id: str) -> Path | None:
    path = SKILLCORNER_DIR / f"{skillcorner_id}.zip"
    return path if path.exists() else None


def _raw_skillcorner_meta(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as zf:
        json_name = [
            name for name in zf.namelist()
            if name.endswith(".json") and "tracking" not in name
        ][0]
        with zf.open(json_name) as f:
            return json.load(f)


def _barca_team_id(raw_meta: dict[str, Any]) -> int | None:
    for key in ("home_team", "away_team"):
        team = raw_meta.get(key) or {}
        if TEAM in team.get("name", ""):
            return int(team["id"])
    return None


def _team_attacks_right(raw_meta: dict[str, Any], team_id: int, period: int) -> bool:
    home_team_id = int(raw_meta["home_team"]["id"])
    home_side = raw_meta["home_team_side"][period - 1]
    if team_id == home_team_id:
        return home_side == "left_to_right"
    return home_side == "right_to_left"


def _event_seconds(ev: dict[str, Any]) -> float:
    ts = ev.get("timestamp")
    if isinstance(ts, str) and ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(ev.get("minute", 0)) * 60 + float(ev.get("second", 0))


def _tracking_seconds(timestamp: str) -> float:
    hh, mm, ss = timestamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _is_barca_goal_kick(ev: dict[str, Any]) -> bool:
    return (
        ev.get("type", {}).get("id") == 30
        and ev.get("team", {}).get("name") == TEAM
        and ev.get("pass", {}).get("type", {}).get("name") == "Goal Kick"
    )


def _sb_to_metric_attack_right(x: float, y: float) -> tuple[float, float]:
    return (
        x / 120.0 * PITCH_LEN - PITCH_LEN / 2.0,
        y / 80.0 * PITCH_WID - PITCH_WID / 2.0,
    )


def _orient_xy(xy: np.ndarray, attack_right: bool) -> np.ndarray:
    out = np.asarray(xy, dtype=np.float64).copy()
    if not attack_right:
        out[..., 0] *= -1.0
    return out


def _goal_kick_length_group(ev: dict[str, Any]) -> str | None:
    end = ev.get("pass", {}).get("end_location")
    if not end or len(end) < 2:
        return None
    end_x, _ = _sb_to_metric_attack_right(float(end[0]), float(end[1]))
    distance_from_own_goal_line = end_x + PITCH_LEN / 2.0
    return "short" if distance_from_own_goal_line < SHORT_FROM_OWN_GOAL_LINE_M else "long"


def _frame_payload(frame: dict[str, Any]) -> tuple[dict[int, np.ndarray], dict[str, Any] | None]:
    player_data = frame.get("player_data") or []
    pos = {
        int(p["player_id"]): np.array([float(p["x"]), float(p["y"])], dtype=np.float64)
        for p in player_data
        if p.get("x") is not None and p.get("y") is not None
    }
    ball = frame.get("ball_data") or {}
    info = None
    if pos and ball.get("x") is not None and ball.get("y") is not None:
        info = {
            "period": int(frame.get("period")),
            "player_ids": np.array(list(pos.keys()), dtype=np.int64),
            "player_xy": np.stack(list(pos.values()), axis=0),
            "ball_xy": np.array([float(ball["x"]), float(ball["y"])], dtype=np.float64),
        }
    return pos, info


def _collect_needed_frames(
    zip_path: Path,
    targets: set[int],
    half_window: int,
) -> tuple[dict[int, dict[int, np.ndarray]], dict[int, dict[str, Any]], dict[int, int]]:
    needed = set()
    candidate_map: dict[int, list[int]] = {}
    for target in targets:
        candidates = [target]
        candidates.extend(
            frame
            for offset in range(1, VALID_FRAME_SEARCH_RADIUS + 1)
            for frame in (target - offset, target + offset)
        )
        candidate_map[target] = candidates
        for frame in candidates:
            for buffer_frame in range(frame - half_window, frame + half_window + 1):
                needed.add(buffer_frame)

    positions: dict[int, dict[int, np.ndarray]] = {}
    valid_frames: dict[int, dict[str, Any]] = {}

    with zipfile.ZipFile(zip_path) as zf:
        jsonl_name = [
            name for name in zf.namelist()
            if name.endswith("_tracking_extrapolated.jsonl")
        ][0]
        with zf.open(jsonl_name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                if not line.strip():
                    continue
                frame = json.loads(line)
                frame_id = int(frame["frame"])
                if frame_id not in needed:
                    continue

                pos, info = _frame_payload(frame)
                if not pos:
                    continue
                positions[frame_id] = pos
                if info is not None:
                    valid_frames[frame_id] = info

    resolved: dict[int, int] = {}
    target_frames: dict[int, dict[str, Any]] = {}
    for target, candidates in candidate_map.items():
        for frame in candidates:
            info = valid_frames.get(frame)
            if info is None:
                continue
            resolved[target] = frame
            target_frames[target] = info
            break

    return positions, target_frames, resolved


def _match_goal_kicks_to_tracking_frames(
    zip_path: Path,
    goal_kicks: list[dict[str, Any]],
    period_starts: dict[int, int],
) -> tuple[dict[int, list[dict[str, Any]]], int]:
    """Return {tracking_frame: [goal-kick events]}.

    The primary mapping uses the pitch-control package convention:
    period_start + round(event_seconds * 10). Timestamp-nearest matching is
    kept as a fallback for packages where the computed frame is unavailable.
    """
    targets = []
    for ev in goal_kicks:
        period = int(ev.get("period"))
        time = _event_seconds(ev)
        start = period_starts.get(period)
        targets.append({
            "event": ev,
            "period": period,
            "time": time,
            "formula_frame": None if start is None else start + int(round(time * SAMPLE_HZ)),
            "best_frame": None,
            "best_delta": float("inf"),
        })

    available_frames: set[int] = set()
    with zipfile.ZipFile(zip_path) as zf:
        jsonl_name = [
            name for name in zf.namelist()
            if name.endswith("_tracking_extrapolated.jsonl")
        ][0]
        with zf.open(jsonl_name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                if not line.strip():
                    continue
                frame = json.loads(line)
                period = frame.get("period")
                timestamp = frame.get("timestamp")
                frame_id = int(frame["frame"])
                available_frames.add(frame_id)
                if period is None or timestamp is None:
                    continue
                t = _tracking_seconds(timestamp)
                for target in targets:
                    if int(period) != target["period"]:
                        continue
                    delta = abs(t - target["time"])
                    if delta < target["best_delta"]:
                        target["best_delta"] = delta
                        target["best_frame"] = int(frame["frame"])

    by_frame: dict[int, list[dict[str, Any]]] = {}
    skipped = 0
    for target in targets:
        formula_frame = target["formula_frame"]
        if formula_frame in available_frames:
            frame = int(formula_frame)
        elif target["best_frame"] is not None and (
            formula_frame is None or target["best_delta"] <= MAX_FRAME_TIME_DELTA
        ):
            frame = int(target["best_frame"])
        else:
            skipped += 1
            continue
        by_frame.setdefault(frame, []).append(target["event"])
    return by_frame, skipped


def _iter_goal_kick_groups() -> Iterable[tuple[dict[str, str], list[dict[str, Any]]]]:
    for row in _read_matches():
        if TEAM not in (row.get("home", ""), row.get("away", "")):
            continue
        match_id = (row.get("statsbomb") or "").strip()
        skillcorner_id = (row.get("skillcorner") or "").strip()
        if not match_id or not skillcorner_id:
            continue
        events = _load_statsbomb_events(match_id)
        if events is None:
            continue
        goal_kicks = [ev for ev in events if _is_barca_goal_kick(ev)]
        if goal_kicks:
            yield row, goal_kicks


def _draw_pitch(ax: plt.Axes) -> None:
    line = "#232323"
    lw = 1.0
    ax.add_patch(Rectangle((-PITCH_LEN / 2, -PITCH_WID / 2), PITCH_LEN, PITCH_WID,
                           fill=False, edgecolor=line, linewidth=lw, zorder=4))
    ax.plot([0, 0], [-PITCH_WID / 2, PITCH_WID / 2], color=line, lw=lw, zorder=4)
    ax.add_patch(plt.Circle((0, 0), 9.15, fill=False, edgecolor=line, lw=lw, zorder=4))
    for sign in (-1, 1):
        goal_x = sign * PITCH_LEN / 2
        box_x = goal_x - sign * 16.5
        six_x = goal_x - sign * 5.5
        ax.add_patch(Rectangle((min(goal_x, box_x), -20.16), 16.5, 40.32,
                               fill=False, edgecolor=line, linewidth=lw, zorder=4))
        ax.add_patch(Rectangle((min(goal_x, six_x), -9.16), 5.5, 18.32,
                               fill=False, edgecolor=line, linewidth=lw, zorder=4))
        ax.scatter([goal_x - sign * 11.0], [0], s=8, c=line, zorder=4)
        arc_x = goal_x - sign * 11.0
        theta1, theta2 = (310, 50) if sign < 0 else (130, 230)
        ax.add_patch(Arc((arc_x, 0), 18.3, 18.3, theta1=theta1, theta2=theta2,
                         edgecolor=line, lw=lw, zorder=4))


def build_average_maps() -> tuple[
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    dict[str, int],
    int,
]:
    grid_xy = make_grid(GRID_NX, GRID_NY, PITCH_LEN, PITCH_WID)
    influence_sums = {
        "short": np.zeros((GRID_NY, GRID_NX), dtype=np.float64),
        "long": np.zeros((GRID_NY, GRID_NX), dtype=np.float64),
    }
    endpoints: dict[str, list[tuple[float, float]]] = {"short": [], "long": []}
    used = {"short": 0, "long": 0}
    skipped = 0

    for row, goal_kicks in _iter_goal_kick_groups():
        skillcorner_id = (row.get("skillcorner") or "").strip()
        zip_path = _skillcorner_zip(skillcorner_id)
        if zip_path is None:
            skipped += len(goal_kicks)
            continue

        sc_meta = load_match_meta(zip_path)
        raw_meta = _raw_skillcorner_meta(zip_path)
        barca_team_id = _barca_team_id(raw_meta)
        if barca_team_id is None:
            skipped += len(goal_kicks)
            continue

        target_by_frame, skipped_for_match = _match_goal_kicks_to_tracking_frames(
            zip_path,
            goal_kicks,
            sc_meta.period_starts,
        )
        skipped += skipped_for_match
        if not target_by_frame:
            continue

        positions, frames, resolved_frames = _collect_needed_frames(
            zip_path,
            set(target_by_frame),
            VEL_HALF_WINDOW,
        )
        velocities_by_frame = {
            target: compute_velocity_buffer(positions, resolved, VEL_HALF_WINDOW)
            for target, resolved in resolved_frames.items()
        }

        for frame, events in target_by_frame.items():
            info = frames.get(frame)
            if info is None:
                skipped += len(events)
                continue

            attack_right = _team_attacks_right(raw_meta, barca_team_id, int(info["period"]))
            player_ids = info["player_ids"]
            player_xy = _orient_xy(info["player_xy"], attack_right)
            ball_xy = _orient_xy(info["ball_xy"], attack_right)
            vel_map = velocities_by_frame.get(frame, {})
            velocities = np.stack([
                _orient_xy(vel_map.get(int(pid), np.zeros(2, dtype=np.float64)), attack_right)
                for pid in player_ids
            ], axis=0)

            team_ids = np.array([sc_meta.player_team.get(int(pid), -1) for pid in player_ids])
            barca_mask = team_ids == barca_team_id
            if not np.any(barca_mask):
                skipped += len(events)
                continue

            influence = influence_grid(grid_xy, player_xy, velocities, ball_xy)
            team_influence = influence[barca_mask].sum(axis=0)

            for ev in events:
                group = _goal_kick_length_group(ev)
                if group is None:
                    skipped += 1
                    continue
                influence_sums[group] += team_influence
                used[group] += 1

                end = ev.get("pass", {}).get("end_location")
                if end and len(end) >= 2:
                    end_x, end_y = _sb_to_metric_attack_right(float(end[0]), float(end[1]))
                    if -PITCH_LEN / 2 <= end_x <= PITCH_LEN / 2 and -PITCH_WID / 2 <= end_y <= PITCH_WID / 2:
                        endpoints[group].append((end_x, end_y))

    if not any(used.values()):
        raise RuntimeError("No Barcelona goal-kick tracking frames could be matched.")

    average_maps = {}
    endpoint_arrays = {}
    for group in ("short", "long"):
        if used[group]:
            average_maps[group] = influence_sums[group] / used[group]
        else:
            average_maps[group] = np.full((GRID_NY, GRID_NX), np.nan, dtype=np.float64)
        endpoint_arrays[group] = np.array(endpoints[group], dtype=np.float64)
    return average_maps, endpoint_arrays, used, skipped


def render() -> Path:
    average_maps, endpoints, used, skipped = build_average_maps()
    grid_xy = make_grid(GRID_NX, GRID_NY, PITCH_LEN, PITCH_WID)
    xs = grid_xy[0, :, 0]
    ys = grid_xy[:, 0, 1]

    fig, axes = plt.subplots(1, 2, figsize=(19.5, 7.8), sharex=True, sharey=True)
    fig.patch.set_facecolor("white")

    finite_values = np.concatenate([
        average_maps[group][np.isfinite(average_maps[group])]
        for group in ("short", "long")
        if np.isfinite(average_maps[group]).any()
    ])
    vmax = max(0.01, float(np.nanmax(finite_values))) if finite_values.size else 0.01
    levels = np.linspace(0, vmax, 24)
    contour = None

    panel_meta = [
        ("short", "Short goal kicks", "#ef233c"),
        ("long", "Long goal kicks", "#ff9f1c"),
    ]
    for ax, (group, title, dot_color) in zip(axes, panel_meta):
        ax.set_facecolor("white")
        contour = ax.contourf(
            xs,
            ys,
            average_maps[group],
            levels=levels,
            cmap="viridis",
            alpha=0.88,
            zorder=1,
        )
        _draw_pitch(ax)
        pts = endpoints[group]
        if pts.size:
            ax.scatter(
                pts[:, 0], pts[:, 1],
                s=38,
                c=dot_color,
                edgecolors="white",
                linewidths=0.7,
                alpha=0.86,
                zorder=5,
                label=f"End location (n={len(pts)})",
            )
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.08), frameon=False, fontsize=9)

        ax.annotate("Barcelona attack ->", xy=(28, 31), xytext=(-28, 31),
                    arrowprops=dict(arrowstyle="->", lw=1.2, color="#111111"),
                    ha="center", va="center", fontsize=9, color="#111111")
        ax.set_title(f"{title} (n={used[group]})", fontsize=12, fontweight="bold", pad=8)
        ax.set_xlim(-PITCH_LEN / 2 - 2, PITCH_LEN / 2 + 2)
        ax.set_ylim(-PITCH_WID / 2 - 2, PITCH_WID / 2 + 2)
        ax.set_aspect("equal")
        ax.set_xlabel("Pitch x (m, Barcelona attack left-to-right)")

    axes[0].set_ylabel("Pitch y (m)")
    cbar = fig.colorbar(contour, ax=axes, fraction=0.028, pad=0.015)
    cbar.set_label("Average Barcelona team influence", fontsize=10)
    cbar.ax.tick_params(labelsize=8)

    fig.suptitle(
        "Barcelona Goal Kicks: Average Influence at Restart by Landing Zone "
        f"(short < {SHORT_FROM_OWN_GOAL_LINE_M:g}m from own goal line, skipped={skipped})",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )
    fig.subplots_adjust(left=0.04, right=0.91, bottom=0.12, top=0.9, wspace=0.04)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved -> {OUT_PATH}")
    return OUT_PATH


if __name__ == "__main__":
    render()
