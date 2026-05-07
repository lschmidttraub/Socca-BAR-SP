"""Barcelona player movement during the goal vs Newcastle United (min 17).

Three-panel figure (starts → paths → ends) showing how Barcelona
outfield players moved in a pre-goal build-up window, using SkillCorner
tracking data combined with StatsBomb event data.

Run from the project root:
    python snippets/goal_movement/goal_movement.py
"""

from __future__ import annotations

import csv
import io
import json
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from mplsoccer import Pitch


# ── Paths (CWD-relative; run from project root) ──────────────────────

DATA_DIR = Path("data")
MATCHES_CSV = DATA_DIR / "matches.csv"
STATSBOMB_DIR = DATA_DIR / "statsbomb"
SKILLCORNER_DIR = DATA_DIR / "skillcorner"
STATSBOMB_ZIPS = ("league_phase.zip", "last16.zip", "playoffs.zip")
OUTPUT_DIR = Path("assets") / "offensive_goal_movement"


# ── Analysis parameters ──────────────────────────────────────────────

TEAM = "Barcelona"
OPPONENT = "Newcastle United"
GOAL_MINUTE = 17
PRE_SECONDS = 7.0
POST_SECONDS = 1.5
MEAN_PATH_SAMPLES = 30

FOCUS_COLOR = "#a50026"
NEUTRAL_COLOR = "#878787"
SCORER_COLOR = "#2ca02c"
BALL_COLOR = "#ffcc00"


# ── CSV team name normalization ──────────────────────────────────────

_CSV_TO_STATSBOMB: dict[str, str] = {
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
    for old, new in _CSV_TO_STATSBOMB.items():
        name = name.replace(old, new)
    return name


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
class GoalWindow:
    statsbomb_match_id: str
    skillcorner_match_id: str
    opponent: str
    period: int
    goal_time: float
    scorer: str
    scorer_id: int | None
    barca_tracks: dict[int, list[TrackSample]] = field(
        default_factory=lambda: defaultdict(list),
    )
    ball_track: list[TrackSample] = field(default_factory=list)


# ── Small helpers ────────────────────────────────────────────────────


def _parse_tracking_timestamp(timestamp: str) -> float:
    hh, mm, ss = timestamp.split(":")
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    return float(value)


def _event_time_seconds(event: dict) -> float:
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def _format_clock(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 60:02d}:{total % 60:02d}"


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


def _normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


# ── Match and event loading ──────────────────────────────────────────


def _find_match_rows(opponent: str) -> list[dict]:
    """Return all matches.csv rows for Barcelona vs opponent with SkillCorner data."""
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    matches = []
    for row in rows:
        if not row.get("skillcorner"):
            continue
        home = _normalise_team(row.get("home", ""))
        away = _normalise_team(row.get("away", ""))
        barca_present = TEAM in (home, away)
        opp_present = opponent in (home, away) or any(
            opponent.lower() in t.lower() for t in (home, away)
        )
        if barca_present and opp_present:
            row["home"] = home
            row["away"] = away
            matches.append(row)
    return matches


def _load_statsbomb_events(match_id: str) -> list[dict] | None:
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


def _find_goal_event(events: list[dict], minute: int) -> dict | None:
    """Return the first Barcelona goal at or near the given minute (±2 min)."""
    for event in events:
        if event.get("type", {}).get("id") != 16:
            continue
        if event.get("team", {}).get("name") != TEAM:
            continue
        if event.get("shot", {}).get("outcome", {}).get("name") != "Goal":
            continue
        if abs(event.get("minute", 0) - minute) <= 2:
            return event
    return None


# ── SkillCorner loading ──────────────────────────────────────────────


def _load_skillcorner_meta(
    zip_path: Path, match_id: str,
) -> tuple[dict, dict[int, PlayerInfo], int]:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}.json") as fh:
            meta = json.load(io.TextIOWrapper(fh, encoding="utf-8"))

    players: dict[int, PlayerInfo] = {}
    for player in meta["players"]:
        role = player.get("player_role", {}) or {}
        full_name = " ".join(
            p for p in [player.get("first_name"), player.get("last_name")] if p
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
    return meta, players, barca_team_id


def _extract_goal_window(
    zip_path: Path,
    match_id: str,
    window: GoalWindow,
    meta: dict,
    players: dict[int, PlayerInfo],
    barca_team_id: int,
) -> None:
    """Fill window.barca_tracks and window.ball_track from SkillCorner JSONL."""
    pitch_length = float(meta["pitch_length"])
    pitch_width = float(meta["pitch_width"])

    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(f"{match_id}_tracking_extrapolated.jsonl") as fh:
            for line in io.TextIOWrapper(fh, encoding="utf-8"):
                frame = json.loads(line)
                timestamp = frame.get("timestamp")
                period = frame.get("period")
                if timestamp is None or period is None:
                    continue
                time_sec = _parse_tracking_timestamp(timestamp)
                if int(period) != window.period:
                    continue
                lo = window.goal_time - PRE_SECONDS
                hi = window.goal_time + POST_SECONDS
                if not (lo <= time_sec <= hi):
                    continue

                attack_right = _team_attacks_right(meta, barca_team_id, window.period)
                t_rel = time_sec - window.goal_time

                for player in frame.get("player_data", []):
                    player_id = int(player["player_id"])
                    info = players.get(player_id)
                    x = _safe_float(player.get("x"))
                    y = _safe_float(player.get("y"))
                    if info is None or x is None or y is None:
                        continue
                    if info.team_id != barca_team_id:
                        continue
                    x_mpl, y_mpl = _skillcorner_to_mpl(
                        x, y,
                        pitch_length=pitch_length,
                        pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    window.barca_tracks[player_id].append(
                        TrackSample(t_rel, x_mpl, y_mpl),
                    )

                ball = frame.get("ball_data", {}) or {}
                bx = _safe_float(ball.get("x"))
                by = _safe_float(ball.get("y"))
                if bx is not None and by is not None:
                    bx_mpl, by_mpl = _skillcorner_to_mpl(
                        bx, by,
                        pitch_length=pitch_length,
                        pitch_width=pitch_width,
                        attack_right=attack_right,
                    )
                    window.ball_track.append(TrackSample(t_rel, bx_mpl, by_mpl))


# ── Track processing ─────────────────────────────────────────────────


def _nearest_sample(samples: list[TrackSample], target_t: float) -> TrackSample | None:
    if not samples:
        return None
    return min(samples, key=lambda s: abs(s.t_rel - target_t))


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


def _find_scorer_id(scorer_name: str, players: dict[int, PlayerInfo]) -> int | None:
    """Match StatsBomb scorer name to a SkillCorner player_id."""
    norm = _normalize_name(scorer_name)
    for player_id, info in players.items():
        if _normalize_name(info.name) == norm:
            return player_id
        if _normalize_name(info.short_name) == norm:
            return player_id
    # Fallback: last-name match
    tokens = norm.split()
    if tokens:
        last = tokens[-1]
        for player_id, info in players.items():
            sc_tokens = _normalize_name(info.short_name).split()
            if sc_tokens and sc_tokens[-1] == last:
                return player_id
    return None


def _build_player_paths(
    window: GoalWindow, players: dict[int, PlayerInfo],
) -> list[dict[str, Any]]:
    """Build interpolated movement paths for all Barcelona outfield players."""
    n_samples = max(MEAN_PATH_SAMPLES, int(round((PRE_SECONDS + POST_SECONDS) * 10)))
    sample_times = np.linspace(-PRE_SECONDS, POST_SECONDS, n_samples)

    paths: list[dict[str, Any]] = []
    for player_id, samples in window.barca_tracks.items():
        info = players.get(player_id)
        if info is None or info.is_goalkeeper:
            continue
        start = _nearest_sample(samples, -PRE_SECONDS)
        end = _nearest_sample(samples, POST_SECONDS)
        if start is None or end is None:
            continue
        path = _resample_track(samples, sample_times)
        if path is None:
            continue
        paths.append({
            "player_id": player_id,
            "name": info.short_name,
            "role": info.role or info.position_group,
            "start": (start.x, start.y),
            "end": (end.x, end.y),
            "path": path,
            "is_scorer": player_id == window.scorer_id,
        })
    return paths


def _build_ball_path(window: GoalWindow) -> np.ndarray | None:
    samples = sorted(window.ball_track, key=lambda s: s.t_rel)
    if len(samples) < 2:
        return None
    n_samples = max(MEAN_PATH_SAMPLES, int(round((PRE_SECONDS + POST_SECONDS) * 10)))
    sample_times = np.linspace(-PRE_SECONDS, POST_SECONDS, n_samples)
    times = np.array([s.t_rel for s in samples])
    xs = np.array([s.x for s in samples])
    ys = np.array([s.y for s in samples])
    x_interp = np.interp(sample_times, times, xs, left=np.nan, right=np.nan)
    y_interp = np.interp(sample_times, times, ys, left=np.nan, right=np.nan)
    return np.column_stack([x_interp, y_interp])


# ── Plotting ─────────────────────────────────────────────────────────


def _apply_theme() -> None:
    mpl.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": NEUTRAL_COLOR,
        "axes.grid": False,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "xtick.color": NEUTRAL_COLOR,
        "ytick.color": NEUTRAL_COLOR,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "figure.dpi": 150,
    })


def _save_fig(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _draw_panel(
    ax: plt.Axes,
    pitch: Pitch,
    paths: list[dict[str, Any]],
    ball_path: np.ndarray | None,
    *,
    variant: str,
) -> None:
    pitch.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])

    for path_data in paths:
        arr = path_data["path"]
        mask = ~np.isnan(arr[:, 0]) & ~np.isnan(arr[:, 1])
        if mask.sum() < 2:
            continue
        xs = arr[mask, 0]
        ys = arr[mask, 1]
        is_scorer = path_data["is_scorer"]
        color = SCORER_COLOR if is_scorer else FOCUS_COLOR
        lw = 2.5 if is_scorer else 1.8
        zorder = 4 if is_scorer else 2

        if variant == "paths":
            pitch.lines(
                xs[:-1], ys[:-1], xs[1:], ys[1:], ax=ax,
                color=color, comet=False, transparent=True,
                alpha_start=0.25, alpha_end=0.9,
                lw=lw, zorder=zorder,
            )
            ax.annotate(
                "",
                xy=(xs[-1], ys[-1]),
                xytext=(xs[-2], ys[-2]),
                arrowprops={"arrowstyle": "-|>", "color": color, "lw": 1.8, "alpha": 0.95},
                zorder=zorder + 1,
            )
            if is_scorer:
                mid = len(xs) // 2
                ax.annotate(
                    path_data["name"],
                    xy=(xs[mid], ys[mid]),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=8, color=SCORER_COLOR, fontweight="bold", zorder=9,
                )

        if variant in {"starts", "paths"}:
            ax.scatter(
                [xs[0]], [ys[0]], s=50,
                color="white", edgecolors=color, linewidth=1.2, zorder=5,
            )

        if variant == "ends":
            ax.scatter(
                [xs[-1]], [ys[-1]], s=46,
                color=color, edgecolors="white", linewidth=0.8, zorder=5,
            )

        if is_scorer and variant in {"starts", "paths", "ends"}:
            pt_x = xs[-1] if variant != "starts" else xs[0]
            pt_y = ys[-1] if variant != "starts" else ys[0]
            ax.scatter(
                [pt_x], [pt_y], s=200, marker="*",
                color="#ffd166", edgecolors="#7a4c00", linewidth=0.9, zorder=8,
            )

    if ball_path is not None and variant == "paths":
        mask = ~np.isnan(ball_path[:, 0]) & ~np.isnan(ball_path[:, 1])
        if mask.sum() >= 2:
            bxs = ball_path[mask, 0]
            bys = ball_path[mask, 1]
            pitch.lines(
                bxs[:-1], bys[:-1], bxs[1:], bys[1:], ax=ax,
                color=BALL_COLOR, comet=False, transparent=True,
                alpha_start=0.4, alpha_end=0.95, lw=2.5, zorder=7,
            )

    ax.set_title(
        {
            "starts": f"01 Starts  |  t−{PRE_SECONDS:.1f}s",
            "paths": f"02 Paths  |  t−{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s",
            "ends": f"03 Ends  |  t+{POST_SECONDS:.1f}s",
        }[variant],
        fontsize=11.5, fontweight="bold", pad=10,
    )


def _plot_three_panel(
    window: GoalWindow,
    players: dict[int, PlayerInfo],
    output_path: Path,
) -> None:
    pitch = Pitch(
        pitch_type="statsbomb", half=False,
        pitch_color="white", line_color="#c7d5cc", linewidth=1.6,
    )
    fig, axes = plt.subplots(1, 3, figsize=(24.0, 7.5))
    fig.subplots_adjust(top=0.76, bottom=0.13, wspace=0.06)

    paths = _build_player_paths(window, players)
    ball_path = _build_ball_path(window)

    for ax, variant in zip(axes, ("starts", "paths", "ends")):
        _draw_panel(ax, pitch, paths, ball_path, variant=variant)

    scorer_label = f"  |  scored by {window.scorer}" if window.scorer else ""
    fig.suptitle(
        f"Barcelona player movement — Goal vs {window.opponent}",
        fontsize=17, fontweight="bold", y=0.995,
    )
    fig.text(
        0.5, 0.926,
        (
            f"{window.opponent}  |  {_format_clock(window.goal_time)}{scorer_label}  |  "
            f"{len(paths)} tracked outfield players  |  "
            f"window: t−{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s"
        ),
        ha="center", fontsize=10.4, color="#333333",
    )

    handles = [
        Line2D(
            [0], [0], marker="o", color="white",
            markeredgecolor=FOCUS_COLOR, markeredgewidth=1.2,
            markersize=7, lw=0, label=f"Start (t−{PRE_SECONDS:.1f}s)",
        ),
        Line2D([0], [0], color=FOCUS_COLOR, lw=2.5, label="Player movement"),
        Line2D(
            [0], [0], marker="o", color=FOCUS_COLOR,
            markeredgecolor="white", markeredgewidth=0.8,
            markersize=7, lw=0, label=f"End (t+{POST_SECONDS:.1f}s)",
        ),
        Line2D(
            [0], [0], marker="*", color="#ffd166",
            markeredgecolor="#7a4c00", markeredgewidth=0.9,
            markersize=11, lw=0, label="Goal scorer",
        ),
        Line2D([0], [0], color=BALL_COLOR, lw=2.5, label="Ball path"),
    ]
    fig.legend(
        handles=handles, loc="lower center",
        ncol=5, fontsize=9,
        frameon=True, fancybox=True, framealpha=0.92,
    )
    _save_fig(fig, output_path)
    print(f"Saved: {output_path}")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    _apply_theme()

    print(f"Finding Barcelona vs {OPPONENT} match(es) with goal near minute {GOAL_MINUTE}...")
    rows = _find_match_rows(OPPONENT)
    if not rows:
        print(f"ERROR: No matches with SkillCorner data found for Barcelona vs {OPPONENT}.")
        return

    row = None
    events = None
    goal_event = None
    for candidate in rows:
        statsbomb_id = candidate["statsbomb"].strip()
        evs = _load_statsbomb_events(statsbomb_id)
        if evs is None:
            continue
        ge = _find_goal_event(evs, GOAL_MINUTE)
        if ge is not None:
            row, events, goal_event = candidate, evs, ge
            break

    if row is None or goal_event is None:
        print(f"ERROR: No Barcelona goal found near minute {GOAL_MINUTE} in any match vs {OPPONENT}.")
        return

    statsbomb_id = row["statsbomb"].strip()
    skillcorner_id = row["skillcorner"].strip()
    print(f"  StatsBomb ID: {statsbomb_id}  |  SkillCorner ID: {skillcorner_id}")

    scorer_name = goal_event.get("player", {}).get("name", "Unknown")
    goal_time = _event_time_seconds(goal_event)
    period = goal_event.get("period", 1)
    print(f"  Goal by {scorer_name} at {_format_clock(goal_time)} (period {period})")

    zip_path = SKILLCORNER_DIR / f"{skillcorner_id}.zip"
    if not zip_path.is_file():
        print(f"ERROR: SkillCorner ZIP not found: {zip_path}")
        return

    print("Loading SkillCorner roster metadata...")
    meta, players, barca_team_id = _load_skillcorner_meta(zip_path, skillcorner_id)

    scorer_id = _find_scorer_id(scorer_name, players)
    print(f"  Scorer SkillCorner ID: {scorer_id}")

    window = GoalWindow(
        statsbomb_match_id=statsbomb_id,
        skillcorner_match_id=skillcorner_id,
        opponent=OPPONENT,
        period=period,
        goal_time=goal_time,
        scorer=scorer_name,
        scorer_id=scorer_id,
    )

    print(
        f"Streaming tracking data "
        f"(t-{PRE_SECONDS:.1f}s to t+{POST_SECONDS:.1f}s around goal)..."
    )
    _extract_goal_window(zip_path, skillcorner_id, window, meta, players, barca_team_id)

    n_players = len(window.barca_tracks)
    n_ball = len(window.ball_track)
    print(f"  {n_players} Barcelona player tracks  |  {n_ball} ball frames")

    if n_players == 0:
        print("ERROR: No tracking data found in the goal window.")
        return

    output_path = OUTPUT_DIR / f"goal_newcastle_{skillcorner_id}_min{GOAL_MINUTE}.png"
    print("Generating three-panel movement figure...")
    _plot_three_panel(window, players, output_path)
    print("Done.")


if __name__ == "__main__":
    main()
