"""Barcelona offensive corner run-path analysis from SkillCorner tracking.

This script combines:
- ``data/matches.csv`` for StatsBomb <-> SkillCorner match mapping
- StatsBomb event JSON to identify Barcelona attacking corners
- SkillCorner tracking to reconstruct player movement around the corner kick
- SkillCorner dynamic events to add tagged off-ball runs when available

Outputs are written to ``assets/offensive_corner_runs_skillcorner/``.
"""

from __future__ import annotations

import csv
import io
import json
import math
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mplsoccer import Pitch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"

import sys

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.viz.style import FOCUS_COLOR, NEUTRAL_COLOR, apply_theme, save_fig

ASSETS_ROOT = PROJECT_ROOT / "assets" / "offensive_corner_runs_skillcorner"
MATCHES_CSV = PROJECT_ROOT / "data" / "matches.csv"
STATSBOMB_ROOT = PROJECT_ROOT / "data" / "statsbomb" / "league_phase"
SKILLCORNER_ROOT = PROJECT_ROOT / "data" / "skillcorner"

TEAM = "Barcelona"
PRE_SECONDS = 2.5
POST_SECONDS = 2.5
INTEREST_X_THRESHOLD = 72.0
MEAN_PATH_SAMPLES = 18

RUN_SUBTYPE_COLORS = {
    "cross_receiver": "#d73027",
    "coming_short": "#4575b4",
    "dropping_off": "#1a9850",
    "run_ahead_of_the_ball": "#fdae61",
    "behind": "#984ea3",
    "support": "#66c2a5",
    "pulling_wide": "#8c6bb1",
    "overlap": "#ff7f00",
    "underlap": "#a65628",
}


@dataclass
class PlayerInfo:
    player_id: int
    team_id: int
    name: str
    short_name: str
    role: str
    position_group: str

    @property
    def is_goalkeeper(self) -> bool:
        return self.role == "GK" or self.position_group == "Goalkeeper"


@dataclass
class TrackSample:
    t_rel: float
    x: float
    y: float


@dataclass
class CornerWindow:
    statsbomb_match_id: str
    skillcorner_match_id: str
    opponent: str
    period: int
    corner_time: float
    taker_name: str
    result: str
    shot_generated: bool
    attempt_players: list[str]
    attempt_time_rel: float | None
    corner_index: int
    side: str = "unknown"
    barca_tracks: dict[int, list[TrackSample]] = field(default_factory=lambda: defaultdict(list))
    ball_track: list[TrackSample] = field(default_factory=list)
    tagged_runs: list[dict[str, Any]] = field(default_factory=list)


def _normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(".", " ").replace("-", " ")
    return " ".join(text.split())


def _parse_tracking_timestamp(timestamp: str) -> float:
    hh, mm, ss = timestamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _parse_dynamic_timestamp(timestamp: str) -> float:
    mm, ss = timestamp.split(":")
    return int(mm) * 60 + float(ss)


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    return float(value)


def _team_attacks_right(meta: dict, team_id: int, period: int) -> bool:
    home_team_id = int(meta["home_team"]["id"])
    home_dir = meta["home_team_side"][period - 1]
    if team_id == home_team_id:
        return home_dir == "left_to_right"
    return home_dir == "right_to_left"


def _skillcorner_to_mpl(
    x: float,
    y: float,
    *,
    pitch_length: float,
    pitch_width: float,
    attack_right: bool,
) -> tuple[float, float]:
    if not attack_right:
        x = -x
    x_mpl = (x + pitch_length / 2.0) / pitch_length * 120.0
    y_mpl = (y + pitch_width / 2.0) / pitch_width * 80.0
    return x_mpl, y_mpl


def _statsbomb_corner_result(events: list[dict], corner_idx: int) -> tuple[str, bool, list[str]]:
    corner = events[corner_idx]
    possession = corner.get("possession")
    period = corner.get("period")
    shots: list[dict] = []
    for event in events[corner_idx + 1:]:
        if event.get("period") != period or event.get("possession") != possession:
            break
        if event.get("team", {}).get("name") != TEAM:
            continue
        if f.is_shot(event):
            shots.append(event)
    shooters = [
        event.get("player", {}).get("name", "Unknown")
        for event in shots
        if event.get("player", {}).get("name")
    ]
    if any(f.is_goal(shot) for shot in shots):
        return "Goal", True, shooters
    if shots:
        return "Shot", True, shooters
    return "No shot", False, []


def _statsbomb_event_time_seconds(event: dict) -> float:
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def _statsbomb_corner_outcome(events: list[dict], corner_idx: int) -> tuple[str, bool, list[str], float | None]:
    corner = events[corner_idx]
    possession = corner.get("possession")
    period = corner.get("period")
    corner_time = _statsbomb_event_time_seconds(corner)
    shots: list[dict] = []
    for event in events[corner_idx + 1:]:
        if event.get("period") != period or event.get("possession") != possession:
            break
        if event.get("team", {}).get("name") != TEAM:
            continue
        if f.is_shot(event):
            shots.append(event)
    shooters = [
        event.get("player", {}).get("name", "Unknown")
        for event in shots
        if event.get("player", {}).get("name")
    ]
    attempt_time_rel = None
    if shots:
        attempt_time_rel = max(0.0, _statsbomb_event_time_seconds(shots[-1]) - corner_time)
    if any(f.is_goal(shot) for shot in shots):
        return "Goal", True, shooters, attempt_time_rel
    if shots:
        return "Shot", True, shooters, attempt_time_rel
    return "No shot", False, [], None


def _load_barcelona_match_rows() -> list[dict]:
    rows = list(csv.DictReader(open(MATCHES_CSV, encoding="utf-8")))
    return [
        row for row in rows
        if row.get("skillcorner") and TEAM in (row.get("home", ""), row.get("away", ""))
    ]


def _load_skillcorner_meta(zip_path: Path, match_id: str) -> tuple[dict, dict[int, PlayerInfo], int, int]:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}.json") as fh:
            meta = json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    players: dict[int, PlayerInfo] = {}
    for player in meta["players"]:
        role = player.get("player_role", {}) or {}
        full_name = " ".join(part for part in [player.get("first_name"), player.get("last_name")] if part)
        players[int(player["id"])] = PlayerInfo(
            player_id=int(player["id"]),
            team_id=int(player["team_id"]),
            name=full_name,
            short_name=(player.get("last_name") or full_name or "Unknown"),
            role=role.get("acronym", ""),
            position_group=role.get("position_group", ""),
        )

    home_team_id = int(meta["home_team"]["id"])
    away_team_id = int(meta["away_team"]["id"])
    barca_team_id = away_team_id if "Barcelona" in meta["away_team"]["name"] else home_team_id
    opp_team_id = home_team_id if barca_team_id == away_team_id else away_team_id
    return meta, players, barca_team_id, opp_team_id


def _build_corner_windows(row: dict) -> list[CornerWindow]:
    statsbomb_match_id = row["statsbomb"].strip()
    events_path = STATSBOMB_ROOT / f"{statsbomb_match_id}.json"
    if not events_path.exists():
        return []
    opponent = row["away"] if TEAM == row["home"] else row["home"]
    events = json.loads(events_path.read_text(encoding="utf-8"))
    windows: list[CornerWindow] = []
    for idx, event in enumerate(events):
        if not (f.is_pass(event) and f.is_corner_pass(event) and event.get("team", {}).get("name") == TEAM):
            continue
        result, shot_generated, attempt_players, attempt_time_rel = _statsbomb_corner_outcome(events, idx)
        windows.append(
            CornerWindow(
                statsbomb_match_id=statsbomb_match_id,
                skillcorner_match_id=row["skillcorner"].strip(),
                opponent=opponent,
                period=int(event.get("period", 1)),
                corner_time=_statsbomb_event_time_seconds(event),
                taker_name=event.get("player", {}).get("name", "Unknown"),
                result=result,
                shot_generated=shot_generated,
                attempt_players=attempt_players,
                attempt_time_rel=attempt_time_rel,
                corner_index=len(windows) + 1,
            )
        )
    return windows


def _attach_tagged_runs(
    zip_path: Path,
    match_id: str,
    windows: list[CornerWindow],
    meta: dict,
    barca_team_id: int,
) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}_dynamic_events.csv") as fh:
            rows = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))
            for row in rows:
                if row["event_type"] != "off_ball_run" or int(row["team_id"]) != barca_team_id:
                    continue
                period = int(row["period"])
                run_time = _parse_dynamic_timestamp(row["time_start"])
                for window in windows:
                    if window.period != period:
                        continue
                    if not (window.corner_time - 3.5 <= run_time <= window.corner_time + 2.0):
                        continue
                    attack_right = _team_attacks_right(meta, barca_team_id, period)
                    x_start = _safe_float(row["x_start"])
                    y_start = _safe_float(row["y_start"])
                    x_end = _safe_float(row["x_end"])
                    y_end = _safe_float(row["y_end"])
                    if None in (x_start, y_start, x_end, y_end):
                        continue
                    sx, sy = _skillcorner_to_mpl(
                        x_start, y_start,
                        pitch_length=float(meta["pitch_length"]),
                        pitch_width=float(meta["pitch_width"]),
                        attack_right=attack_right,
                    )
                    ex, ey = _skillcorner_to_mpl(
                        x_end, y_end,
                        pitch_length=float(meta["pitch_length"]),
                        pitch_width=float(meta["pitch_width"]),
                        attack_right=attack_right,
                    )
                    window.tagged_runs.append({
                        "player_name": row["player_name"],
                        "subtype": row["event_subtype"] or "unknown",
                        "x_start": sx,
                        "y_start": sy,
                        "x_end": ex,
                        "y_end": ey,
                    })


def _extract_tracking_windows(
    zip_path: Path,
    match_id: str,
    windows: list[CornerWindow],
    meta: dict,
    players: dict[int, PlayerInfo],
    barca_team_id: int,
) -> None:
    pitch_length = float(meta["pitch_length"])
    pitch_width = float(meta["pitch_width"])

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}_tracking_extrapolated.jsonl") as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8")
            for line in text:
                frame = json.loads(line)
                timestamp = frame.get("timestamp")
                period = frame.get("period")
                if timestamp is None or period is None:
                    continue
                time_sec = _parse_tracking_timestamp(timestamp)
                period = int(period)

                active_windows = [
                    window for window in windows
                    if window.period == period and window.corner_time - PRE_SECONDS <= time_sec <= window.corner_time + _tracking_post_seconds(window)
                ]
                if not active_windows:
                    continue

                frame_offense: dict[int, tuple[float, float]] = {}
                attack_right = _team_attacks_right(meta, barca_team_id, period)

                for player in frame.get("player_data", []):
                    player_id = int(player["player_id"])
                    info = players.get(player_id)
                    x = _safe_float(player.get("x"))
                    y = _safe_float(player.get("y"))
                    if info is None or x is None or y is None:
                        continue
                    x_mpl, y_mpl = _skillcorner_to_mpl(
                        x, y,
                        pitch_length=pitch_length,
                        pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    if info.team_id == barca_team_id:
                        frame_offense[player_id] = (x_mpl, y_mpl)
                ball = frame.get("ball_data", {}) or {}
                ball_xy = None
                bx = _safe_float(ball.get("x"))
                by = _safe_float(ball.get("y"))
                if bx is not None and by is not None:
                    ball_xy = _skillcorner_to_mpl(
                        bx, by,
                        pitch_length=pitch_length,
                        pitch_width=pitch_width,
                        attack_right=attack_right,
                    )

                for window in active_windows:
                    t_rel = time_sec - window.corner_time
                    for player_id, (x_mpl, y_mpl) in frame_offense.items():
                        window.barca_tracks[player_id].append(TrackSample(t_rel, x_mpl, y_mpl))
                    if ball_xy is not None:
                        window.ball_track.append(TrackSample(t_rel, ball_xy[0], ball_xy[1]))


def _nearest_sample(samples: list[TrackSample], target_t: float) -> TrackSample | None:
    if not samples:
        return None
    return min(samples, key=lambda sample: abs(sample.t_rel - target_t))


def _infer_corner_side(window: CornerWindow) -> str:
    kick_ball = _nearest_sample(window.ball_track, 0.0)
    if kick_ball is not None:
        return "top" if kick_ball.y >= 40.0 else "bottom"
    return "top"


def _side_label(side: str) -> str:
    return "Left-side corner" if side == "bottom" else "Right-side corner"


def _tracking_post_seconds(window: CornerWindow) -> float:
    return POST_SECONDS


def _display_end_seconds(window: CornerWindow) -> float:
    return POST_SECONDS


def _resample_track(samples: list[TrackSample], sample_times: np.ndarray) -> np.ndarray | None:
    if len(samples) < 2:
        return None
    samples = sorted(samples, key=lambda sample: sample.t_rel)
    times = np.array([sample.t_rel for sample in samples])
    xs = np.array([sample.x for sample in samples])
    ys = np.array([sample.y for sample in samples])
    if np.allclose(times, times[0]):
        return None
    x_interp = np.interp(sample_times, times, xs, left=np.nan, right=np.nan)
    y_interp = np.interp(sample_times, times, ys, left=np.nan, right=np.nan)
    path = np.column_stack([x_interp, y_interp])
    if np.isnan(path).all():
        return None
    return path


def _corner_kicker_id(window: CornerWindow, players: dict[int, PlayerInfo]) -> int | None:
    kick_ball = _nearest_sample(window.ball_track, 0.0)
    if kick_ball is None:
        return None
    candidates = []
    for player_id, samples in window.barca_tracks.items():
        kick_pos = _nearest_sample(samples, 0.0)
        if kick_pos is None:
            continue
        dist = math.hypot(kick_pos.x - kick_ball.x, kick_pos.y - kick_ball.y)
        candidates.append((dist, player_id))
    if not candidates:
        return None
    dist, player_id = min(candidates, key=lambda item: item[0])
    return player_id if dist <= 6.0 else None


def _track_summary(window: CornerWindow, samples: list[TrackSample]) -> tuple[TrackSample | None, TrackSample | None, TrackSample | None]:
    start = _nearest_sample(samples, -PRE_SECONDS)
    kick = _nearest_sample(samples, 0.0)
    end = _nearest_sample(samples, _display_end_seconds(window))
    return start, kick, end


def _player_paths_for_window(
    window: CornerWindow,
    players: dict[int, PlayerInfo],
) -> list[dict[str, Any]]:
    kicker_id = _corner_kicker_id(window, players)
    offense_paths: list[dict[str, Any]] = []
    display_end = _display_end_seconds(window)
    sample_count = max(MEAN_PATH_SAMPLES, int(round((display_end + PRE_SECONDS) * 6)))
    sample_times = np.linspace(-PRE_SECONDS, display_end, sample_count)

    for player_id, samples in window.barca_tracks.items():
        info = players[player_id]
        if info.is_goalkeeper or player_id == kicker_id:
            continue
        start, kick, end = _track_summary(window, samples)
        if start is None or kick is None or end is None:
            continue
        if max(start.x, kick.x, end.x) < INTEREST_X_THRESHOLD:
            continue
        path = _resample_track(samples, sample_times)
        if path is None:
            continue
        offense_paths.append({
            "player_id": player_id,
            "name": info.short_name,
            "role": info.role or info.position_group,
            "start": (start.x, start.y),
            "kick": (kick.x, kick.y),
            "end": (end.x, end.y),
            "path": path,
            "result": window.result,
            "corner_index": window.corner_index,
            "match": window.opponent,
        })

    return offense_paths


def _collect_corner_windows() -> tuple[list[CornerWindow], dict[int, PlayerInfo]]:
    all_windows: list[CornerWindow] = []
    player_lookup: dict[int, PlayerInfo] = {}

    for row in _load_barcelona_match_rows():
        match_id = row["skillcorner"].strip()
        zip_path = SKILLCORNER_ROOT / f"{match_id}.zip"
        if not zip_path.is_file():
            continue

        windows = _build_corner_windows(row)
        if not windows:
            continue

        meta, players, barca_team_id, _ = _load_skillcorner_meta(zip_path, match_id)
        player_lookup.update(players)

        _attach_tagged_runs(zip_path, match_id, windows, meta, barca_team_id)
        _extract_tracking_windows(zip_path, match_id, windows, meta, players, barca_team_id)

        for window in windows:
            if window.barca_tracks:
                window.side = _infer_corner_side(window)
                all_windows.append(window)

    return all_windows, player_lookup


def _make_pitch() -> tuple[plt.Figure, plt.Axes, Pitch]:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="white",
        line_color="#c7d5cc",
        linewidth=1.6,
    )
    fig, ax = pitch.draw(figsize=(10, 7.5))
    fig.patch.set_facecolor("white")
    ax.set_xticks([])
    ax.set_yticks([])
    return fig, ax, pitch


def _overlay_pitch_lines(ax: plt.Axes) -> None:
    overlay = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="none",
        line_color="#f5f2e8",
        linewidth=2.1,
    )
    overlay.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])


def _apply_header(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.995)
    fig.text(0.5, 0.926, subtitle, ha="center", fontsize=10.4, color="#333333")


def _corner_marker(ax: plt.Axes, side: str) -> None:
    y = 79.2 if side == "top" else 0.8
    marker = ">" 
    ax.scatter([119.5], [y], s=240, marker=marker, color="#ffcc00", edgecolors="#444444", linewidth=0.8, zorder=6)


def _format_match_clock(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def _side_slug(side: str) -> str:
    return "left" if side == "bottom" else "right"


def _variant_slug(variant: str) -> str:
    return {
        "starts": "01starts",
        "paths": "02paths",
        "ends": "03ends",
    }[variant]


def _attempt_player_ids(window: CornerWindow, players: dict[int, PlayerInfo]) -> set[int]:
    if not window.attempt_players:
        return set()

    by_full: dict[str, set[int]] = defaultdict(set)
    by_short: dict[str, set[int]] = defaultdict(set)
    by_last: dict[str, set[int]] = defaultdict(set)
    for player_id, info in players.items():
        by_full[_normalize_name(info.name)].add(player_id)
        by_short[_normalize_name(info.short_name)].add(player_id)
        last_name = _normalize_name(info.short_name).split()
        if last_name:
            by_last[last_name[-1]].add(player_id)

    matched: set[int] = set()
    for name in window.attempt_players:
        normalized = _normalize_name(name)
        matched.update(by_full.get(normalized, set()))
        matched.update(by_short.get(normalized, set()))
        tokens = normalized.split()
        if tokens:
            matched.update(by_last.get(tokens[-1], set()))
    return matched


def _plot_runner_heatmap_all_corners(
    windows: list[CornerWindow],
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="white",
        line_color="#c7d5cc",
        linewidth=1.6,
    )
    fig, axes = plt.subplots(1, 2, figsize=(16, 7.5))
    fig.subplots_adjust(top=0.80, bottom=0.14, wspace=0.12)

    for ax in axes:
        pitch.draw(ax=ax)
        ax.set_xticks([])
        ax.set_yticks([])

    for ax, side in zip(axes, ("bottom", "top")):
        xs: list[float] = []
        ys: list[float] = []
        for window in windows:
            if window.side != side:
                continue
            for path in _player_paths_for_window(window, players):
                arr = path["path"]
                mask = ~np.isnan(arr[:, 0]) & ~np.isnan(arr[:, 1])
                xs.extend(arr[mask, 0].tolist())
                ys.extend(arr[mask, 1].tolist())

        if xs:
            pitch.kdeplot(
                xs,
                ys,
                ax=ax,
                fill=True,
                levels=70,
                thresh=0.05,
                cut=4,
                cmap="inferno",
                alpha=0.78,
                zorder=2,
            )
            pitch.scatter(xs, ys, ax=ax, s=6, color="#ffb347", alpha=0.08, edgecolors="none", zorder=3)

        _overlay_pitch_lines(ax)

        _corner_marker(ax, side)
        shots = sum(1 for window in windows if window.side == side and window.shot_generated)
        goals = sum(1 for window in windows if window.side == side and window.result == "Goal")
        ax.set_title(
            f"{_side_label(side)}  |  n = {sum(1 for w in windows if w.side == side)} corners  |  {shots} shots  |  {goals} goals",
            fontsize=12.5,
            fontweight="bold",
            pad=10,
        )

    _apply_header(
        fig,
        "Barcelona attacking corner run heatmap",
        (
            f"Attacker position density from t-{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s "
            "around every corner. Fire-style heatmap with pitch markings redrawn on top."
        ),
    )
    handles = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffcc00", markeredgecolor="#444444", markersize=9, lw=0, label="Corner kick"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=1, fontsize=9, frameon=True, fancybox=True, framealpha=0.92)
    save_fig(fig, output_path, tight=False)


def _draw_corner_panel(
    ax: plt.Axes,
    pitch: Pitch,
    window: CornerWindow,
    players: dict[int, PlayerInfo],
    *,
    variant: str,
) -> None:
    pitch.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])

    paths = _player_paths_for_window(window, players)
    attempt_ids = _attempt_player_ids(window, players)
    end_seconds = _display_end_seconds(window)

    for path in paths:
        arr = path["path"]
        mask = ~np.isnan(arr[:, 0]) & ~np.isnan(arr[:, 1])
        if mask.sum() < 2:
            continue
        xs = arr[mask, 0]
        ys = arr[mask, 1]
        color = "#2ca02c" if window.result == "Goal" else FOCUS_COLOR
        is_attempt_player = path["player_id"] in attempt_ids

        if variant == "paths":
            pitch.lines(
                xs[:-1],
                ys[:-1],
                xs[1:],
                ys[1:],
                ax=ax,
                color=color,
                comet=False,
                transparent=True,
                alpha_start=0.28,
                alpha_end=0.9,
                lw=2.3,
                zorder=2,
            )
            ax.annotate(
                "",
                xy=(xs[-1], ys[-1]),
                xytext=(xs[-2], ys[-2]),
                arrowprops={"arrowstyle": "-", "color": color, "lw": 2.0, "alpha": 0.95},
                zorder=5,
            )

        if variant in {"starts", "paths"}:
            ax.scatter([xs[0]], [ys[0]], s=54, color="white", edgecolors=color, linewidth=1.25, zorder=4)

        if variant == "ends":
            ax.scatter([xs[-1]], [ys[-1]], s=46, color=color, edgecolors="white", linewidth=0.8, zorder=5)

        if is_attempt_player and variant in {"starts", "paths", "ends"}:
            attempt_x, attempt_y = (xs[-1], ys[-1]) if variant != "starts" else (xs[0], ys[0])
            ax.scatter(
                [attempt_x],
                [attempt_y],
                s=180,
                marker="*",
                color="#ffd166",
                edgecolors="#7a4c00",
                linewidth=0.9,
                zorder=7,
            )

    _corner_marker(ax, window.side)
    ax.set_title(
        {
            "starts": f"01 Starts  |  t-{PRE_SECONDS:.1f}s",
            "paths": f"02 Paths  |  t-{PRE_SECONDS:.1f}s to t+{end_seconds:.1f}s",
            "ends": f"03 Ends  |  t+{end_seconds:.1f}s",
        }[variant],
        fontsize=11.5,
        fontweight="bold",
        pad=10,
    )


def _plot_corner_four_panel(
    window: CornerWindow,
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color="white",
        line_color="#c7d5cc",
        linewidth=1.6,
    )
    fig, axes = plt.subplots(1, 3, figsize=(18.5, 7.2))
    fig.subplots_adjust(top=0.76, bottom=0.13, wspace=0.08)

    for ax, variant in zip(axes, ("starts", "paths", "ends")):
        _draw_corner_panel(ax, pitch, window, players, variant=variant)

    paths = _player_paths_for_window(window, players)
    end_seconds = _display_end_seconds(window)
    _apply_header(
        fig,
        "Barcelona attacking corner run map",
        (
            f"{window.opponent}  |  corner {window.corner_index}  |  {_side_label(window.side)}  |  "
            f"{_format_match_clock(window.corner_time)}  |  {window.result}  |  {len(paths)} tracked attackers  |  "
            f"window: t-{PRE_SECONDS:.1f}s to t+{end_seconds:.1f}s"
        ),
    )

    handles = [
        Line2D([0], [0], marker="o", color="white", markeredgecolor=FOCUS_COLOR, markeredgewidth=1.2, markersize=7, lw=0, label=f"Start (t-{PRE_SECONDS:.1f}s)"),
        Line2D([0], [0], color=FOCUS_COLOR, lw=2.5, label="Attacker run"),
        Line2D([0], [0], marker="o", color=FOCUS_COLOR, markeredgecolor="white", markeredgewidth=0.8, markersize=7, lw=0, label="End point"),
    ]
    if window.shot_generated:
        handles.append(Line2D([0], [0], marker="*", color="#ffd166", markeredgecolor="#7a4c00", markeredgewidth=0.9, markersize=10, lw=0, label="Attempt player"))
    handles.append(Line2D([0], [0], marker=">", color="w", markerfacecolor="#ffcc00", markeredgecolor="#444444", markersize=9, lw=0, label="Corner kick"))
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 5), fontsize=9, frameon=True, fancybox=True, framealpha=0.92)
    save_fig(fig, output_path, tight=False)


def _plot_runner_density(
    windows: list[CornerWindow],
    players: dict[int, PlayerInfo],
    *,
    side: str,
    output_path: Path,
) -> None:
    fig, ax, pitch = _make_pitch()
    fig.subplots_adjust(top=0.82, bottom=0.10)

    offense_paths: list[dict[str, Any]] = []
    for window in windows:
        if window.side != side:
            continue
        offense_paths.extend(_player_paths_for_window(window, players))

    xs: list[float] = []
    ys: list[float] = []
    for path in offense_paths:
        arr = path["path"]
        mask = ~np.isnan(arr[:, 0]) & ~np.isnan(arr[:, 1])
        xs.extend(arr[mask, 0].tolist())
        ys.extend(arr[mask, 1].tolist())

    if xs:
        pitch.kdeplot(
            xs,
            ys,
            ax=ax,
            fill=True,
            levels=70,
            thresh=0.05,
            cut=4,
            cmap="inferno",
            alpha=0.78,
            zorder=2,
        )
        pitch.scatter(xs, ys, ax=ax, s=6, color="#ffb347", alpha=0.08, edgecolors="none", zorder=3)

    _overlay_pitch_lines(ax)
    _corner_marker(ax, side)
    _apply_header(
        fig,
        "Barcelona corner run density",
        f"{_side_label(side)}  |  density of Barcelona runner positions from t-{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s",
    )
    save_fig(fig, output_path, tight=False)


def _plot_corner_windows(
    windows: list[CornerWindow],
    players: dict[int, PlayerInfo],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for window in windows:
        clock = _format_match_clock(window.corner_time).replace(":", "")
        base = (
            f"corner_{window.skillcorner_match_id}_{window.corner_index:02d}_"
            f"{_side_slug(window.side)}_{clock}_{window.result.lower().replace(' ', '_')}"
        )
        _plot_corner_four_panel(window, players, output_dir / f"{base}.png")


def _plot_tagged_runs(
    windows: list[CornerWindow],
    *,
    side: str,
    output_path: Path,
) -> None:
    tagged = [run for window in windows if window.side == side for run in window.tagged_runs]
    if not tagged:
        return

    fig, ax, pitch = _make_pitch()
    fig.subplots_adjust(top=0.84, bottom=0.12)

    counts = Counter()
    for run in tagged:
        subtype = run["subtype"]
        counts[subtype] += 1
        color = RUN_SUBTYPE_COLORS.get(subtype, NEUTRAL_COLOR)
        pitch.arrows(
            run["x_start"], run["y_start"], run["x_end"], run["y_end"], ax=ax,
            color=color, width=1.8, headwidth=4.8, headlength=4.8, alpha=0.75, zorder=3,
        )
        pitch.scatter([run["x_start"]], [run["y_start"]], ax=ax, s=28, color=color, edgecolors="white", linewidth=0.45, zorder=4)

    _corner_marker(ax, side)
    fig.suptitle("Barcelona tagged off-ball runs near corners", fontsize=16, fontweight="bold", y=0.97)
    fig.text(
        0.5,
        0.93,
        f"{_side_label(side)}  |  SkillCorner off_ball_run labels in the corner window  |  n = {len(tagged)} tagged runs",
        ha="center",
        fontsize=10.5,
        color="#333333",
    )

    handles = [
        Line2D([0], [0], color=RUN_SUBTYPE_COLORS[subtype], lw=3, label=f"{subtype} ({counts[subtype]})")
        for subtype, _ in counts.most_common()
    ]
    handles.append(Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffcc00", markeredgecolor="#444444", markersize=9, lw=0, label="Corner kick"))
    ax.legend(handles=handles, loc="lower left", fontsize=9, frameon=True, fancybox=True, framealpha=0.92)
    save_fig(fig, output_path, tight=False)


def _write_run_table(
    windows: list[CornerWindow],
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    rows: list[dict[str, Any]] = []
    for window in windows:
        for path in _player_paths_for_window(window, players):
            start_x, start_y = path["start"]
            end_x, end_y = path["end"]
            rows.append({
                "skillcorner_match_id": window.skillcorner_match_id,
                "statsbomb_match_id": window.statsbomb_match_id,
                "opponent": window.opponent,
                "corner_index": window.corner_index,
                "corner_time_sec": round(window.corner_time, 2),
                "corner_side": window.side,
                "result": window.result,
                "team": TEAM,
                "player_id": path["player_id"],
                "player_name": path["name"],
                "role": path["role"],
                "start_x": round(start_x, 2),
                "start_y": round(start_y, 2),
                "end_x": round(end_x, 2),
                "end_y": round(end_y, 2),
                "delta_x": round(end_x - start_x, 2),
                "delta_y": round(end_y - start_y, 2),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [
            "skillcorner_match_id", "statsbomb_match_id", "opponent", "corner_index",
            "corner_time_sec", "corner_side", "result", "team", "player_id", "player_name",
            "role", "start_x", "start_y", "end_x", "end_y", "delta_x", "delta_y",
        ])
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path | None = None) -> None:
    if output_dir is None:
        output_dir = ASSETS_ROOT

    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting Barcelona corner tracking windows from SkillCorner...")
    windows, players = _collect_corner_windows()
    if not windows:
        print("No Barcelona corners with SkillCorner tracking found.")
        return

    side_counts = Counter(window.side for window in windows)
    print(f"  {len(windows)} tracked corners  |  {dict(side_counts)}")

    for legacy_name in (
        "runner_heatmap_all_corners.png",
        "runner_paths_all_corners.png",
        "runner_density_left_side.png",
        "runner_density_right_side.png",
        "tagged_runs_left_side.png",
        "tagged_runs_right_side.png",
    ):
        legacy_path = output_dir / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()

    corner_maps_dir = output_dir / "corner_run_maps"
    corner_maps_dir.mkdir(parents=True, exist_ok=True)
    for png_path in corner_maps_dir.glob("*.png"):
        png_path.unlink()

    _write_run_table(windows, players, output_dir / "barcelona_corner_run_summary.csv")
    _plot_corner_windows(windows, players, corner_maps_dir)

    print(f"Done - outputs saved to {output_dir}/")


if __name__ == "__main__":
    run()
