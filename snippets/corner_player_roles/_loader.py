"""Shared event-loader and corner-sequence extractor for this snippet.

Reads ``data/matches.csv`` and streams StatsBomb event JSONs out of the
three zip archives in ``data/statsbomb/`` (``league_phase.zip``,
``last16.zip``, ``playoffs.zip``) without ever extracting them to disk,
then walks every corner restart pass belonging to the focus team and
returns one record per corner with the taker and the "delivery
receiver" — the player who eventually receives the meaningful delivery
once any short-corner manipulation phase is stripped away.

All paths are CWD-relative: run the scripts from the project root
(the directory that contains ``data/``). This file is self-contained
and has no dependency on ``src/stats``.
"""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

DATA_DIR = Path("data")
STATSBOMB_DIR = DATA_DIR / "statsbomb"
MATCHES_CSV = DATA_DIR / "matches.csv"

ZIP_NAMES = ("league_phase.zip", "last16.zip", "playoffs.zip")

# ── Corner sequence constants (mirrors src/offense/barcelona_offensive_corners.py) ──
SHORT_CORNER_MAX_LEN = 15.0
SEQUENCE_MAX_SECONDS = 20.0

# Meaningful-delivery thresholds for short-corner follow-ups
DELIVERY_END_X = 96.0       # pass end deep in the box
DELIVERY_LOC_X = 105.0      # pass origin already inside the 18-yard box
DELIVERY_MIN_LEN = 12.0     # pass length that counts as a real ball into the mixer

PASS_TYPE_ID = 30
SHOT_TYPE_ID = 16


# ── Match container ──────────────────────────────────────────────────


@dataclass
class Match:
    statsbomb_id: str
    date: str
    home: str
    away: str
    phase: str  # "league_phase" | "last16" | "playoffs" | "unknown"
    events: list[dict]


def _read_matches_csv(csv_path: Path = MATCHES_CSV) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _index_phases(statsbomb_dir: Path = STATSBOMB_DIR) -> dict[str, str]:
    """Return ``{match_id: phase}`` for every event JSON found in the ZIPs."""
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
    """Stream event JSON for *match_id* out of whichever ZIP contains it."""
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
) -> Iterator[Match]:
    """Yield one :class:`Match` per row in ``matches.csv`` (when events exist)."""
    phase_by_id = _index_phases(statsbomb_dir)
    for row in _read_matches_csv(matches_csv):
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        events = _load_events(statsbomb_dir, match_id)
        if events is None:
            continue
        yield Match(
            statsbomb_id=match_id,
            date=row.get("date", "").strip(),
            home=row.get("home", "").strip(),
            away=row.get("away", "").strip(),
            phase=phase_by_id.get(match_id, "unknown"),
            events=events,
        )


# ── Team-name resolution ──────────────────────────────────────────────
#
# Exact-match only. A handful of teams (PSG vs "Paris Saint-Germain",
# Bayern München vs "Bayern Munich", Monaco vs "AS Monaco", Leverkusen
# vs "Bayer Leverkusen", Dortmund vs "Borussia Dortmund") are spelled
# differently in matches.csv and StatsBomb events and are therefore
# silently skipped. Barcelona's spelling is identical in both sources,
# so this snippet's Barcelona numbers are unaffected.


def resolve_team_name(csv_team: str, match: Match) -> str | None:
    for e in match.events:
        if e.get("team", {}).get("name") == csv_team:
            return csv_team
    return None


# ── Event helpers ────────────────────────────────────────────────────


def _is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == PASS_TYPE_ID


def _is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == SHOT_TYPE_ID


def _is_corner_pass(e: dict) -> bool:
    return _is_pass(e) and e.get("pass", {}).get("type", {}).get("name") == "Corner"


def _event_team(e: dict) -> str:
    return e.get("team", {}).get("name", "")


def _event_player(e: dict) -> str:
    return e.get("player", {}).get("name", "")


def _event_time_seconds(event: dict) -> float:
    ts = event.get("timestamp", "")
    if ts:
        try:
            hh, mm, ss = ts.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        except ValueError:
            pass
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


# ── Corner sequence extraction ───────────────────────────────────────


def _sequence_events(events: list[dict], start_idx: int) -> list[dict]:
    """Contiguous events sharing the corner's ``possession`` and ``period``.

    Capped at :data:`SEQUENCE_MAX_SECONDS` seconds after the corner pass.
    """
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
    """Return the corner pass (direct) or the first "real" follow-up delivery.

    For short corners, walks forward until it finds a focus-team shot or
    a focus-team pass that either ends in the box (x ≥ 96), starts near
    the byline (x ≥ 105) or is at least :data:`DELIVERY_MIN_LEN` yards
    long. If nothing qualifies, falls back to the original corner pass.
    """
    corner = sequence[0]
    if _routine_type(corner) != "Short corner":
        return corner

    for event in sequence[1:]:
        if _event_team(event) != team_sb:
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
        if end[0] >= DELIVERY_END_X or loc[0] >= DELIVERY_LOC_X or length >= DELIVERY_MIN_LEN:
            return event

    return corner


def _delivery_receiver(delivery: dict, sequence: list[dict], team_sb: str) -> str:
    """Player who receives *delivery*.

    For a pass this is ``pass.recipient.name``. If that's missing (e.g.
    the delivery is a shot, or the pass has no recipient), fall back to
    the next focus-team player who touches the ball after the delivery.
    """
    recipient = delivery.get("pass", {}).get("recipient", {}).get("name")
    if recipient:
        return recipient

    delivery_id = delivery.get("id")
    found = False
    for event in sequence:
        if delivery_id and event.get("id") == delivery_id:
            found = True
            continue
        if not found:
            continue
        if _event_team(event) == team_sb:
            player = _event_player(event)
            if player:
                return player
    return "Unknown"


# ── Top-level API ────────────────────────────────────────────────────


def collect_corner_data(focus_team: str = "Barcelona") -> list[dict]:
    """Return one record per *focus_team* corner across every match.

    Each record has at minimum::

        {
            "match_id": str,
            "date": str,
            "opponent": str,
            "taker": str,
            "first_receiver": str,     # pass.recipient of the corner restart
            "delivery_receiver": str,  # post-short-corner meaningful delivery
            "routine_type": str,
        }
    """
    records: list[dict] = []
    for match in iter_matches():
        team_sb = resolve_team_name(focus_team, match)
        if team_sb is None:
            continue
        opponent_csv = match.away if focus_team == match.home else match.home

        events = match.events
        for idx, event in enumerate(events):
            if _event_team(event) != team_sb:
                continue
            if not _is_corner_pass(event):
                continue

            sequence = _sequence_events(events, idx)
            delivery = _meaningful_delivery(sequence, team_sb)

            taker = _event_player(event) or "Unknown"
            first_receiver = (
                event.get("pass", {}).get("recipient", {}).get("name") or "Unknown"
            )
            delivery_receiver = (
                _delivery_receiver(delivery, sequence, team_sb) if delivery else "Unknown"
            )

            records.append(
                {
                    "match_id": match.statsbomb_id,
                    "date": match.date,
                    "opponent": opponent_csv,
                    "taker": taker,
                    "first_receiver": first_receiver,
                    "delivery_receiver": delivery_receiver,
                    "routine_type": _routine_type(event),
                }
            )
    return records
