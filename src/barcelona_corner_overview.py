#!/usr/bin/env python3
"""
Create an overview of Barcelona player positions at the moment of `corner_reception`
frames from SkillCorner game packages, and generate a heatmap.

Expected dataset layout
-----------------------
A root directory like `data_new/skillcorner/` containing one or more game packages,
either as folders or zip files named after the game id, e.g.:

    data_new/skillcorner/
        12345.zip
        67890/

Each package is expected to contain at least:
    - {game_id}_dynamic_events.csv
    - {game_id}_tracking_extrapolated.jsonl

Optionally, if present, the script also uses:
    - {game_id}_match.json

What the script does
--------------------
1. Finds all `corner_reception` rows in dynamic events.
2. Filters them to Barcelona corners when possible.
3. Uses each row's `frame_start` to read the matching frame from tracking.
4. Extracts Barcelona player positions at that exact frame.
5. Optionally normalizes every corner to the same attacking corner (top-right).
6. Saves:
   - a long table of all sampled positions
   - a per-player summary table
   - a mean-position overview plot
   - a positional heatmap
   - a small run summary JSON

Usage example
-------------
python barcelona_corner_overview.py \
    --dataset-root data_new/skillcorner \
    --team "Barcelona" \
    --output-dir outputs/barca_corner_overview

Notes
-----
- SkillCorner tracking coordinates are in meters, centered on the middle of the pitch.
- If `{game_id}_match.json` is available, player/team identification is much more reliable.
- If Barcelona players cannot be identified from metadata, the script falls back to
  plotting all players in the selected `corner_reception` frames and prints a warning.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
HALF_LENGTH = PITCH_LENGTH / 2.0
HALF_WIDTH = PITCH_WIDTH / 2.0


@dataclass
class GameResources:
    game_id: str
    container_path: Path
    is_zip: bool
    dynamic_events_member: str
    tracking_member: str
    match_member: Optional[str] = None


class PackageReader:
    """Read files from either a zip package or an extracted folder."""

    def __init__(self, resources: GameResources):
        self.resources = resources
        self._zip: Optional[zipfile.ZipFile] = None

    def __enter__(self) -> "PackageReader":
        if self.resources.is_zip:
            self._zip = zipfile.ZipFile(self.resources.container_path)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None

    def _open_binary(self, member: str):
        if self.resources.is_zip:
            assert self._zip is not None
            return self._zip.open(member, "r")
        return open(member, "rb")

    def read_text(self, member: str, encoding: str = "utf-8") -> str:
        with self._open_binary(member) as fh:
            return fh.read().decode(encoding)

    def open_text(self, member: str, encoding: str = "utf-8"):
        binary_fh = self._open_binary(member)
        return io.TextIOWrapper(binary_fh, encoding=encoding)


# -----------------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------------

def discover_game_packages(dataset_root: Path) -> List[GameResources]:
    """Discover game folders/zips and resolve the relevant file members."""
    resources: List[GameResources] = []

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {dataset_root}")

    # Zip packages like data_new/skillcorner/12345.zip
    for zip_path in sorted(dataset_root.glob("*.zip")):
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        res = _resolve_members(names, container_path=zip_path, is_zip=True)
        if res is not None:
            resources.append(res)

    # Extracted game folders like data_new/skillcorner/12345/
    for folder in sorted(p for p in dataset_root.iterdir() if p.is_dir()):
        names = [str(p) for p in folder.rglob("*") if p.is_file()]
        res = _resolve_members(names, container_path=folder, is_zip=False)
        if res is not None:
            resources.append(res)

    return resources


def _resolve_members(
    names: Sequence[str],
    container_path: Path,
    is_zip: bool,
) -> Optional[GameResources]:
    dynamic_candidates = [n for n in names if n.endswith("_dynamic_events.csv")]
    tracking_candidates = [n for n in names if n.endswith("_tracking_extrapolated.jsonl")]
    match_candidates = [n for n in names if n.endswith("_match.json")]

    if not dynamic_candidates or not tracking_candidates:
        return None

    dynamic_member = sorted(dynamic_candidates)[0]
    tracking_member = sorted(tracking_candidates)[0]
    match_member = sorted(match_candidates)[0] if match_candidates else None

    game_id = _extract_game_id(dynamic_member) or _extract_game_id(tracking_member) or container_path.stem

    return GameResources(
        game_id=str(game_id),
        container_path=container_path,
        is_zip=is_zip,
        dynamic_events_member=dynamic_member,
        tracking_member=tracking_member,
        match_member=match_member,
    )


def _extract_game_id(path_like: str) -> Optional[str]:
    filename = Path(path_like).name
    match = re.match(r"(\d+)_", filename)
    return match.group(1) if match else None


# -----------------------------------------------------------------------------
# Metadata parsing
# -----------------------------------------------------------------------------

def load_match_metadata(reader: PackageReader, member: Optional[str]) -> dict:
    if member is None:
        return {}
    try:
        return json.loads(reader.read_text(member))
    except Exception:
        return {}


@dataclass
class PlayerMeta:
    player_id: int
    player_name: str
    team_name: Optional[str]
    team_side: Optional[str]  # "home team" or "away team"


@dataclass
class MatchMeta:
    home_team_name: Optional[str]
    away_team_name: Optional[str]
    players: Dict[int, PlayerMeta]


TEAM_KEYS = [
    "home_team",
    "away_team",
    "homeTeam",
    "awayTeam",
]


def parse_match_meta(match_json: dict) -> MatchMeta:
    home_team_name = _nested_name(match_json.get("home_team")) or _nested_name(match_json.get("homeTeam"))
    away_team_name = _nested_name(match_json.get("away_team")) or _nested_name(match_json.get("awayTeam"))

    players: Dict[int, PlayerMeta] = {}

    # Primary, explicit parsing.
    for key in ("players", "lineup", "line_up"):
        value = match_json.get(key)
        if isinstance(value, list):
            _ingest_player_list(value, players, home_team_name, away_team_name)

    # Fallback recursive scan if the structure is different.
    if not players:
        for obj in _walk_json(match_json):
            if isinstance(obj, list):
                _ingest_player_list(obj, players, home_team_name, away_team_name)

    return MatchMeta(
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        players=players,
    )


def _nested_name(value) -> Optional[str]:
    if isinstance(value, dict):
        for key in ("name", "short_name", "shortName", "display_name", "displayName"):
            if value.get(key):
                return str(value[key])
    return None


def _ingest_player_list(
    maybe_players: list,
    players: Dict[int, PlayerMeta],
    home_team_name: Optional[str],
    away_team_name: Optional[str],
) -> None:
    for item in maybe_players:
        if not isinstance(item, dict):
            continue

        pid = item.get("player_id", item.get("id"))
        if pid is None:
            continue
        try:
            pid_int = int(pid)
        except Exception:
            continue

        team_name = None
        team_side = None

        if isinstance(item.get("team"), dict):
            team_name = _nested_name(item["team"])
        team_name = team_name or item.get("team_name") or item.get("teamName")

        team_id = item.get("team_id")
        if team_name is None and team_id is not None:
            # Sometimes lineups reference home/away team ids, but we only know names.
            # Leave as None if not directly recoverable.
            pass

        side_raw = item.get("team_side") or item.get("side") or item.get("group")
        if isinstance(side_raw, str):
            lowered = side_raw.strip().casefold()
            if "home" in lowered:
                team_side = "home team"
            elif "away" in lowered:
                team_side = "away team"

        if team_side == "home team" and team_name is None:
            team_name = home_team_name
        elif team_side == "away team" and team_name is None:
            team_name = away_team_name

        player_name = _player_name(item)
        players[pid_int] = PlayerMeta(
            player_id=pid_int,
            player_name=player_name,
            team_name=str(team_name) if team_name is not None else None,
            team_side=team_side,
        )


def _player_name(item: dict) -> str:
    for key in ("name", "player_name", "full_name", "fullName", "display_name", "displayName"):
        if item.get(key):
            return str(item[key])

    first = item.get("first_name") or item.get("firstName") or ""
    last = item.get("last_name") or item.get("lastName") or ""
    full = f"{first} {last}".strip()
    if full:
        return full

    return str(item.get("player_id", item.get("id", "unknown_player")))


def _walk_json(obj):
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_json(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_json(value)


# -----------------------------------------------------------------------------
# Dynamic events parsing
# -----------------------------------------------------------------------------

def load_dynamic_events(reader: PackageReader, member: str) -> pd.DataFrame:
    with reader.open_text(member) as fh:
        return pd.read_csv(fh)


TEAM_COLUMN_HINTS = [
    "team_name",
    "team",
    "attacking_team_name",
    "attacking_team",
    "team_in_possession_name",
    "possession_team_name",
    "owning_team_name",
    "start_team_name",
    "group",
    "possession_group",
]

PLAYER_COLUMN_HINTS = [
    "player_id",
    "start_player_id",
    "event_player_id",
    "attacking_player_id",
]


def detect_team_column(df: pd.DataFrame) -> Optional[str]:
    lower_to_original = {c.casefold(): c for c in df.columns}
    for hint in TEAM_COLUMN_HINTS:
        if hint.casefold() in lower_to_original:
            return lower_to_original[hint.casefold()]

    # Fallback: any column containing team/group.
    for col in df.columns:
        cl = col.casefold()
        if ("team" in cl or "group" in cl) and "opponent" not in cl:
            return col
    return None


def detect_player_column(df: pd.DataFrame) -> Optional[str]:
    lower_to_original = {c.casefold(): c for c in df.columns}
    for hint in PLAYER_COLUMN_HINTS:
        if hint.casefold() in lower_to_original:
            return lower_to_original[hint.casefold()]

    for col in df.columns:
        cl = col.casefold()
        if "player" in cl and "id" in cl:
            return col
    return None


@dataclass
class CornerSelection:
    frame_starts: List[int]
    selected_rows: pd.DataFrame
    selection_method: str


def select_corner_reception_frames(
    df: pd.DataFrame,
    team_keyword: str,
    match_meta: MatchMeta,
) -> CornerSelection:
    if "start_type" not in df.columns:
        raise ValueError("dynamic_events.csv does not contain a 'start_type' column")
    if "frame_start" not in df.columns:
        raise ValueError("dynamic_events.csv does not contain a 'frame_start' column")

    corners = df[df["start_type"].astype(str).str.casefold() == "corner_reception"].copy()
    if corners.empty:
        return CornerSelection([], corners, "no_corner_reception_rows")

    team_col = detect_team_column(corners)
    player_col = detect_player_column(corners)

    team_keyword_cf = team_keyword.casefold()

    # 1) Prefer explicit team column.
    if team_col is not None:
        team_series = corners[team_col].astype(str)
        mask = team_series.str.casefold().str.contains(team_keyword_cf, na=False)
        selected = corners[mask].copy()
        if not selected.empty:
            frames = pd.to_numeric(selected["frame_start"], errors="coerce").dropna().astype(int).tolist()
            return CornerSelection(frames, selected, f"team_column:{team_col}")

    # 2) Fall back to player mapping from match.json.
    if player_col is not None and match_meta.players:
        def player_is_team(pid) -> bool:
            try:
                pid_int = int(pid)
            except Exception:
                return False
            meta = match_meta.players.get(pid_int)
            return bool(meta and meta.team_name and team_keyword_cf in meta.team_name.casefold())

        mask = corners[player_col].apply(player_is_team)
        selected = corners[mask].copy()
        if not selected.empty:
            frames = pd.to_numeric(selected["frame_start"], errors="coerce").dropna().astype(int).tolist()
            return CornerSelection(frames, selected, f"player_column:{player_col}")

    # 3) If Barcelona is home/away and group-like column exists, try matching that side.
    if team_col is not None:
        barca_side = infer_team_side_from_match_meta(team_keyword, match_meta)
        if barca_side is not None:
            mask = corners[team_col].astype(str).str.casefold().eq(barca_side.casefold())
            selected = corners[mask].copy()
            if not selected.empty:
                frames = pd.to_numeric(selected["frame_start"], errors="coerce").dropna().astype(int).tolist()
                return CornerSelection(frames, selected, f"side_column:{team_col}")

    # 4) Last resort: take all corner_reception rows.
    frames = pd.to_numeric(corners["frame_start"], errors="coerce").dropna().astype(int).tolist()
    return CornerSelection(frames, corners, "fallback_all_corner_reception_rows")


# -----------------------------------------------------------------------------
# Team/player identification
# -----------------------------------------------------------------------------

def infer_team_side_from_match_meta(team_keyword: str, match_meta: MatchMeta) -> Optional[str]:
    team_keyword_cf = team_keyword.casefold()
    if match_meta.home_team_name and team_keyword_cf in match_meta.home_team_name.casefold():
        return "home team"
    if match_meta.away_team_name and team_keyword_cf in match_meta.away_team_name.casefold():
        return "away team"
    return None


def identify_team_players(team_keyword: str, match_meta: MatchMeta) -> Set[int]:
    team_keyword_cf = team_keyword.casefold()
    player_ids: Set[int] = set()
    inferred_side = infer_team_side_from_match_meta(team_keyword, match_meta)

    for pid, meta in match_meta.players.items():
        if meta.team_name and team_keyword_cf in meta.team_name.casefold():
            player_ids.add(pid)
        elif inferred_side is not None and meta.team_side == inferred_side:
            player_ids.add(pid)

    return player_ids


# -----------------------------------------------------------------------------
# Tracking extraction
# -----------------------------------------------------------------------------

def iter_tracking_frames(reader: PackageReader, member: str) -> Iterator[dict]:
    with reader.open_text(member) as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {member}: {exc}") from exc


@dataclass
class ExtractionResult:
    records: List[dict]
    found_frames: Set[int]


def extract_positions_at_frames(
    reader: PackageReader,
    tracking_member: str,
    frame_starts: Sequence[int],
    team_player_ids: Set[int],
    match_meta: MatchMeta,
    normalize_to_same_corner: bool,
    detected_only: bool,
    fallback_to_all_players: bool,
    game_id: str,
) -> ExtractionResult:
    target_frames = set(int(f) for f in frame_starts)
    found_frames: Set[int] = set()
    records: List[dict] = []

    if not target_frames:
        return ExtractionResult(records, found_frames)

    use_team_filter = bool(team_player_ids)

    for row in iter_tracking_frames(reader, tracking_member):
        frame = row.get("frame")
        if frame not in target_frames:
            continue

        found_frames.add(int(frame))
        timestamp = row.get("timestamp")
        period = row.get("period")
        ball_data = row.get("ball_data") or {}
        ball_x = _safe_float(ball_data.get("x"))
        ball_y = _safe_float(ball_data.get("y"))

        x_sign = 1.0
        y_sign = 1.0
        if normalize_to_same_corner:
            if ball_x is not None and ball_x < 0:
                x_sign = -1.0
            if ball_y is not None and ball_y < 0:
                y_sign = -1.0

        player_rows = row.get("player_data") or []
        for player in player_rows:
            pid_raw = player.get("player_id")
            if pid_raw is None:
                continue
            try:
                pid = int(pid_raw)
            except Exception:
                continue

            if detected_only and not bool(player.get("is_detected", False)):
                continue

            if use_team_filter:
                if pid not in team_player_ids:
                    continue
            elif not fallback_to_all_players:
                continue

            x = _safe_float(player.get("x"))
            y = _safe_float(player.get("y"))
            if x is None or y is None:
                continue

            meta = match_meta.players.get(pid)
            player_name = meta.player_name if meta else str(pid)
            team_name = meta.team_name if meta else None

            records.append(
                {
                    "game_id": game_id,
                    "frame": int(frame),
                    "timestamp": timestamp,
                    "period": period,
                    "player_id": pid,
                    "player_name": player_name,
                    "team_name": team_name,
                    "is_detected": bool(player.get("is_detected", False)),
                    "x": x,
                    "y": y,
                    "x_norm": x * x_sign,
                    "y_norm": y * y_sign,
                    "ball_x": ball_x,
                    "ball_y": ball_y,
                    "ball_x_norm": None if ball_x is None else ball_x * x_sign,
                    "ball_y_norm": None if ball_y is None else ball_y * y_sign,
                }
            )

        if found_frames == target_frames:
            break

    return ExtractionResult(records, found_frames)


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Aggregation and plotting
# -----------------------------------------------------------------------------

def summarize_positions(df_positions: pd.DataFrame, normalized: bool) -> pd.DataFrame:
    if df_positions.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "player_name",
                "samples",
                "mean_x",
                "mean_y",
                "median_x",
                "median_y",
                "std_x",
                "std_y",
                "detected_rate",
                "games",
                "frames",
            ]
        )

    x_col = "x_norm" if normalized else "x"
    y_col = "y_norm" if normalized else "y"

    summary = (
        df_positions.groupby(["player_id", "player_name"], dropna=False)
        .agg(
            samples=("player_id", "size"),
            mean_x=(x_col, "mean"),
            mean_y=(y_col, "mean"),
            median_x=(x_col, "median"),
            median_y=(y_col, "median"),
            std_x=(x_col, "std"),
            std_y=(y_col, "std"),
            detected_rate=("is_detected", "mean"),
            games=("game_id", pd.Series.nunique),
            frames=("frame", pd.Series.nunique),
        )
        .reset_index()
        .sort_values(["samples", "player_name"], ascending=[False, True])
    )

    for col in ("std_x", "std_y"):
        summary[col] = summary[col].fillna(0.0)

    return summary


def draw_pitch(ax, pitch_length: float = PITCH_LENGTH, pitch_width: float = PITCH_WIDTH) -> None:
    hl = pitch_length / 2.0
    hw = pitch_width / 2.0

    # Outer lines
    ax.plot([-hl, hl], [-hw, -hw], linewidth=1.2)
    ax.plot([-hl, hl], [hw, hw], linewidth=1.2)
    ax.plot([-hl, -hl], [-hw, hw], linewidth=1.2)
    ax.plot([hl, hl], [-hw, hw], linewidth=1.2)

    # Halfway line and center circle
    ax.plot([0, 0], [-hw, hw], linewidth=1.0)
    center_circle = plt.Circle((0, 0), 9.15, fill=False, linewidth=1.0)
    ax.add_patch(center_circle)

    # Penalty boxes
    penalty_area_length = 16.5
    penalty_area_width = 40.32
    six_yard_length = 5.5
    six_yard_width = 18.32

    # Left side
    ax.plot([-hl, -hl + penalty_area_length], [-penalty_area_width / 2, -penalty_area_width / 2], linewidth=1.0)
    ax.plot([-hl, -hl + penalty_area_length], [penalty_area_width / 2, penalty_area_width / 2], linewidth=1.0)
    ax.plot([-hl + penalty_area_length, -hl + penalty_area_length], [-penalty_area_width / 2, penalty_area_width / 2], linewidth=1.0)
    ax.plot([-hl, -hl + six_yard_length], [-six_yard_width / 2, -six_yard_width / 2], linewidth=1.0)
    ax.plot([-hl, -hl + six_yard_length], [six_yard_width / 2, six_yard_width / 2], linewidth=1.0)
    ax.plot([-hl + six_yard_length, -hl + six_yard_length], [-six_yard_width / 2, six_yard_width / 2], linewidth=1.0)

    # Right side
    ax.plot([hl, hl - penalty_area_length], [-penalty_area_width / 2, -penalty_area_width / 2], linewidth=1.0)
    ax.plot([hl, hl - penalty_area_length], [penalty_area_width / 2, penalty_area_width / 2], linewidth=1.0)
    ax.plot([hl - penalty_area_length, hl - penalty_area_length], [-penalty_area_width / 2, penalty_area_width / 2], linewidth=1.0)
    ax.plot([hl, hl - six_yard_length], [-six_yard_width / 2, -six_yard_width / 2], linewidth=1.0)
    ax.plot([hl, hl - six_yard_length], [six_yard_width / 2, six_yard_width / 2], linewidth=1.0)
    ax.plot([hl - six_yard_length, hl - six_yard_length], [-six_yard_width / 2, six_yard_width / 2], linewidth=1.0)

    # Penalty spots
    ax.scatter([-hl + 11, hl - 11], [0, 0], s=8)

    ax.set_xlim(-hl - 1, hl + 1)
    ax.set_ylim(-hw - 1, hw + 1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)


def save_heatmap(df_positions: pd.DataFrame, output_path: Path, normalized: bool, team_label: str) -> None:
    if df_positions.empty:
        return

    x_col = "x_norm" if normalized else "x"
    y_col = "y_norm" if normalized else "y"

    fig, ax = plt.subplots(figsize=(12, 8))
    hist = ax.hist2d(
        df_positions[x_col],
        df_positions[y_col],
        bins=(42, 28),
        range=[[-HALF_LENGTH, HALF_LENGTH], [-HALF_WIDTH, HALF_WIDTH]],
    )
    draw_pitch(ax)
    title = f"{team_label} positions at corner reception frames"
    if normalized:
        title += " (normalized to same attacking corner)"
    ax.set_title(title)
    fig.colorbar(hist[3], ax=ax, shrink=0.8, label="Position count")
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_mean_position_plot(
    df_summary: pd.DataFrame,
    output_path: Path,
    normalized: bool,
    team_label: str,
) -> None:
    if df_summary.empty:
        return

    fig, ax = plt.subplots(figsize=(12, 8))
    draw_pitch(ax)
    ax.scatter(df_summary["mean_x"], df_summary["mean_y"], s=80)

    for _, row in df_summary.iterrows():
        label = row["player_name"] if pd.notna(row["player_name"]) else str(row["player_id"])
        ax.text(row["mean_x"] + 0.4, row["mean_y"] + 0.4, str(label), fontsize=8)

    title = f"{team_label} mean positions at corner reception frames"
    if normalized:
        title += " (normalized)"
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------

def run(args: argparse.Namespace) -> dict:
    dataset_root = Path(args.dataset_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    packages = discover_game_packages(dataset_root)
    if not packages:
        raise FileNotFoundError(
            f"No valid game packages found under {dataset_root}. "
            "Expected folders or zip files containing *_dynamic_events.csv and *_tracking_extrapolated.jsonl."
        )

    if args.game_ids:
        requested_ids = {g.strip() for g in args.game_ids.split(",") if g.strip()}
        packages = [p for p in packages if p.game_id in requested_ids]
        if not packages:
            raise ValueError(f"No discovered game packages match --game-ids={args.game_ids!r}")

    all_records: List[dict] = []
    per_game_report: List[dict] = []
    used_fallback_to_all_players = False

    for resources in packages:
        with PackageReader(resources) as reader:
            dynamic_events = load_dynamic_events(reader, resources.dynamic_events_member)
            match_json = load_match_metadata(reader, resources.match_member)
            match_meta = parse_match_meta(match_json)

            selection = select_corner_reception_frames(dynamic_events, args.team, match_meta)
            team_player_ids = identify_team_players(args.team, match_meta)

            extraction = extract_positions_at_frames(
                reader=reader,
                tracking_member=resources.tracking_member,
                frame_starts=selection.frame_starts,
                team_player_ids=team_player_ids,
                match_meta=match_meta,
                normalize_to_same_corner=not args.no_normalize,
                detected_only=args.detected_only,
                fallback_to_all_players=args.fallback_to_all_players,
                game_id=resources.game_id,
            )

            if not team_player_ids and args.fallback_to_all_players and extraction.records:
                used_fallback_to_all_players = True

            all_records.extend(extraction.records)
            per_game_report.append(
                {
                    "game_id": resources.game_id,
                    "container": str(resources.container_path),
                    "corner_selection_method": selection.selection_method,
                    "corner_rows_selected": int(len(selection.selected_rows)),
                    "requested_frames": int(len(selection.frame_starts)),
                    "found_frames": int(len(extraction.found_frames)),
                    "identified_team_players": int(len(team_player_ids)),
                    "positions_extracted": int(len(extraction.records)),
                    "home_team_name": match_meta.home_team_name,
                    "away_team_name": match_meta.away_team_name,
                }
            )

    positions_df = pd.DataFrame(all_records)
    normalized = not args.no_normalize
    summary_df = summarize_positions(positions_df, normalized=normalized)

    # Save tabular outputs.
    positions_csv = output_dir / "barcelona_corner_positions_long.csv"
    summary_csv = output_dir / "barcelona_corner_player_overview.csv"
    per_game_csv = output_dir / "barcelona_corner_per_game_report.csv"
    summary_json = output_dir / "barcelona_corner_run_summary.json"

    positions_df.to_csv(positions_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)
    pd.DataFrame(per_game_report).to_csv(per_game_csv, index=False)

    # Save plots.
    heatmap_png = output_dir / "barcelona_corner_heatmap.png"
    overview_png = output_dir / "barcelona_corner_mean_positions.png"
    save_heatmap(positions_df, heatmap_png, normalized=normalized, team_label=args.team)
    save_mean_position_plot(summary_df, overview_png, normalized=normalized, team_label=args.team)

    run_summary = {
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "team": args.team,
        "game_count": len(packages),
        "total_positions": int(len(positions_df)),
        "unique_players": int(positions_df["player_id"].nunique()) if not positions_df.empty else 0,
        "unique_frames": int(positions_df["frame"].nunique()) if not positions_df.empty else 0,
        "normalized_to_same_corner": normalized,
        "detected_only": bool(args.detected_only),
        "fallback_to_all_players_used": bool(used_fallback_to_all_players),
        "outputs": {
            "positions_csv": str(positions_csv),
            "summary_csv": str(summary_csv),
            "per_game_csv": str(per_game_csv),
            "heatmap_png": str(heatmap_png),
            "overview_png": str(overview_png),
        },
        "per_game": per_game_report,
    }

    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(run_summary, fh, indent=2)

    if positions_df.empty:
        print("No positions were extracted. Check the team filter, metadata, or selected game ids.")
    else:
        print(f"Saved: {positions_csv}")
        print(f"Saved: {summary_csv}")
        print(f"Saved: {per_game_csv}")
        print(f"Saved: {heatmap_png}")
        print(f"Saved: {overview_png}")
        print(f"Frames used: {run_summary['unique_frames']}")
        print(f"Players used: {run_summary['unique_players']}")
        if used_fallback_to_all_players:
            print(
                "Warning: Barcelona player ids could not be identified from match metadata in at least one game; "
                "all tracked players were used for those frames because --fallback-to-all-players was enabled."
            )

    return run_summary


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a Barcelona corner-reception positional overview and heatmap from SkillCorner packages."
    )
    parser.add_argument(
        "--dataset-root",
        required=True,
        help="Root directory containing SkillCorner game folders and/or game_id.zip files.",
    )
    parser.add_argument(
        "--team",
        default="Barcelona",
        help="Team name keyword used to identify the target team (default: Barcelona).",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where CSVs, plots, and summary JSON will be written.",
    )
    parser.add_argument(
        "--game-ids",
        default="",
        help="Optional comma-separated list of game ids to process. By default all discovered games are used.",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Do not normalize corners to the same attacking corner. By default x/y are flipped so every corner points to the same corner quadrant.",
    )
    parser.add_argument(
        "--detected-only",
        action="store_true",
        help="Use only players with is_detected=True in the tracking frame.",
    )
    parser.add_argument(
        "--fallback-to-all-players",
        action="store_true",
        help="If Barcelona players cannot be identified from metadata, use all players in the selected frames instead of returning no positions.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
