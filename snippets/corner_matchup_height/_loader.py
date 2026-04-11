"""Shared loader for the ``corner_matchup_height`` snippet.

Streams StatsBomb event JSONs *and* lineup JSONs out of the ZIP
archives in ``data/statsbomb/`` and, for each focus-team match, builds:

1. the top-6 mean outfield-player height for the focus team and the
   opponent (``focus_top6`` / ``opp_top6``), and
2. the focus team's corner deliveries with zone classification, from
   which we derive the per-match *far-post share*.

The whole pipeline only depends on the Python stdlib so the snippet
folder can be copied into another repo unchanged.

All paths are CWD-relative: callers are expected to run the scripts
from the project root (the directory that contains ``data/``).
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

STATSBOMB_DIR = Path("data/statsbomb")
MATCHES_CSV = Path("data/matches.csv")

# last16.zip ships WITHOUT lineup files, so matches from that phase
# will be dropped when we try to compute their top-6 height profile.
# That's deliberate and matches the wiki numbers.
EVENT_ZIPS = ("league_phase.zip", "last16.zip", "playoffs.zip")
LINEUP_ZIPS = ("league_phase.zip", "playoffs.zip")

TOP_N_HEIGHT = 6
SHORT_CORNER_MAX_LEN = 15.0
SEQUENCE_MAX_SECONDS = 20.0

# StatsBomb v8 type IDs
PASS_TYPE_ID = 30
SHOT_TYPE_ID = 16

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


# ── Raw JSON loading ──────────────────────────────────────────────────


def _read_matches_csv(csv_path: Path = MATCHES_CSV) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return rows


def _load_events(match_id: str, statsbomb_dir: Path = STATSBOMB_DIR) -> list[dict] | None:
    target = f"{match_id}.json"
    for zname in EVENT_ZIPS:
        zp = statsbomb_dir / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def _load_lineup(match_id: str, statsbomb_dir: Path = STATSBOMB_DIR) -> list[dict] | None:
    target = f"{match_id}_lineups.json"
    for zname in LINEUP_ZIPS:
        zp = statsbomb_dir / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


# ── Lineup helpers ────────────────────────────────────────────────────


def _is_goalkeeper(player: dict) -> bool:
    return any(
        "Goalkeeper" in pos.get("position", "")
        for pos in player.get("positions", [])
    )


def _actually_played(player: dict) -> bool:
    """Non-empty ``positions`` list ⇒ player took the pitch."""
    return len(player.get("positions", [])) > 0


def _outfield_heights(players: list[dict]) -> list[float]:
    return [
        float(p["player_height"])
        for p in players
        if _actually_played(p) and not _is_goalkeeper(p) and p.get("player_height")
    ]


def _top_n_mean(heights: list[float], n: int = TOP_N_HEIGHT) -> float | None:
    top = sorted(heights, reverse=True)[:n]
    if len(top) < n:
        return None
    return sum(top) / n


def _match_height_profile(
    lineup: list[dict], focus_team: str
) -> tuple[float | None, float | None]:
    """Return ``(focus_top6, opp_top6)`` from a 2-team lineup payload.

    Exact-match lookup: we require *focus_team* to appear verbatim
    as one of the two ``team_name`` entries in the lineup JSON.
    """
    if not lineup or len(lineup) != 2:
        return None, None
    sb_names = [td.get("team_name", "") for td in lineup]
    if focus_team not in sb_names:
        return None, None
    focus_idx = sb_names.index(focus_team)
    opp_idx = 1 - focus_idx
    focus_h = _top_n_mean(_outfield_heights(lineup[focus_idx].get("lineup", [])))
    opp_h = _top_n_mean(_outfield_heights(lineup[opp_idx].get("lineup", [])))
    return focus_h, opp_h


# ── Event helpers ─────────────────────────────────────────────────────


def _is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == PASS_TYPE_ID


def _is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == SHOT_TYPE_ID


def _is_corner_pass(e: dict) -> bool:
    return _is_pass(e) and e.get("pass", {}).get("type", {}).get("name") == "Corner"


def _by_team(e: dict, team_sb: str) -> bool:
    return e.get("team", {}).get("name") == team_sb


def _event_time_seconds(event: dict) -> float:
    ts = event.get("timestamp", "")
    if ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


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
    """For direct corners, the corner itself. For short corners, walk
    forward until we find a same-team shot or a long enough pass that
    actually delivers the ball into the area."""
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
        if (
            end[0] >= 96
            or loc[0] >= 105
            or float(event.get("pass", {}).get("length", 0.0) or 0.0) >= 12
        ):
            return event
    return corner


def _classify_zone(loc: tuple[float, float] | None) -> str:
    """Same boundaries as ``src/offense/barcelona_offensive_corners.py``."""
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


def _flip_location(
    loc: list[float] | None, flip_y: bool
) -> tuple[float, float] | None:
    """Mirror the y-axis so that corners from either side land in the
    same half of the pitch for zone classification."""
    if not loc or len(loc) < 2:
        return None
    x, y = float(loc[0]), float(loc[1])
    if flip_y:
        y = 80.0 - y
    return x, y


def _delivery_endpoint(
    delivery: dict | None, flip_y: bool
) -> tuple[float, float] | None:
    if delivery is None:
        return None
    if _is_pass(delivery):
        end = delivery.get("pass", {}).get("end_location")
    else:
        end = delivery.get("location")
    return _flip_location(end, flip_y)


def _team_in_events(team: str, events: list[dict]) -> str | None:
    """Return *team* if it appears verbatim as any event team name."""
    for e in events:
        if e.get("team", {}).get("name") == team:
            return team
    return None


def _opponent_csv(row: dict, focus_team: str) -> str:
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    return away if home == focus_team else home


# ── Public API ────────────────────────────────────────────────────────


def collect_match_rows(focus_team: str = "Barcelona") -> list[dict]:
    """Return per-match rows for *focus_team*'s corner deliveries.

    Each entry has the keys::

        label            e.g. "vs Newcastle United"
        opponent         "Newcastle United"
        match_id         "4028847"
        focus_top6       mean top-6 outfield height, cm
        opp_top6         mean top-6 outfield height, cm
        height_gap       opp_top6 − focus_top6  (positive ⇒ opponent taller)
        n_corners        total focus-team corners in the match
        far_post         corners whose meaningful delivery landed in Far post
        far_post_share   far_post / n_corners  (NaN if n_corners == 0)

    Matches where the lineup file is missing (e.g. Round of 16), where
    the focus team / opponent height profile can't be computed, or
    where the focus team took no corners at all (far-post share
    undefined) are silently skipped — consistent with the wiki numbers.
    """
    out: list[dict] = []
    for row in _read_matches_csv():
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        home = row.get("home", "").strip()
        away = row.get("away", "").strip()
        if focus_team not in (home, away):
            continue

        events = _load_events(match_id)
        if events is None:
            continue
        # Exact-match only: focus team's CSV name must appear in events.
        team_sb = _team_in_events(focus_team, events)
        if team_sb is None:
            continue

        lineup = _load_lineup(match_id)
        if lineup is None:
            continue
        focus_h, opp_h = _match_height_profile(lineup, focus_team)
        if focus_h is None or opp_h is None:
            continue

        n_corners = 0
        far_post = 0
        for idx, event in enumerate(events):
            if not (_is_corner_pass(event) and _by_team(event, team_sb)):
                continue
            sequence = _sequence_events(events, idx)
            delivery = _meaningful_delivery(sequence, team_sb)
            if delivery is None:
                continue
            # Flip y so deliveries from the top of the pitch mirror
            # into the same half as deliveries from the bottom, then
            # classify using the shared zone boundaries.
            corner_loc = event.get("location")
            flip_y = bool(corner_loc and corner_loc[1] > 40)
            endpoint = _delivery_endpoint(delivery, flip_y)
            zone = _classify_zone(endpoint)
            n_corners += 1
            if zone == "Far post":
                far_post += 1

        if n_corners == 0:
            # Match with no corners has an undefined far-post share
            # (0/0) — skip, matching the source script's behaviour.
            continue
        share = far_post / n_corners
        out.append({
            "label": f"vs {_opponent_csv(row, focus_team)}",
            "opponent": _opponent_csv(row, focus_team),
            "match_id": match_id,
            "focus_top6": focus_h,
            "opp_top6": opp_h,
            "height_gap": opp_h - focus_h,
            "n_corners": n_corners,
            "far_post": far_post,
            "far_post_share": share,
        })

    return out


def abbr(label: str) -> str:
    """Turn ``"vs Newcastle United"`` into ``"NU"``, etc. Matches the
    ``_abbr`` helper in ``src/offense/barcelona_offensive_corners.py``."""
    tokens = [tok for tok in label.replace("vs ", "").split() if tok]
    if not tokens:
        return label
    if len(tokens) == 1:
        return tokens[0][:4]
    return "".join(tok[0] for tok in tokens[:3]).upper()
