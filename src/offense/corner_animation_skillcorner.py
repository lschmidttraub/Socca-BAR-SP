"""Animate the next Barcelona corner after a given minute using SkillCorner.

The script links ``data/matches.csv`` to StatsBomb events and SkillCorner
tracking. It builds a reusable per-match cache of corner tracking windows, then
renders the selected corner as a GIF/MP4/HTML animation.

Example:
    python src/offense/corner_animation_skillcorner.py 2059201 39.0
    python src/offense/corner_animation_skillcorner.py 2059201 39 --output assets/corner_animations/example.mp4
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from mplsoccer import Pitch


TEAM = "Barcelona"
DATA_DIRNAME = "data"
STATSBOMB_ZIPS = ("league_phase.zip", "last16.zip", "playoffs.zip")
DEFAULT_PRE_SECONDS = 2.0
DEFAULT_POST_SECONDS = 20.0
DEFAULT_FRAME_STRIDE = 1
DEFAULT_FPS = 10

BARCA_COLOR = "#d71920"
OPPONENT_COLOR = "#1f77b4"
BALL_COLOR = "#111111"
BALL_UNTRACKED_COLOR = "#9a9a9a"
PITCH_LINE_COLOR = "#c7d5cc"
CACHE_VERSION = 5

BARCA_DIM_COLOR = "#e8a3a6"
OPPONENT_DIM_COLOR = "#9db9d5"

CSV_TO_STATSBOMB: dict[str, str] = {
    "Internazionale": "Inter Milan",
    "PSG": "Paris Saint-Germain",
    "Monaco": "AS Monaco",
    "Leverkusen": "Bayer Leverkusen",
    "Dortmund": "Borussia Dortmund",
    "Frankfurt": "Eintracht Frankfurt",
    "Qarabag": "Qarabag FK",
    "Bayern Munchen": "Bayern Munich",
    "Bayern M\u00fcnchen": "Bayern Munich",
    "Olympiacos Piraeus": "Olympiacos",
    "PSV": "PSV Eindhoven",
    "Kobenhavn": "FC Kobenhavn",
    "K\u00f8benhavn": "FC Kobenhavn",
}


@dataclass(frozen=True)
class PlayerInfo:
    player_id: int
    team_id: int
    short_name: str
    full_name: str


@dataclass(frozen=True)
class CornerEvent:
    index: int
    statsbomb_match_id: str
    skillcorner_match_id: str
    period: int
    possession: int | None
    corner_time_sec: float
    turnover_time_sec: float
    end_reason: str
    team_name: str
    taker_name: str
    opponent_name: str
    touch_player_names: tuple[str, ...]


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


PROJECT_ROOT = _project_root()
DATA_DIR = PROJECT_ROOT / DATA_DIRNAME
MATCHES_CSV = DATA_DIR / "matches.csv"
STATSBOMB_DIR = DATA_DIR / "statsbomb"
SKILLCORNER_DIR = DATA_DIR / "skillcorner"
ASSETS_DIR = PROJECT_ROOT / "assets" / "corner_animations"
CACHE_DIR = ASSETS_DIR / "cache"


def _normalise_team(name: str) -> str:
    clean = " ".join((name or "").split())
    for old, new in CSV_TO_STATSBOMB.items():
        clean = clean.replace(old, new)
    return clean


def _normalise_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(".", " ").replace("-", " ").replace("\u00f8", "o")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.split())


def _name_aliases(name: str) -> set[str]:
    normalised = _normalise_name(name.replace("(GK)", ""))
    if not normalised:
        return set()
    tokens = normalised.split()
    aliases = {normalised}
    if tokens:
        aliases.add(tokens[-1])
    if len(tokens) >= 2:
        aliases.add(" ".join(tokens[-2:]))
    if len(tokens) >= 3:
        aliases.add(" ".join(tokens[-3:]))
    return aliases


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    return float(value)


def _parse_tracking_timestamp(timestamp: str) -> float:
    hh, mm, ss = timestamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _event_time_seconds(event: dict[str, Any]) -> float:
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def _format_clock(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def _is_corner(event: dict[str, Any]) -> bool:
    return (
        event.get("type", {}).get("id") == 30
        and event.get("pass", {}).get("type", {}).get("name") == "Corner"
    )


def _event_player_name(event: dict[str, Any]) -> str | None:
    name = event.get("player", {}).get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _event_touch_player_names(event: dict[str, Any]) -> list[str]:
    names: list[str] = []
    actor = _event_player_name(event)
    if actor is not None:
        names.append(actor)

    pass_data = event.get("pass", {})
    recipient = pass_data.get("recipient", {}).get("name")
    pass_completed = event.get("type", {}).get("id") == 30 and pass_data.get("outcome") is None
    if pass_completed and isinstance(recipient, str) and recipient.strip():
        names.append(recipient.strip())

    return names


def _load_match_rows() -> list[dict[str, str]]:
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return rows


def _find_match_row(skillcorner_match_id: str) -> dict[str, str]:
    for row in _load_match_rows():
        if row.get("skillcorner", "").strip() == skillcorner_match_id:
            return row
    raise KeyError(f"No matches.csv row found with skillcorner={skillcorner_match_id}")


def _load_statsbomb_events(statsbomb_match_id: str) -> list[dict[str, Any]]:
    target = f"{statsbomb_match_id}.json"

    direct = next(STATSBOMB_DIR.rglob(target), None) if STATSBOMB_DIR.exists() else None
    if direct is not None:
        return json.loads(direct.read_text(encoding="utf-8"))

    zip_candidates = [STATSBOMB_DIR / name for name in STATSBOMB_ZIPS]
    zip_candidates.extend(sorted(STATSBOMB_DIR.rglob("*.zip")) if STATSBOMB_DIR.exists() else [])
    seen: set[Path] = set()
    for zip_path in zip_candidates:
        if zip_path in seen or not zip_path.is_file():
            continue
        seen.add(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if member.rsplit("/", 1)[-1] == target:
                    with zf.open(member) as fh:
                        return json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    raise FileNotFoundError(f"No StatsBomb event JSON found for match {statsbomb_match_id}")


def _skillcorner_zip_candidates(skillcorner_match_id: str) -> list[Path]:
    candidates = [
        SKILLCORNER_DIR / f"{skillcorner_match_id}.zip",
        DATA_DIR / "skillcorner.zip",
    ]
    if SKILLCORNER_DIR.exists():
        candidates.extend(sorted(SKILLCORNER_DIR.rglob("*.zip")))
    return candidates


def _find_skillcorner_zip(skillcorner_match_id: str) -> Path:
    expected_members = {
        f"{skillcorner_match_id}.json",
        f"{skillcorner_match_id}_tracking_extrapolated.jsonl",
    }
    seen: set[Path] = set()
    for zip_path in _skillcorner_zip_candidates(skillcorner_match_id):
        if zip_path in seen or not zip_path.is_file():
            continue
        seen.add(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            basenames = {name.rsplit("/", 1)[-1] for name in zf.namelist()}
        if expected_members.issubset(basenames):
            return zip_path
    raise FileNotFoundError(f"No SkillCorner zip found for match {skillcorner_match_id}")


def _open_zip_member_by_basename(zf: zipfile.ZipFile, basename: str) -> io.BufferedReader:
    for member in zf.namelist():
        if member.rsplit("/", 1)[-1] == basename:
            return zf.open(member)
    raise KeyError(f"Missing {basename} in {zf.filename}")


def _load_skillcorner_meta(
    zip_path: Path,
    skillcorner_match_id: str,
) -> tuple[dict[str, Any], dict[int, PlayerInfo], int, int]:
    with zipfile.ZipFile(zip_path) as zf:
        with _open_zip_member_by_basename(zf, f"{skillcorner_match_id}.json") as fh:
            meta = json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    players: dict[int, PlayerInfo] = {}
    for player in meta["players"]:
        role_name = player.get("player_role", {}).get("name", "")
        first = player.get("first_name") or ""
        last = player.get("last_name") or ""
        full_name = " ".join(part for part in (first, last) if part) or "Unknown"
        short_name = last or full_name
        if role_name == "Goalkeeper":
            short_name = f"{short_name} (GK)"
        player_id = int(player["id"])
        players[player_id] = PlayerInfo(
            player_id=player_id,
            team_id=int(player["team_id"]),
            short_name=short_name,
            full_name=full_name,
        )

    home_team_id = int(meta["home_team"]["id"])
    away_team_id = int(meta["away_team"]["id"])
    barca_team_id = away_team_id if TEAM in meta["away_team"]["name"] else home_team_id
    opponent_team_id = home_team_id if barca_team_id == away_team_id else away_team_id
    return meta, players, barca_team_id, opponent_team_id


def _team_attacks_right(meta: dict[str, Any], team_id: int, period: int) -> bool:
    home_team_id = int(meta["home_team"]["id"])
    home_dir = meta["home_team_side"][period - 1]
    if team_id == home_team_id:
        return home_dir == "left_to_right"
    return home_dir == "right_to_left"


def _skillcorner_to_statsbomb(
    x: float,
    y: float,
    *,
    pitch_length: float,
    pitch_width: float,
    attack_right: bool,
) -> tuple[float, float]:
    if not attack_right:
        x = -x
    return (
        (x + pitch_length / 2.0) / pitch_length * 120.0,
        (y + pitch_width / 2.0) / pitch_width * 80.0,
    )


def _corner_end(
    events: list[dict[str, Any]],
    corner_idx: int,
    post_seconds: float,
) -> tuple[float, str]:
    corner = events[corner_idx]
    period = corner.get("period")
    corner_time = _event_time_seconds(corner)
    requested_end = corner_time + post_seconds

    for event in events[corner_idx + 1:]:
        event_time = _event_time_seconds(event)
        if event.get("period") != period:
            return event_time, "period changed"
        if event_time > requested_end:
            return requested_end, f"manual duration ({post_seconds:g}s)"

    return requested_end, f"manual duration ({post_seconds:g}s)"


def _corner_touch_player_names(
    events: list[dict[str, Any]],
    corner_idx: int,
    turnover_time_sec: float,
) -> tuple[str, ...]:
    corner = events[corner_idx]
    period = corner.get("period")
    names: list[str] = []
    seen: set[str] = set()

    for event in events[corner_idx:]:
        if event.get("period") != period:
            break
        if _event_time_seconds(event) > turnover_time_sec:
            break
        for player_name in _event_touch_player_names(event):
            normalised = _normalise_name(player_name)
            if normalised in seen:
                continue
            seen.add(normalised)
            names.append(player_name)
    return tuple(names)


def _find_corners(
    events: list[dict[str, Any]],
    row: dict[str, str],
    *,
    team: str,
    include_all_teams: bool,
    post_seconds: float,
) -> list[CornerEvent]:
    corners: list[CornerEvent] = []
    skillcorner_match_id = row["skillcorner"].strip()
    statsbomb_match_id = row["statsbomb"].strip()

    for event_idx, event in enumerate(events):
        if not _is_corner(event):
            continue
        team_name = event.get("team", {}).get("name", "")
        if not include_all_teams and team_name != team:
            continue
        opponent_name = row["away"] if team_name == row["home"] else row["home"]
        turnover_time_sec, end_reason = _corner_end(events, event_idx, post_seconds)
        corners.append(
            CornerEvent(
                index=len(corners) + 1,
                statsbomb_match_id=statsbomb_match_id,
                skillcorner_match_id=skillcorner_match_id,
                period=int(event.get("period", 1)),
                possession=event.get("possession"),
                corner_time_sec=_event_time_seconds(event),
                turnover_time_sec=turnover_time_sec,
                end_reason=end_reason,
                team_name=team_name,
                taker_name=event.get("player", {}).get("name", "Unknown"),
                opponent_name=opponent_name,
                touch_player_names=_corner_touch_player_names(events, event_idx, turnover_time_sec),
            )
        )
    return corners


def _next_corner_after_minute(corners: list[CornerEvent], minute: float) -> CornerEvent:
    threshold = minute * 60.0
    for corner in corners:
        if corner.corner_time_sec >= threshold:
            return corner
    raise LookupError(f"No matching corner found after minute {minute:g}")


def _player_payload(
    player: dict[str, Any],
    players: dict[int, PlayerInfo],
    *,
    barca_team_id: int,
    touch_names: set[str],
) -> dict[str, Any] | None:
    player_id = int(player["player_id"])
    info = players.get(player_id)
    x = _safe_float(player.get("x"))
    y = _safe_float(player.get("y"))
    if info is None or x is None or y is None:
        return None
    return {
        "id": player_id,
        "name": info.short_name,
        "full_name": info.full_name,
        "team": "Barcelona" if info.team_id == barca_team_id else "Opponent",
        "touched_ball": _player_matches_touch_names(info, touch_names),
        "x_raw": x,
        "y_raw": y,
    }


def _player_matches_touch_names(info: PlayerInfo, touch_names: set[str]) -> bool:
    if not touch_names:
        return False
    candidates = _name_aliases(info.full_name) | _name_aliases(info.short_name)
    return bool(candidates & touch_names)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}
    return bool(value)


def _ball_is_tracked(ball: dict[str, Any]) -> bool:
    for key in (
        "is_tracked",
        "tracked",
        "is_ball_tracked",
        "ball_tracked",
        "is_detected",
        "detected",
        "is_visible",
        "visible",
    ):
        if key in ball:
            return _as_bool(ball[key])
    return True


def _corner_cache_paths(skillcorner_match_id: str) -> tuple[Path, Path]:
    base = CACHE_DIR / f"{skillcorner_match_id}_corner_movements"
    return base.with_suffix(".json"), base.with_suffix(".csv")


def _cache_is_usable(
    cache_path: Path,
    corners: list[CornerEvent],
    *,
    pre_seconds: float,
    frame_stride: int,
) -> bool:
    if not cache_path.is_file():
        return False
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        cached.get("cache_version") == CACHE_VERSION
        and len(cached.get("corners", [])) == len(corners)
        and cached.get("pre_seconds") == pre_seconds
        and cached.get("frame_stride") == frame_stride
    )


def _build_corner_cache(
    *,
    row: dict[str, str],
    corners: list[CornerEvent],
    pre_seconds: float,
    frame_stride: int,
    force: bool,
) -> dict[str, Any]:
    skillcorner_match_id = row["skillcorner"].strip()
    json_path, csv_path = _corner_cache_paths(skillcorner_match_id)
    if not force and _cache_is_usable(
        json_path,
        corners,
        pre_seconds=pre_seconds,
        frame_stride=frame_stride,
    ):
        return json.loads(json_path.read_text(encoding="utf-8"))

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _find_skillcorner_zip(skillcorner_match_id)
    meta, players, barca_team_id, _ = _load_skillcorner_meta(zip_path, skillcorner_match_id)
    pitch_length = float(meta["pitch_length"])
    pitch_width = float(meta["pitch_width"])

    cached_corners: list[dict[str, Any]] = []
    for corner in corners:
        cached_corners.append(
            {
                "corner_index": corner.index,
                "statsbomb_match_id": corner.statsbomb_match_id,
                "skillcorner_match_id": corner.skillcorner_match_id,
                "period": corner.period,
                "possession": corner.possession,
                "corner_time_sec": corner.corner_time_sec,
                "turnover_time_sec": corner.turnover_time_sec,
                "end_reason": corner.end_reason,
                "team_name": corner.team_name,
                "taker_name": corner.taker_name,
                "opponent_name": corner.opponent_name,
                "touch_player_names": list(corner.touch_player_names),
                "frames": [],
            }
        )

    with zipfile.ZipFile(zip_path) as zf:
        with _open_zip_member_by_basename(
            zf,
            f"{skillcorner_match_id}_tracking_extrapolated.jsonl",
        ) as fh:
            for frame_no, line in enumerate(io.TextIOWrapper(fh, encoding="utf-8")):
                if frame_stride > 1 and frame_no % frame_stride:
                    continue
                frame = json.loads(line)
                timestamp = frame.get("timestamp")
                period = frame.get("period")
                if timestamp is None or period is None:
                    continue
                period = int(period)
                time_sec = _parse_tracking_timestamp(timestamp)
                active = [
                    (corner, payload)
                    for corner, payload in zip(corners, cached_corners, strict=True)
                    if (
                        corner.period == period
                        and corner.corner_time_sec - pre_seconds
                        <= time_sec
                        <= corner.turnover_time_sec
                    )
                ]
                if not active:
                    continue

                attack_right = _team_attacks_right(meta, barca_team_id, period)
                player_rows = list(frame.get("player_data", []))

                ball_payload = None
                ball = frame.get("ball_data", {}) or {}
                bx = _safe_float(ball.get("x"))
                by = _safe_float(ball.get("y"))
                if bx is not None and by is not None:
                    bx_mpl, by_mpl = _skillcorner_to_statsbomb(
                        bx,
                        by,
                        pitch_length=pitch_length,
                        pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    ball_payload = {
                        "x": round(bx_mpl, 3),
                        "y": round(by_mpl, 3),
                        "tracked": _ball_is_tracked(ball),
                    }

                for corner, payload in active:
                    touch_names = {
                        alias
                        for name in corner.touch_player_names
                        for alias in _name_aliases(name)
                    }
                    players_frame: list[dict[str, Any]] = []
                    for player in player_rows:
                        player_payload = _player_payload(
                            player,
                            players,
                            barca_team_id=barca_team_id,
                            touch_names=touch_names,
                        )
                        if player_payload is None:
                            continue
                        x, y = _skillcorner_to_statsbomb(
                            player_payload.pop("x_raw"),
                            player_payload.pop("y_raw"),
                            pitch_length=pitch_length,
                            pitch_width=pitch_width,
                            attack_right=attack_right,
                        )
                        player_payload["x"] = round(x, 3)
                        player_payload["y"] = round(y, 3)
                        players_frame.append(player_payload)
                    payload["frames"].append(
                        {
                            "timestamp": timestamp,
                            "time_sec": round(time_sec, 3),
                            "t_rel": round(time_sec - corner.corner_time_sec, 3),
                            "players": players_frame,
                            "ball": ball_payload,
                        }
                    )

    cache = {
        "cache_version": CACHE_VERSION,
        "match": {
            "statsbomb_match_id": row["statsbomb"].strip(),
            "skillcorner_match_id": skillcorner_match_id,
            "home": row.get("home", ""),
            "away": row.get("away", ""),
            "team_orientation": "Barcelona attacks left-to-right",
        },
        "pre_seconds": pre_seconds,
        "frame_stride": frame_stride,
        "corners": cached_corners,
    }
    json_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    _write_flat_cache_csv(cache, csv_path)
    return cache


def _write_flat_cache_csv(cache: dict[str, Any], output_path: Path) -> None:
    rows: list[dict[str, Any]] = []
    for corner in cache["corners"]:
        for frame_idx, frame in enumerate(corner["frames"]):
            ball = frame.get("ball") or {}
            if ball:
                rows.append(
                    {
                        "skillcorner_match_id": corner["skillcorner_match_id"],
                        "corner_index": corner["corner_index"],
                        "corner_time_sec": corner["corner_time_sec"],
                        "frame_index": frame_idx,
                        "timestamp": frame["timestamp"],
                        "time_sec": frame["time_sec"],
                        "t_rel": frame["t_rel"],
                        "entity_type": "ball",
                        "entity_id": "",
                        "entity_name": "Ball",
                        "team": "Ball",
                        "x": ball.get("x"),
                        "y": ball.get("y"),
                        "ball_tracked": ball.get("tracked"),
                        "touched_ball": "",
                    }
                )
            for player in frame["players"]:
                rows.append(
                    {
                        "skillcorner_match_id": corner["skillcorner_match_id"],
                        "corner_index": corner["corner_index"],
                        "corner_time_sec": corner["corner_time_sec"],
                        "frame_index": frame_idx,
                        "timestamp": frame["timestamp"],
                        "time_sec": frame["time_sec"],
                        "t_rel": frame["t_rel"],
                        "entity_type": "player",
                        "entity_id": player["id"],
                        "entity_name": player["name"],
                        "team": player["team"],
                        "x": player["x"],
                        "y": player["y"],
                        "ball_tracked": "",
                        "touched_ball": player.get("touched_ball", False),
                    }
                )

    fieldnames = [
        "skillcorner_match_id",
        "corner_index",
        "corner_time_sec",
        "frame_index",
        "timestamp",
        "time_sec",
        "t_rel",
        "entity_type",
        "entity_id",
        "entity_name",
        "team",
        "x",
        "y",
        "ball_tracked",
        "touched_ball",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _cached_corner(cache: dict[str, Any], corner: CornerEvent) -> dict[str, Any]:
    for cached in cache["corners"]:
        if cached["corner_index"] == corner.index:
            return cached
    raise KeyError(f"Corner {corner.index} missing from cache")


def _default_output_path(corner: CornerEvent, suffix: str) -> Path:
    clock = _format_clock(corner.corner_time_sec).replace(":", "")
    return ASSETS_DIR / f"corner_{corner.skillcorner_match_id}_{clock}.{suffix}"


def _draw_pitch() -> tuple[plt.Figure, plt.Axes, Pitch]:
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color=PITCH_LINE_COLOR,
        linewidth=1.4,
    )
    fig, ax = pitch.draw(figsize=(12, 8))
    fig.patch.set_facecolor("white")
    ax.set_xticks([])
    ax.set_yticks([])
    return fig, ax, pitch


def _save_animation(animation: FuncAnimation, output_path: Path, fps: int) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()
    if suffix == ".gif":
        animation.save(output_path, writer=PillowWriter(fps=fps))
    elif suffix == ".mp4":
        animation.save(output_path, writer=FFMpegWriter(fps=fps))
    elif suffix in {".html", ".htm"}:
        output_path.write_text(animation.to_jshtml(fps=fps), encoding="utf-8")
    else:
        raise ValueError("Output must end with .gif, .mp4, or .html")


def _player_color(player: dict[str, Any], *, highlight_touches: bool) -> str:
    if not highlight_touches or player.get("touched_ball"):
        return BARCA_COLOR if player["team"] == "Barcelona" else OPPONENT_COLOR
    return BARCA_DIM_COLOR if player["team"] == "Barcelona" else OPPONENT_DIM_COLOR


def _render_animation(
    corner: dict[str, Any],
    output_path: Path,
    fps: int,
    *,
    highlight_touches: bool,
) -> None:
    frames = corner["frames"]
    if not frames:
        raise ValueError("Selected corner has no cached tracking frames")

    fig, ax, _ = _draw_pitch()
    fig.subplots_adjust(top=0.88, bottom=0.08)
    ax.set_title(
        (
            f"{corner['team_name']} corner vs {corner['opponent_name']}  |  "
            f"{_format_clock(corner['corner_time_sec'])}  |  "
            f"taker: {corner['taker_name']}"
        ),
        fontsize=13,
        fontweight="bold",
        pad=10,
    )
    subtitle = fig.text(
        0.5,
        0.91,
        (
            "Barcelona in red, opponent in blue, ball in black. "
            "Untracked ball frames are grey. Pitch oriented so Barcelona attacks left-to-right."
        ),
        ha="center",
        fontsize=9.5,
        color="#333333",
    )
    _ = subtitle

    barca_scatter = ax.scatter([], [], s=92, c=BARCA_COLOR, edgecolors="white", linewidth=0.8, zorder=4)
    opp_scatter = ax.scatter([], [], s=92, c=OPPONENT_COLOR, edgecolors="white", linewidth=0.8, zorder=3)
    ball_scatter = ax.scatter([], [], s=48, c=BALL_COLOR, edgecolors="white", linewidth=0.5, zorder=5)
    clock_text = ax.text(
        4,
        76,
        "",
        ha="left",
        va="center",
        fontsize=12,
        fontweight="bold",
        color="#111111",
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "edgecolor": "#dddddd", "alpha": 0.9},
        zorder=6,
    )

    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BARCA_COLOR, markeredgecolor="white", markersize=8, label="Barcelona"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=OPPONENT_COLOR, markeredgecolor="white", markersize=8, label="Opponent"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BALL_COLOR, markeredgecolor="white", markersize=6, label="Ball"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BALL_UNTRACKED_COLOR, markeredgecolor="white", markersize=6, label="Ball not tracked"),
    ]
    if highlight_touches:
        handles.append(
            Line2D([0], [0], marker="o", color="w", markerfacecolor=BARCA_DIM_COLOR, markeredgecolor="white", markersize=8, label="No touch in scene")
        )
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.08), ncol=len(handles), frameon=False)

    def update(frame: dict[str, Any]) -> tuple[Any, ...]:
        barca_players = [player for player in frame["players"] if player["team"] == "Barcelona"]
        opponent_players = [player for player in frame["players"] if player["team"] == "Opponent"]
        barca_xy = [(player["x"], player["y"]) for player in barca_players]
        opponent_xy = [(player["x"], player["y"]) for player in opponent_players]
        barca_colors = [
            _player_color(player, highlight_touches=highlight_touches)
            for player in barca_players
        ]
        opponent_colors = [
            _player_color(player, highlight_touches=highlight_touches)
            for player in opponent_players
        ]
        ball = frame.get("ball")
        barca_scatter.set_offsets(barca_xy or [[float("nan"), float("nan")]])
        opp_scatter.set_offsets(opponent_xy or [[float("nan"), float("nan")]])
        barca_scatter.set_facecolors(barca_colors or [BARCA_COLOR])
        opp_scatter.set_facecolors(opponent_colors or [OPPONENT_COLOR])
        if ball:
            ball_scatter.set_offsets([[ball["x"], ball["y"]]])
            ball_scatter.set_facecolors([BALL_COLOR if ball.get("tracked", True) else BALL_UNTRACKED_COLOR])
        else:
            ball_scatter.set_offsets([[float("nan"), float("nan")]])
        clock_text.set_text(f"t {frame['t_rel']:+.1f}s")
        return barca_scatter, opp_scatter, ball_scatter, clock_text

    animation = FuncAnimation(
        fig,
        update,
        frames=frames,
        interval=1000 / fps,
        blit=False,
        repeat=True,
    )
    _save_animation(animation, output_path, fps)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_id", help="SkillCorner match id from data/matches.csv")
    parser.add_argument("minute", type=float, help="Minute threshold; selects the next corner after this")
    parser.add_argument("--team", default=TEAM, help="StatsBomb team name whose next corner should be selected")
    parser.add_argument("--include-all-teams", action="store_true", help="Select the next corner by either team")
    parser.add_argument("--pre-seconds", type=float, default=DEFAULT_PRE_SECONDS)
    parser.add_argument(
        "--post-seconds",
        "--max-post-seconds",
        dest="post_seconds",
        type=float,
        default=DEFAULT_POST_SECONDS,
        help="Seconds to show after the corner kick; this is used as a fixed manual length.",
    )
    parser.add_argument("--frame-stride", type=int, default=DEFAULT_FRAME_STRIDE)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--force-cache", action="store_true", help="Rebuild the match cache even if it exists")
    parser.add_argument(
        "--highlight-touches",
        action="store_true",
        help="Desaturate players who do not touch the ball during the selected corner scene",
    )
    parser.add_argument("--output", type=Path, help="Output .gif, .mp4, or .html path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    row = _find_match_row(args.game_id)
    events = _load_statsbomb_events(row["statsbomb"].strip())
    corners = _find_corners(
        events,
        row,
        team=args.team,
        include_all_teams=args.include_all_teams,
        post_seconds=args.post_seconds,
    )
    corner = _next_corner_after_minute(corners, args.minute)

    cache = _build_corner_cache(
        row=row,
        corners=corners,
        pre_seconds=args.pre_seconds,
        frame_stride=max(1, args.frame_stride),
        force=args.force_cache,
    )
    cached_corner = _cached_corner(cache, corner)
    output_path = args.output or _default_output_path(corner, "gif")
    _render_animation(
        cached_corner,
        output_path,
        fps=args.fps,
        highlight_touches=args.highlight_touches,
    )

    json_cache, csv_cache = _corner_cache_paths(args.game_id)
    print(
        "Rendered corner animation\n"
        f"  match: {row.get('home')} vs {row.get('away')}\n"
        f"  selected corner: #{corner.index} at {_format_clock(corner.corner_time_sec)}\n"
        f"  situation end: {_format_clock(corner.turnover_time_sec)} ({corner.end_reason})\n"
        f"  StatsBomb touch players: {', '.join(corner.touch_player_names) or 'none'}\n"
        f"  output: {output_path}\n"
        f"  cache json: {json_cache}\n"
        f"  cache csv: {csv_cache}"
    )


if __name__ == "__main__":
    main()
