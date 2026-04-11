"""Shared data loader for the corner-run-maps snippet.

Reads ``data/matches.csv``, streams StatsBomb event JSONs out of the
three ZIPs in ``data/statsbomb/``, and loads SkillCorner per-match
tracking from ``data/skillcorner/{id}.zip`` — all without extracting
to disk.

The public entry point is :func:`collect_corner_windows`, which returns
a list of :class:`CornerWindow` objects (one per tracked corner) and a
player lookup dict.

All paths are CWD-relative: run from the project root (the directory
that contains ``data/``).
"""

from __future__ import annotations

import csv
import io
import json
import math
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# ── Paths (CWD-relative) ────────────────────────────────────────────

DATA_DIR = Path("data")
MATCHES_CSV = DATA_DIR / "matches.csv"
STATSBOMB_DIR = DATA_DIR / "statsbomb"
SKILLCORNER_DIR = DATA_DIR / "skillcorner"

STATSBOMB_ZIPS = ("league_phase.zip", "last16.zip", "playoffs.zip")

# CSV team names that differ from their StatsBomb event spelling.
# Applied when reading matches.csv so every downstream lookup is
# an exact match against the events.
CSV_TO_STATSBOMB: dict[str, str] = {
    "Internazionale": "Inter Milan",
    "PSG": "Paris Saint-Germain",
    "Monaco": "AS Monaco",
    "Leverkusen": "Bayer Leverkusen",
    "Dortmund": "Borussia Dortmund",
    "Frankfurt": "Eintracht Frankfurt",
    "Qarabag": "Qarabağ FK",
    "Bayern München": "Bayern Munich",
    "Olympiacos Piraeus": "Olympiacos",
    "PSV": "PSV Eindhoven",
    "København": "FC København",
}


def _normalise_team(name: str) -> str:
    """Apply CSV→StatsBomb spelling fixes."""
    for old, new in CSV_TO_STATSBOMB.items():
        name = name.replace(old, new)
    return name


# ── Constants ────────────────────────────────────────────────────────

DEFAULT_TEAM = "Barcelona"
PRE_SECONDS = 2.5
POST_SECONDS = 2.5
INTEREST_X_THRESHOLD = 72.0   # only include attackers past halfway
MEAN_PATH_SAMPLES = 18

FOCUS_COLOR = "#a50026"
NEUTRAL_COLOR = "#878787"


# ── Event predicates (StatsBomb v8) ──────────────────────────────────

def is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == 30


def is_corner_pass(e: dict) -> bool:
    return is_pass(e) and e.get("pass", {}).get("type", {}).get("name") == "Corner"


def is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == 16


def is_goal(e: dict) -> bool:
    return e.get("shot", {}).get("outcome", {}).get("name") == "Goal"


# ── Data classes ─────────────────────────────────────────────────────


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
    result: str
    shot_generated: bool
    attempt_players: list[str]
    attempt_time_rel: float | None
    corner_index: int
    side: str = "unknown"
    barca_tracks: dict[int, list[TrackSample]] = field(
        default_factory=lambda: defaultdict(list),
    )
    ball_track: list[TrackSample] = field(default_factory=list)


# ── Small helpers ────────────────────────────────────────────────────


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(".", " ").replace("-", " ")
    return " ".join(text.split())


def _parse_tracking_timestamp(timestamp: str) -> float:
    hh, mm, ss = timestamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


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
    """Convert SkillCorner metres (origin at centre) → StatsBomb 120×80."""
    if not attack_right:
        x = -x
    x_mpl = (x + pitch_length / 2.0) / pitch_length * 120.0
    y_mpl = (y + pitch_width / 2.0) / pitch_width * 80.0
    return x_mpl, y_mpl


def event_time_seconds(event: dict) -> float:
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def format_match_clock(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    minutes = total_seconds // 60
    secs = total_seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def side_label(side: str) -> str:
    return "Left-side corner" if side == "bottom" else "Right-side corner"


def side_slug(side: str) -> str:
    return "left" if side == "bottom" else "right"


# ── StatsBomb corner outcome ─────────────────────────────────────────


def _statsbomb_corner_outcome(
    events: list[dict],
    corner_idx: int,
    team: str,
) -> tuple[str, bool, list[str], float | None]:
    """Determine shot/goal/no-shot result within the corner possession."""
    corner = events[corner_idx]
    possession = corner.get("possession")
    period = corner.get("period")
    corner_time = event_time_seconds(corner)
    shots: list[dict] = []
    for event in events[corner_idx + 1:]:
        if event.get("period") != period or event.get("possession") != possession:
            break
        if event.get("team", {}).get("name") != team:
            continue
        if is_shot(event):
            shots.append(event)
    shooters = [
        event.get("player", {}).get("name", "Unknown")
        for event in shots
        if event.get("player", {}).get("name")
    ]
    attempt_time_rel = None
    if shots:
        attempt_time_rel = max(
            0.0, event_time_seconds(shots[-1]) - corner_time,
        )
    if any(is_goal(shot) for shot in shots):
        return "Goal", True, shooters, attempt_time_rel
    if shots:
        return "Shot", True, shooters, attempt_time_rel
    return "No shot", False, [], None


# ── Data loading ─────────────────────────────────────────────────────


def _load_match_rows(team: str) -> list[dict]:
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return [
        row for row in rows
        if row.get("skillcorner") and team in (row.get("home", ""), row.get("away", ""))
    ]


def _load_skillcorner_meta(
    zip_path: Path, match_id: str,
) -> tuple[dict, dict[int, PlayerInfo], int, int]:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}.json") as fh:
            meta = json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    players: dict[int, PlayerInfo] = {}
    for player in meta["players"]:
        role = player.get("player_role", {}) or {}
        full_name = " ".join(
            part for part in [player.get("first_name"), player.get("last_name")]
            if part
        )
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
    barca_team_id = (
        away_team_id if "Barcelona" in meta["away_team"]["name"] else home_team_id
    )
    opp_team_id = home_team_id if barca_team_id == away_team_id else away_team_id
    return meta, players, barca_team_id, opp_team_id


def _load_statsbomb_events(match_id: str) -> list[dict] | None:
    """Load event JSON for *match_id* from whichever StatsBomb ZIP contains it."""
    target = f"{match_id}.json"
    for zname in STATSBOMB_ZIPS:
        zp = STATSBOMB_DIR / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def _build_corner_windows(row: dict, team: str) -> list[CornerWindow]:
    statsbomb_match_id = row["statsbomb"].strip()
    opponent = row["away"] if team == row["home"] else row["home"]
    events = _load_statsbomb_events(statsbomb_match_id)
    if events is None:
        return []
    windows: list[CornerWindow] = []
    for idx, event in enumerate(events):
        if not (
            is_pass(event)
            and is_corner_pass(event)
            and event.get("team", {}).get("name") == team
        ):
            continue
        result, shot_generated, attempt_players, attempt_time_rel = (
            _statsbomb_corner_outcome(events, idx, team)
        )
        windows.append(
            CornerWindow(
                statsbomb_match_id=statsbomb_match_id,
                skillcorner_match_id=row["skillcorner"].strip(),
                opponent=opponent,
                period=int(event.get("period", 1)),
                corner_time=event_time_seconds(event),
                result=result,
                shot_generated=shot_generated,
                attempt_players=attempt_players,
                attempt_time_rel=attempt_time_rel,
                corner_index=len(windows) + 1,
            ),
        )
    return windows


def _extract_tracking_windows(
    zip_path: Path,
    match_id: str,
    windows: list[CornerWindow],
    meta: dict,
    players: dict[int, PlayerInfo],
    barca_team_id: int,
) -> None:
    """Load tracking frames into each CornerWindow's player/ball tracks."""
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
                    w for w in windows
                    if (
                        w.period == period
                        and w.corner_time - PRE_SECONDS <= time_sec <= w.corner_time + POST_SECONDS
                    )
                ]
                if not active_windows:
                    continue

                attack_right = _team_attacks_right(meta, barca_team_id, period)

                frame_offense: dict[int, tuple[float, float]] = {}
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
                bx = _safe_float(ball.get("x"))
                by = _safe_float(ball.get("y"))
                ball_xy = None
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
                        window.barca_tracks[player_id].append(
                            TrackSample(t_rel, x_mpl, y_mpl),
                        )
                    if ball_xy is not None:
                        window.ball_track.append(
                            TrackSample(t_rel, ball_xy[0], ball_xy[1]),
                        )


# ── Track processing ─────────────────────────────────────────────────


def nearest_sample(samples: list[TrackSample], target_t: float) -> TrackSample | None:
    if not samples:
        return None
    return min(samples, key=lambda s: abs(s.t_rel - target_t))


def infer_corner_side(window: CornerWindow) -> str:
    kick_ball = nearest_sample(window.ball_track, 0.0)
    if kick_ball is not None:
        return "top" if kick_ball.y >= 40.0 else "bottom"
    return "top"


def _resample_track(
    samples: list[TrackSample], sample_times: np.ndarray,
) -> np.ndarray | None:
    if len(samples) < 2:
        return None
    samples = sorted(samples, key=lambda s: s.t_rel)
    times = np.array([s.t_rel for s in samples])
    xs = np.array([s.x for s in samples])
    ys = np.array([s.y for s in samples])
    if np.allclose(times, times[0]):
        return None
    x_interp = np.interp(sample_times, times, xs, left=np.nan, right=np.nan)
    y_interp = np.interp(sample_times, times, ys, left=np.nan, right=np.nan)
    path = np.column_stack([x_interp, y_interp])
    if np.isnan(path).all():
        return None
    return path


def _corner_kicker_id(
    window: CornerWindow, players: dict[int, PlayerInfo],
) -> int | None:
    kick_ball = nearest_sample(window.ball_track, 0.0)
    if kick_ball is None:
        return None
    candidates = []
    for player_id, samples in window.barca_tracks.items():
        kick_pos = nearest_sample(samples, 0.0)
        if kick_pos is None:
            continue
        dist = math.hypot(kick_pos.x - kick_ball.x, kick_pos.y - kick_ball.y)
        candidates.append((dist, player_id))
    if not candidates:
        return None
    dist, player_id = min(candidates, key=lambda item: item[0])
    return player_id if dist <= 6.0 else None


def player_paths_for_window(
    window: CornerWindow,
    players: dict[int, PlayerInfo],
) -> list[dict[str, Any]]:
    """Build interpolated movement paths for every attacking outfielder."""
    kicker_id = _corner_kicker_id(window, players)
    offense_paths: list[dict[str, Any]] = []
    sample_count = max(MEAN_PATH_SAMPLES, int(round((POST_SECONDS + PRE_SECONDS) * 6)))
    sample_times = np.linspace(-PRE_SECONDS, POST_SECONDS, sample_count)

    for player_id, samples in window.barca_tracks.items():
        info = players.get(player_id)
        if info is None or info.is_goalkeeper or player_id == kicker_id:
            continue

        start = nearest_sample(samples, -PRE_SECONDS)
        kick = nearest_sample(samples, 0.0)
        end = nearest_sample(samples, POST_SECONDS)
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
        })

    return offense_paths


def attempt_player_ids(
    window: CornerWindow, players: dict[int, PlayerInfo],
) -> set[int]:
    if not window.attempt_players:
        return set()

    by_full: dict[str, set[int]] = defaultdict(set)
    by_short: dict[str, set[int]] = defaultdict(set)
    by_last: dict[str, set[int]] = defaultdict(set)
    for player_id, info in players.items():
        by_full[normalize_name(info.name)].add(player_id)
        by_short[normalize_name(info.short_name)].add(player_id)
        last_name = normalize_name(info.short_name).split()
        if last_name:
            by_last[last_name[-1]].add(player_id)

    matched: set[int] = set()
    for name in window.attempt_players:
        normalized = normalize_name(name)
        matched.update(by_full.get(normalized, set()))
        matched.update(by_short.get(normalized, set()))
        tokens = normalized.split()
        if tokens:
            matched.update(by_last.get(tokens[-1], set()))
    return matched


# ── Public API ───────────────────────────────────────────────────────


def collect_corner_windows(
    team: str,
) -> tuple[list[CornerWindow], dict[int, PlayerInfo]]:
    """Return all corner windows with tracking data for *team*."""
    all_windows: list[CornerWindow] = []
    player_lookup: dict[int, PlayerInfo] = {}

    for row in _load_match_rows(team):
        match_id = row["skillcorner"].strip()
        zip_path = SKILLCORNER_DIR / f"{match_id}.zip"
        if not zip_path.is_file():
            continue

        windows = _build_corner_windows(row, team)
        if not windows:
            continue

        meta, players, barca_team_id, _ = _load_skillcorner_meta(zip_path, match_id)
        player_lookup.update(players)

        _extract_tracking_windows(
            zip_path, match_id, windows, meta, players, barca_team_id,
        )

        for window in windows:
            if window.barca_tracks:
                window.side = infer_corner_side(window)
                all_windows.append(window)

    return all_windows, player_lookup
