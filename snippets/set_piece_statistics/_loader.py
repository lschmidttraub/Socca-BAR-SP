"""Shared StatsBomb event-data loader used by every script in this snippet.

The loader reads ``data/matches.csv`` (the project-wide lookup table) and
streams match JSONs out of the three StatsBomb ZIP archives in
``data/statsbomb/`` without ever extracting them to disk.

Every helper here is self-contained — no dependency on the project's
``src/stats`` library — so the whole ``set_piece_statistics`` snippet folder
can be dropped into another repo that follows the same data layout.

All paths are CWD-relative: scripts in this snippet assume they're run
from the project root (the directory that contains ``data/``).
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

LEAGUE_PHASE_ZIP = "league_phase.zip"
ZIP_NAMES = (LEAGUE_PHASE_ZIP, "last16.zip", "playoffs.zip")

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


@dataclass
class Match:
    """One row from matches.csv plus its loaded StatsBomb events."""

    statsbomb_id: str
    date: str
    home: str
    away: str
    phase: str  # "league_phase" | "last16" | "playoffs"
    events: list[dict]

    def opponent_of(self, team: str) -> str:
        return self.away if team in self.home else self.home


def _normalise_team(name: str) -> str:
    """Apply CSV→StatsBomb spelling fixes."""
    for old, new in CSV_TO_STATSBOMB.items():
        name = name.replace(old, new)
    return name


def _read_matches_csv(csv_path: Path = MATCHES_CSV) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return rows


def _index_phases(statsbomb_dir: Path = STATSBOMB_DIR) -> dict[str, str]:
    """Return ``{match_id: phase}`` for every match ID found in the ZIPs."""
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
    """Load event JSON for *match_id* from whichever ZIP contains it."""
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
    phase: str | None = None,
) -> Iterator[Match]:
    """Yield a :class:`Match` for every row in ``matches.csv``.

    When *phase* is given (``"league_phase"``, ``"last16"`` or
    ``"playoffs"``), only matches from that phase are yielded.
    """
    phase_by_id = _index_phases(statsbomb_dir)
    for row in _read_matches_csv(matches_csv):
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        match_phase = phase_by_id.get(match_id, "unknown")
        if phase is not None and match_phase != phase:
            continue
        events = _load_events(statsbomb_dir, match_id)
        if events is None:
            continue
        yield Match(
            statsbomb_id=match_id,
            date=row.get("date", "").strip(),
            home=row.get("home", "").strip(),
            away=row.get("away", "").strip(),
            phase=match_phase,
            events=events,
        )


# ── Team-name resolution ──────────────────────────────────────────────
#
# CSV team names are normalised to StatsBomb spelling via
# CSV_TO_STATSBOMB when matches.csv is loaded.  resolve_team_name()
# still does a final exact-match check as a safety net for any team
# whose mapping is incomplete or absent.


def resolve_team_name(csv_team: str, match: Match) -> str | None:
    """Return *csv_team* if it appears verbatim in *match*'s events.

    With the CSV→StatsBomb mapping applied at load time this should
    succeed for every team.  Returns ``None`` only for unmapped
    spelling mismatches, in which case callers skip the pair.
    """
    for e in match.events:
        if e.get("team", {}).get("name") == csv_team:
            return csv_team
    return None


# ── Event predicates (StatsBomb v8 schema) ────────────────────────────

PASS_TYPE_ID = 30
SHOT_TYPE_ID = 16
OPPONENT_HALF_X = 60.0  # free kicks beyond the halfway line


def is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == PASS_TYPE_ID


def is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == SHOT_TYPE_ID


def pass_type(e: dict) -> str | None:
    return e.get("pass", {}).get("type", {}).get("name")


def shot_type(e: dict) -> str | None:
    return e.get("shot", {}).get("type", {}).get("name")


def is_corner_pass(e: dict) -> bool:
    return is_pass(e) and pass_type(e) == "Corner"


def is_free_kick_pass(e: dict) -> bool:
    return is_pass(e) and pass_type(e) == "Free Kick"


def is_free_kick_shot(e: dict) -> bool:
    return is_shot(e) and shot_type(e) == "Free Kick"


def is_penalty_shot(e: dict) -> bool:
    return is_shot(e) and shot_type(e) == "Penalty"


def play_pattern(e: dict) -> str:
    return e.get("play_pattern", {}).get("name", "")


def shot_xg(e: dict) -> float:
    return float(e.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)


def is_goal(e: dict) -> bool:
    return e.get("shot", {}).get("outcome", {}).get("name") == "Goal"


def event_team(e: dict) -> str:
    return e.get("team", {}).get("name", "")


def in_opponent_half(e: dict) -> bool:
    """True if the event's x-coordinate is past the half-way line (x ≥ 60)."""
    loc = e.get("location")
    return bool(loc and loc[0] >= OPPONENT_HALF_X)
