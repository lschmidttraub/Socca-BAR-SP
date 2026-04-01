"""Data loading utilities for StatsBomb event data.

``matches.csv`` is the source of truth for which matches exist and who
played.  Event data is loaded from ``.zip`` archives (or extracted JSON
directories) in the StatsBomb data folder.
"""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Iterator


# ── CSV helpers ──────────────────────────────────────────────────────

def _read_matches_csv(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _find_matches_csv(data_dir: Path) -> Path | None:
    """Locate matches.csv: check data_dir itself, then its parent."""
    for candidate in [data_dir / "matches.csv", data_dir.parent / "matches.csv"]:
        if candidate.is_file():
            return candidate
    return None


# ── Event loading (no lineup file needed) ────────────────────────────

def _load_events_from_zip(zip_path: Path, match_id: str) -> list[dict] | None:
    """Load events for *match_id* from a ZIP archive."""
    with zipfile.ZipFile(zip_path) as zf:
        for n in zf.namelist():
            if n.rsplit("/", 1)[-1] == f"{match_id}.json":
                with zf.open(n) as f:
                    return json.load(f)
    return None


def _load_events(data_dir: Path, match_id: str) -> list[dict] | None:
    """Find and load events for *match_id* from data_dir."""
    if data_dir.suffix == ".zip" and data_dir.is_file():
        return _load_events_from_zip(data_dir, match_id)

    if data_dir.is_dir():
        # Extracted JSON
        events_path = data_dir / f"{match_id}.json"
        if events_path.exists():
            with open(events_path, encoding="utf-8") as f:
                return json.load(f)
        # Search ZIPs
        for zp in sorted(data_dir.glob("*.zip")):
            result = _load_events_from_zip(zp, match_id)
            if result is not None:
                return result

    return None


# ── Public API ───────────────────────────────────────────────────────

MatchRow = dict  # a row from matches.csv


def iter_matches(
    data_dir: Path,
) -> Iterator[tuple[MatchRow, list[dict]]]:
    """Yield ``(csv_row, events)`` for every match in matches.csv.

    *csv_row* contains ``home``, ``away``, ``score``, ``statsbomb``, etc.
    Team names come from the CSV, not from lineup files.
    """
    csv_path = _find_matches_csv(data_dir)
    if csv_path is None:
        raise FileNotFoundError(
            f"matches.csv not found in {data_dir} or {data_dir.parent}"
        )

    rows = _read_matches_csv(csv_path)
    for row in rows:
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        events = _load_events(data_dir, match_id)
        if events is not None:
            yield row, events


def load_match(data_dir: Path, match_id: str) -> list[dict] | None:
    """Load events for a single match by StatsBomb ID."""
    return _load_events(data_dir, match_id)


def get_team_names(row: MatchRow) -> tuple[str, str]:
    """Extract (home, away) team names from a CSV row."""
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    if not home or not away:
        raise ValueError(f"Missing team names in row: {row}")
    return home, away


def get_match_rows(csv_path: Path, team: str | None = None) -> list[dict]:
    """Return rows from matches.csv, optionally filtered to a team."""
    rows = _read_matches_csv(csv_path)
    if team is None:
        return rows
    return [
        r for r in rows
        if team in r.get("home", "") or team in r.get("away", "")
    ]
