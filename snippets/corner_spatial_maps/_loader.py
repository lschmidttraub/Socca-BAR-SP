"""Shared loader for the ``corner_spatial_maps`` snippet.

Reads ``data/matches.csv`` and streams StatsBomb match JSONs out of the
three ZIP archives in ``data/statsbomb/``. For every focus-team corner
it extracts the corner-pass, the first *meaningful delivery*, the first
shot and the first team touch after the corner, recorded as one rich
dict per corner sequence.

Every helper here is self-contained — no imports from the project's
``src/stats`` library — so the whole ``corner_spatial_maps`` folder
can be dropped into another repo that follows the same data layout.

All paths are CWD-relative: callers are expected to run the plot
scripts from the project root (the directory that contains ``data/``).

Spelling drift note: a handful of UCL teams (PSG, Bayern München,
Monaco, Leverkusen, Dortmund) are spelled differently in
``matches.csv`` vs. the StatsBomb event feed. This loader uses
exact-match team-name resolution only (no fuzzy matching), so those
teams fall through when they are not the focus team. Barcelona's own
spelling is stable, so the output for ``focus_team="Barcelona"`` is
unaffected.
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any, Iterator

# ── Paths (CWD-relative — run scripts from the project root) ────────
DATA_DIR = Path("data")
STATSBOMB_DIR = DATA_DIR / "statsbomb"
MATCHES_CSV = DATA_DIR / "matches.csv"
ZIP_NAMES = ("league_phase.zip", "last16.zip", "playoffs.zip")

# ── Sequence-extraction constants (match src/offense/…) ─────────────
SHORT_CORNER_MAX_LEN = 15.0
SEQUENCE_MAX_SECONDS = 20.0

# ── Event-type ids from the StatsBomb v8 schema ─────────────────────
PASS_TYPE_ID = 30
SHOT_TYPE_ID = 16


# ── Plot-wide styling constants (copied from the source so the plot
# scripts stay self-contained) ──────────────────────────────────────
ROUTINE_ORDER = [
    "Direct inswing",
    "Direct outswing",
    "Direct other",
    "Short corner",
]

ZONE_ORDER = [
    "Near post",
    "Central six-yard",
    "Far post",
    "Penalty spot",
    "Edge of box",
    "Wide recycle",
]

# Focus colour + the rest of the offensive-corners palette
FOCUS_COLOR = "#a50026"
AVG_COLOR = "#f4a261"

ROUTINE_COLORS: dict[str, str] = {
    "Direct inswing": FOCUS_COLOR,
    "Direct outswing": "#f28e2b",
    "Direct other": "#8c6bb1",
    "Short corner": AVG_COLOR,
}

ZONE_COLORS: dict[str, str] = {
    "Near post": "#d73027",
    "Central six-yard": "#fc8d59",
    "Far post": "#4575b4",
    "Penalty spot": "#66bd63",
    "Edge of box": "#984ea3",
    "Wide recycle": "#878787",
}

FIRST_TOUCH_COLORS: dict[str, str] = {
    "Shot": "#ff4d6d",
    "Pass": "#3b82f6",
    "Carry": "#ffd43b",
}

DARK_FIG_COLOR = "#0a2512"
DARK_PITCH_COLOR = "#2f6f31"
DARK_LINE_COLOR = "#f5f5f5"


# ── StatsBomb I/O ───────────────────────────────────────────────────


def _read_matches_csv(csv_path: Path = MATCHES_CSV) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _index_phases(statsbomb_dir: Path = STATSBOMB_DIR) -> dict[str, str]:
    """Return ``{match_id: phase}`` for every match-JSON in the ZIPs."""
    phase_by_id: dict[str, str] = {}
    for zname in ZIP_NAMES:
        zp = statsbomb_dir / zname
        if not zp.is_file():
            continue
        phase = zname.replace(".zip", "")
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                base = n.rsplit("/", 1)[-1]
                if base.endswith(".json") and not base.endswith("_lineups.json"):
                    phase_by_id[base.removesuffix(".json")] = phase
    return phase_by_id


def _load_events(statsbomb_dir: Path, match_id: str) -> list[dict] | None:
    """Load the events JSON for *match_id* from whichever ZIP contains it."""
    target = f"{match_id}.json"
    for zname in ZIP_NAMES:
        zp = statsbomb_dir / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def iter_matches(
    statsbomb_dir: Path = STATSBOMB_DIR,
    matches_csv: Path = MATCHES_CSV,
) -> Iterator[tuple[dict, list[dict]]]:
    """Yield ``(row, events)`` pairs for every row in ``matches.csv``."""
    _ = _index_phases(statsbomb_dir)  # ensures the dir is real
    for row in _read_matches_csv(matches_csv):
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        events = _load_events(statsbomb_dir, match_id)
        if events is None:
            continue
        yield row, events


# ── Event predicates (self-contained, no src/stats dependency) ──────


def _is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == PASS_TYPE_ID


def _is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == SHOT_TYPE_ID


def _pass_type_name(e: dict) -> str | None:
    return e.get("pass", {}).get("type", {}).get("name")


def _is_corner_pass(e: dict) -> bool:
    return _is_pass(e) and _pass_type_name(e) == "Corner"


def _by_team(e: dict, team: str) -> bool:
    return e.get("team", {}).get("name", "") == team


def _shot_xg(e: dict) -> float:
    return float(e.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)


def _event_player(e: dict) -> str:
    return e.get("player", {}).get("name", "")


def _event_type_name(e: dict) -> str:
    return e.get("type", {}).get("name", "")


def _is_carry(e: dict) -> bool:
    return _event_type_name(e) == "Carry"


def _is_actionable(e: dict) -> bool:
    return _is_pass(e) or _is_shot(e) or _is_carry(e)


def _action_kind(e: dict) -> str | None:
    if _is_shot(e):
        return "Shot"
    if _is_pass(e):
        return "Pass"
    if _is_carry(e):
        return "Carry"
    return None


# ── Team-name resolution (exact match only) ─────────────────────────


def _team_in_match(team: str, row: dict, events: list[dict]) -> str | None:
    """Return *team* verbatim if it appears as an event ``team.name``.

    Exact-match lookup only — no fuzzy matching. A miss means the team's
    CSV spelling differs from its event spelling (see module docstring)
    so callers simply skip the (team, match) pair.
    """
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    if team not in (home, away):
        return None
    for e in events:
        if e.get("team", {}).get("name") == team:
            return team
    return None


def _team_label(row: dict, team: str) -> str:
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    if team == home:
        return away
    if team == away:
        return home
    return away if team in home else home


# ── Coordinate helpers (match the original source exactly) ──────────


def _event_time_seconds(event: dict) -> float:
    ts = event.get("timestamp", "")
    if ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def _flip_location(
    loc: list[float] | None, flip_y: bool
) -> tuple[float, float] | None:
    if not loc or len(loc) < 2:
        return None
    x, y = float(loc[0]), float(loc[1])
    if flip_y:
        y = 80.0 - y
    return x, y


def _clip_to_pitch(
    loc: tuple[float, float] | None,
) -> tuple[float, float] | None:
    if loc is None:
        return None
    x, y = loc
    return max(60.0, min(120.0, x)), max(0.0, min(80.0, y))


def _event_end_location(
    event: dict, flip_y: bool
) -> tuple[float, float] | None:
    end = None
    if _is_pass(event):
        end = event.get("pass", {}).get("end_location")
    elif _is_carry(event):
        end = event.get("carry", {}).get("end_location")
    elif _is_shot(event):
        end = event.get("shot", {}).get("end_location")
    return _clip_to_pitch(_flip_location(end, flip_y))


# ── Sequence extraction ─────────────────────────────────────────────


def _sequence_events(events: list[dict], start_idx: int) -> list[dict]:
    start = events[start_idx]
    possession = start.get("possession")
    period = start.get("period")
    t0 = _event_time_seconds(start)
    seq = [start]

    for event in events[start_idx + 1:]:
        if event.get("period") != period or event.get("possession") != possession:
            break
        if _event_time_seconds(event) - t0 > SEQUENCE_MAX_SECONDS:
            break
        seq.append(event)

    return seq


def _routine_type(corner: dict) -> str:
    length = float(corner.get("pass", {}).get("length", 0.0) or 0.0)
    if length <= SHORT_CORNER_MAX_LEN:
        return "Short corner"

    technique = corner.get("pass", {}).get("technique", {}).get("name")
    inswing = corner.get("pass", {}).get("inswinging")
    if inswing is True or technique == "Inswinging":
        return "Direct inswing"
    if inswing is False or technique == "Outswinging":
        return "Direct outswing"
    return "Direct other"


def _meaningful_delivery(sequence: list[dict], team_sb: str) -> dict | None:
    corner = sequence[0]
    if _routine_type(corner) != "Short corner":
        return corner

    for event in sequence[1:]:
        if not _by_team(event, team_sb):
            continue
        if _is_shot(event):
            return event
        if not _is_pass(event):
            continue
        loc = event.get("location")
        end = event.get("pass", {}).get("end_location")
        if not loc or not end:
            continue
        length = float(event.get("pass", {}).get("length", 0.0) or 0.0)
        if end[0] >= 96 or loc[0] >= 105 or length >= 12:
            return event

    return corner


def _classify_zone(loc: tuple[float, float] | None) -> str:
    if loc is None:
        return "Wide recycle"
    x, y = loc
    if x >= 114 and y < 33:
        return "Near post"
    if x >= 114 and y > 47:
        return "Far post"
    if x >= 114:
        return "Central six-yard"
    if x >= 102 and 28 <= y <= 52:
        return "Penalty spot"
    if x >= 96:
        return "Edge of box"
    return "Wide recycle"


def _first_touch_after_corner(
    sequence: list[dict],
    team_sb: str,
    flip_y: bool,
) -> dict[str, Any] | None:
    tracked_types = {
        "Ball Receipt*",
        "Ball Recovery",
        "Carry",
        "Dribble",
        "Duel",
        "Pass",
        "Shot",
    }

    first_touch = None
    first_idx = None
    for idx, event in enumerate(sequence[1:], start=1):
        if not _by_team(event, team_sb):
            continue
        if _event_type_name(event) not in tracked_types:
            continue
        if not event.get("location"):
            continue
        first_touch = event
        first_idx = idx
        break

    if first_touch is None or first_idx is None:
        return None

    action_event = first_touch if _is_actionable(first_touch) else None
    if action_event is None:
        for event in sequence[first_idx + 1:]:
            if not _by_team(event, team_sb):
                continue
            if _is_actionable(event):
                action_event = event
                break

    if action_event is None:
        return None

    start = _clip_to_pitch(_flip_location(first_touch.get("location"), flip_y))
    if start is None:
        start = _clip_to_pitch(_flip_location(action_event.get("location"), flip_y))
    end = _event_end_location(action_event, flip_y)
    kind = _action_kind(action_event)
    if start is None or kind is None:
        return None

    return {
        "start": start,
        "end": end,
        "kind": kind,
        "player": _event_player(action_event) or "Unknown",
    }


def _first_shot_in_sequence(
    sequence: list[dict], team_sb: str
) -> dict | None:
    for event in sequence[1:]:
        if _by_team(event, team_sb) and _is_shot(event):
            return event
    return None


# ── Public entry point ──────────────────────────────────────────────


def collect_corner_sequences(focus_team: str = "Barcelona") -> list[dict]:
    """Return one rich dict per *focus_team* corner across all matches.

    Each dict carries the fields needed by all three plot scripts in
    this snippet folder: corner side, routine type, delivery zone,
    delivery start/end coordinates (y-flipped so every corner lives on
    the same side of the pitch), first-shot location + xG, and the
    first-touch after the corner (location, end location and kind).
    """
    sequences: list[dict] = []

    for row, events in iter_matches():
        team_sb = _team_in_match(focus_team, row, events)
        if team_sb is None:
            continue

        opponent = _team_label(row, focus_team)

        for idx, event in enumerate(events):
            if not (_is_corner_pass(event) and _by_team(event, team_sb)):
                continue

            sequence = _sequence_events(events, idx)
            delivery = _meaningful_delivery(sequence, team_sb)
            first_shot = _first_shot_in_sequence(sequence, team_sb)

            # flip_y ensures every corner ends up on the "bottom"
            # (y close to 0) half of the pitch, so the 3-panel
            # spatial_profile can draw them all together.
            flip_y = bool(event.get("location") and event["location"][1] > 40)

            corner_start = _flip_location(event.get("location"), flip_y)
            corner_end = _flip_location(
                event.get("pass", {}).get("end_location"), flip_y
            )
            delivery_start = (
                _flip_location(delivery.get("location"), flip_y)
                if delivery
                else None
            )
            delivery_end = None
            if delivery is not None:
                if _is_pass(delivery):
                    delivery_end = _flip_location(
                        delivery.get("pass", {}).get("end_location"), flip_y
                    )
                else:
                    delivery_end = _flip_location(delivery.get("location"), flip_y)

            first_shot_loc = (
                _flip_location(first_shot.get("location"), flip_y)
                if first_shot
                else None
            )
            first_shot_xg = _shot_xg(first_shot) if first_shot else 0.0

            first_touch = _first_touch_after_corner(sequence, team_sb, flip_y)

            sequences.append(
                {
                    "match_id": row.get("statsbomb", "").strip(),
                    "opponent": opponent,
                    "minute": int(event.get("minute", 0)),
                    "corner_taker": _event_player(event) or "Unknown",
                    # "bottom" = corner was taken from y ≤ 40 originally
                    # "top" = corner was taken from y > 40 originally
                    "corner_side": "top" if flip_y else "bottom",
                    "routine_type": _routine_type(event),
                    "corner_length": float(
                        event.get("pass", {}).get("length", 0.0) or 0.0
                    ),
                    "delivery_zone": _classify_zone(delivery_end),
                    "corner_start_x": corner_start[0] if corner_start else None,
                    "corner_start_y": corner_start[1] if corner_start else None,
                    "corner_end_x": corner_end[0] if corner_end else None,
                    "corner_end_y": corner_end[1] if corner_end else None,
                    "delivery_start_x": delivery_start[0] if delivery_start else None,
                    "delivery_start_y": delivery_start[1] if delivery_start else None,
                    "delivery_end_x": delivery_end[0] if delivery_end else None,
                    "delivery_end_y": delivery_end[1] if delivery_end else None,
                    "first_shot_x": first_shot_loc[0] if first_shot_loc else None,
                    "first_shot_y": first_shot_loc[1] if first_shot_loc else None,
                    "first_shot_xg": first_shot_xg,
                    "first_touch_kind": first_touch["kind"] if first_touch else "",
                    "first_touch_player": first_touch["player"] if first_touch else "",
                    "first_touch_x": (
                        first_touch["start"][0] if first_touch else None
                    ),
                    "first_touch_y": (
                        first_touch["start"][1] if first_touch else None
                    ),
                    "first_touch_end_x": (
                        first_touch["end"][0]
                        if first_touch and first_touch["end"]
                        else None
                    ),
                    "first_touch_end_y": (
                        first_touch["end"][1]
                        if first_touch and first_touch["end"]
                        else None
                    ),
                }
            )

    return sequences


# ── Side-subset helper (used by the two dark-themed by-side plots) ──


def iter_side_subsets(
    sequences: list[dict],
) -> list[tuple[str, list[dict]]]:
    """Return ``[("bottom", …), ("top", …)]`` subsets by ``corner_side``.

    The two by-side plots render each subset on its own axis, with
    ``"bottom"`` labelled "Left-side corner" and ``"top"`` labelled
    "Right-side corner".
    """
    return [
        (side, [seq for seq in sequences if seq["corner_side"] == side])
        for side in ("bottom", "top")
    ]


def side_title(side: str) -> str:
    return "Left-side corner" if side == "bottom" else "Right-side corner"


def display_point(
    point: tuple[float | None, float | None] | None,
    side: str,
) -> tuple[float, float] | None:
    """Mirror *point* to the correct side for the by-side plots.

    The loader stores delivery/first-touch coordinates already y-flipped
    for the 3-panel spatial-profile view. For the by-side plots we want
    to display each corner on its original side, so top-side corners
    must be un-flipped (mirror y about the pitch centre).
    """
    if point is None:
        return None
    x, y = point
    if x is None or y is None:
        return None
    if side == "top":
        return float(x), 80.0 - float(y)
    return float(x), float(y)
