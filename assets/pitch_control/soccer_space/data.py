"""SkillCorner tracking-data loader for the Fernandez & Bornn pipeline.

Reads the bundled zip files produced by the SkillCorner export. Each zip
contains:

    <match_id>.json                          — match metadata
    <match_id>_tracking_extrapolated.jsonl   — 10 Hz tracking, one frame/line

Velocity is not part of the raw tracking; it is computed here via a centred
finite difference over a configurable temporal half-window.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np


SAMPLE_HZ = 10.0           # SkillCorner extrapolated tracking rate
DT = 1.0 / SAMPLE_HZ


@dataclass
class MatchMeta:
    match_id: int
    home_team_id: int
    away_team_id: int
    player_team: dict[int, int]                 # player_id → team_id
    home_team_name: str
    away_team_name: str
    period_starts: dict[int, int]               # period → start_frame


def load_match_meta(zip_path: Path) -> MatchMeta:
    """Read match metadata from <match_id>.json inside the zip."""
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        json_name = [n for n in zf.namelist()
                     if n.endswith(".json") and "tracking" not in n][0]
        with zf.open(json_name) as fp:
            meta = json.load(fp)
    player_team = {p["id"]: p["team_id"] for p in meta["players"]}
    period_starts = {pp["period"]: pp["start_frame"]
                     for pp in meta["match_periods"]}
    return MatchMeta(
        match_id       = meta["id"],
        home_team_id   = meta["home_team"]["id"],
        away_team_id   = meta["away_team"]["id"],
        player_team    = player_team,
        home_team_name = meta["home_team"]["name"],
        away_team_name = meta["away_team"]["name"],
        period_starts  = period_starts,
    )


@dataclass
class Frame:
    frame: int
    period: int | None
    timestamp: str | None
    ball_xy: np.ndarray           # (2,)
    player_ids: np.ndarray        # (P,)
    player_xy:  np.ndarray        # (P, 2)
    possession_team: int | None   # team_id or None


def iter_frames(zip_path: Path) -> Iterator[Frame]:
    """Yield Frame instances one at a time from the JSONL inside the zip.

    Only well-formed frames (ball detected and 22 player rows) are emitted.
    """
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        jsonl_name = [n for n in zf.namelist()
                      if n.endswith("_tracking_extrapolated.jsonl")][0]
        with zf.open(jsonl_name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                if not line.strip():
                    continue
                d = json.loads(line)
                ball = d.get("ball_data") or {}
                bx, by = ball.get("x"), ball.get("y")
                if bx is None or by is None:
                    continue
                pdata = d.get("player_data") or []
                if not pdata:
                    continue
                ids = np.fromiter((p["player_id"] for p in pdata),
                                  dtype=np.int64, count=len(pdata))
                xs  = np.fromiter((p["x"] for p in pdata),
                                  dtype=np.float64, count=len(pdata))
                ys  = np.fromiter((p["y"] for p in pdata),
                                  dtype=np.float64, count=len(pdata))
                xy  = np.stack([xs, ys], axis=1)
                poss = (d.get("possession") or {}).get("group")
                yield Frame(
                    frame=d["frame"], period=d.get("period"),
                    timestamp=d.get("timestamp"),
                    ball_xy=np.array([bx, by], dtype=np.float64),
                    player_ids=ids, player_xy=xy,
                    possession_team=None  # filled in by caller using meta
                                          # because tracking only stores
                                          # home/away string.
                )


def possession_team_id(poss_group: str | None, meta: MatchMeta) -> int | None:
    if poss_group == "home team":
        return meta.home_team_id
    if poss_group == "away team":
        return meta.away_team_id
    return None


def iter_frames_with_meta(zip_path: Path) -> Iterator[tuple[Frame, MatchMeta]]:
    """Convenience wrapper that fills in possession_team and yields meta."""
    meta = load_match_meta(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        jsonl_name = [n for n in zf.namelist()
                      if n.endswith("_tracking_extrapolated.jsonl")][0]
        with zf.open(jsonl_name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                if not line.strip():
                    continue
                d = json.loads(line)
                ball = d.get("ball_data") or {}
                bx, by = ball.get("x"), ball.get("y")
                if bx is None or by is None:
                    continue
                pdata = d.get("player_data") or []
                if len(pdata) == 0:
                    continue
                ids = np.fromiter((p["player_id"] for p in pdata),
                                  dtype=np.int64, count=len(pdata))
                xs  = np.fromiter((p["x"] for p in pdata),
                                  dtype=np.float64, count=len(pdata))
                ys  = np.fromiter((p["y"] for p in pdata),
                                  dtype=np.float64, count=len(pdata))
                xy  = np.stack([xs, ys], axis=1)
                poss = (d.get("possession") or {}).get("group")
                f = Frame(
                    frame=d["frame"], period=d.get("period"),
                    timestamp=d.get("timestamp"),
                    ball_xy=np.array([bx, by], dtype=np.float64),
                    player_ids=ids, player_xy=xy,
                    possession_team=possession_team_id(poss, meta),
                )
                yield f, meta


def split_teams(frame: Frame, meta: MatchMeta
                ) -> tuple[np.ndarray, np.ndarray,
                           np.ndarray, np.ndarray]:
    """Return (home_ids, home_xy, away_ids, away_xy) for the frame."""
    teams = np.array([meta.player_team.get(int(pid), -1)
                      for pid in frame.player_ids])
    home_mask = teams == meta.home_team_id
    away_mask = teams == meta.away_team_id
    return (frame.player_ids[home_mask], frame.player_xy[home_mask],
            frame.player_ids[away_mask], frame.player_xy[away_mask])


# --- Velocity computation ---------------------------------------------------
def compute_velocity_buffer(positions_by_frame: dict[int, dict[int, np.ndarray]],
                            frame: int,
                            half_window: int = 3) -> dict[int, np.ndarray]:
    """Centred finite difference: v_i(t) ≈ (p_i(t+h) − p_i(t−h)) / (2 h Δt).

    Falls back to forward / backward differences when one side is missing.

    Parameters
    ----------
    positions_by_frame : nested dict, frame → {player_id → (x, y)}.
    frame              : target frame index.
    half_window        : h in frames (default 3 ⇒ 0.6 s window at 10 Hz).
    """
    forward  = positions_by_frame.get(frame + half_window, {})
    backward = positions_by_frame.get(frame - half_window, {})
    centre   = positions_by_frame.get(frame, {})
    out: dict[int, np.ndarray] = {}
    for pid, p0 in centre.items():
        pf = forward.get(pid); pb = backward.get(pid)
        if pf is not None and pb is not None:
            v = (pf - pb) / (2.0 * half_window * DT)
        elif pf is not None:
            v = (pf - p0) / (half_window * DT)
        elif pb is not None:
            v = (p0 - pb) / (half_window * DT)
        else:
            v = np.zeros(2, dtype=np.float64)
        out[pid] = v
    return out


def collect_window_buffer(zip_path: Path,
                          target_frames: set[int],
                          half_window: int = 3
                          ) -> dict[int, dict[int, np.ndarray]]:
    """Cache positions for every frame in target_frames ± half_window.

    Used by callers (training/inference) that need velocities at a small set
    of target frames without keeping the entire match in RAM.
    """
    needed = set()
    for f in target_frames:
        for k in range(-half_window, half_window + 1):
            needed.add(f + k)
    buf: dict[int, dict[int, np.ndarray]] = {}
    for f, _m in iter_frames_with_meta(zip_path):
        if f.frame in needed:
            buf[f.frame] = {int(pid): xy
                            for pid, xy in zip(f.player_ids, f.player_xy)}
    return buf
