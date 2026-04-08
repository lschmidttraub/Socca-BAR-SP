"""Download video clips of every set-piece event in a match.

Change SET_PIECE below to select which set piece to extract.

Usage:
    python corner_videos.py <statsbomb_match_id> [-hq]

Outputs 10-second MP4 clips (one per event) into the videos/ directory.
Requires the Wyscout eventvideo tool at data/wyscout/eventvideo.py (or
inside data/wyscout.zip).
"""

import argparse
import csv
import json
import subprocess
import sys
import zipfile
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────

SET_PIECE = "corners"

# Mapping from set-piece name to StatsBomb pass.type.name / shot.type.name
SET_PIECE_FILTERS = {
    "corners":    {"pass_type": "Corner",    "shot_type": "Corner"},
    "free_kicks": {"pass_type": "Free Kick", "shot_type": "Free Kick"},
    "throw_ins":  {"pass_type": "Throw-in",  "shot_type": None},
    "goal_kicks": {"pass_type": "Goal Kick", "shot_type": None},
    "penalties":  {"pass_type": None,         "shot_type": "Penalty"},
}

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"
STATSBOMB_DIR = DATA_DIR / "statsbomb"
MATCHES_CSV = DATA_DIR / "matches.csv"
VIDEOS_DIR = ROOT / "videos"

# Possible locations for the Wyscout CLI tool
EVENTVIDEO_CANDIDATES = [
    DATA_DIR / "wyscout" / "eventvideo.py",
    DATA_DIR / "wyscout" / "eventvideo" / "eventvideo.py",
]
WYSCOUT_ZIP = DATA_DIR / "wyscout.zip"


# ── Wyscout tool discovery ───────────────────────────────────────────

def _find_eventvideo() -> Path:
    """Locate the eventvideo.py script on disk or inside wyscout.zip."""
    for p in EVENTVIDEO_CANDIDATES:
        if p.is_file():
            return p
    # Try extracting from zip
    if WYSCOUT_ZIP.is_file():
        extract_dir = DATA_DIR / "wyscout"
        with zipfile.ZipFile(WYSCOUT_ZIP) as zf:
            # Find eventvideo.py inside the zip
            for name in zf.namelist():
                if name.endswith("eventvideo.py"):
                    zf.extract(name, extract_dir)
                    return extract_dir / name
    raise FileNotFoundError(
        "Cannot find eventvideo.py. Expected at one of:\n"
        + "\n".join(f"  {p}" for p in EVENTVIDEO_CANDIDATES)
        + f"\nor inside {WYSCOUT_ZIP}"
    )


# ── Match lookup ─────────────────────────────────────────────────────

def _read_matches() -> list[dict]:
    with open(MATCHES_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _find_match_row(match_id: str) -> dict:
    """Find the matches.csv row for a StatsBomb match ID."""
    for row in _read_matches():
        if row.get("statsbomb", "").strip() == match_id:
            return row
    raise KeyError(f"No match found in matches.csv with statsbomb={match_id}")


# ── StatsBomb event loading ──────────────────────────────────────────

def _load_events(match_id: str) -> list[dict]:
    """Load StatsBomb events for a match, searching JSON files and ZIPs."""
    # Direct JSON file
    for json_path in STATSBOMB_DIR.rglob(f"{match_id}.json"):
        with open(json_path, encoding="utf-8") as f:
            return json.load(f)
    # Inside ZIPs
    for zp in sorted(STATSBOMB_DIR.rglob("*.zip")):
        with zipfile.ZipFile(zp) as zf:
            for name in zf.namelist():
                if name.rsplit("/", 1)[-1] == f"{match_id}.json":
                    with zf.open(name) as f:
                        return json.load(f)
    raise FileNotFoundError(f"No StatsBomb events found for match {match_id}")


def _get_setpiece_events(events: list[dict], set_piece: str) -> list[dict]:
    """Return all events matching the given set-piece type."""
    filt = SET_PIECE_FILTERS[set_piece]
    pass_type = filt["pass_type"]
    shot_type = filt["shot_type"]
    result = []
    for e in events:
        type_id = e.get("type", {}).get("id")
        if type_id == 30 and pass_type:  # Pass
            if e.get("pass", {}).get("type", {}).get("name") == pass_type:
                result.append(e)
        elif type_id == 16 and shot_type:  # Shot (direct free kick / penalty)
            if e.get("shot", {}).get("type", {}).get("name") == shot_type:
                result.append(e)
    return result


# ── Timestamp conversion ────────────────────────────────────────────

def _timestamp_to_seconds(ts: str) -> int:
    """Convert StatsBomb timestamp 'HH:MM:SS.mmm' to integer seconds."""
    parts = ts.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return round(h * 3600 + m * 60 + s)


def _video_timestamp(event: dict, videooffset: int) -> int:
    """Compute the Wyscout video timestamp for a StatsBomb event.

    Period 1: elapsed seconds + 1
    Period 2+: elapsed seconds + videooffset
    """
    elapsed = _timestamp_to_seconds(event["timestamp"])
    period = event.get("period", 1)
    if period == 1:
        return elapsed + 1
    return elapsed + videooffset


# ── Video download ───────────────────────────────────────────────────

def _download_clip(
    eventvideo_py: Path,
    wyscout_id: str,
    video_ts: int,
    output_path: Path,
    hq: bool = False,
) -> None:
    cmd = [sys.executable, str(eventvideo_py), wyscout_id, str(video_ts), str(output_path)]
    if hq:
        cmd.append("-hq")
    subprocess.run(cmd, check=True)


# ── Main ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Download set-piece video clips for a match.")
    parser.add_argument("match_id", help="StatsBomb match ID")
    parser.add_argument("-hq", action="store_true", help="Download high-quality clips")
    args = parser.parse_args()

    match_id = args.match_id.strip()

    if SET_PIECE not in SET_PIECE_FILTERS:
        print(f"Unknown SET_PIECE={SET_PIECE!r}. Choose from: {list(SET_PIECE_FILTERS)}")
        sys.exit(1)

    # Lookup match metadata
    row = _find_match_row(match_id)
    wyscout_id = row["wyscout"].strip()
    videooffset = int(row["videooffset"].strip())
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    print(f"Match: {home} vs {away}  (statsbomb={match_id}, wyscout={wyscout_id})")
    print(f"Set piece: {SET_PIECE}")

    # Load events and find set pieces
    events = _load_events(match_id)
    sp_events = _get_setpiece_events(events, SET_PIECE)
    if not sp_events:
        print(f"No {SET_PIECE} found in this match.")
        return
    print(f"Found {len(sp_events)} {SET_PIECE} event(s).\n")

    # Locate the Wyscout download tool
    eventvideo_py = _find_eventvideo()

    # Download each clip
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    for i, ev in enumerate(sp_events, 1):
        team = ev.get("team", {}).get("name", "unknown")
        player = ev.get("player", {}).get("name", "unknown")
        period = ev.get("period", 1)
        ts = ev["timestamp"]
        video_ts = _video_timestamp(ev, videooffset)

        ts_safe = ts.replace(":", "-").split(".")[0]
        filename = f"{SET_PIECE}_{i:02d}_p{period}_{ts_safe}_{team}.mp4"
        output_path = VIDEOS_DIR / filename

        print(f"[{i}/{len(sp_events)}] {team} – {player} (period {period}, {ts}) → video_ts={video_ts}")
        try:
            _download_clip(eventvideo_py, wyscout_id, video_ts, output_path, hq=args.hq)
            print(f"  Saved: {output_path}")
        except subprocess.CalledProcessError as exc:
            print(f"  ERROR: eventvideo.py exited with code {exc.returncode}", file=sys.stderr)

    print(f"\nDone. {len(sp_events)} clip(s) saved to {VIDEOS_DIR}/")


if __name__ == "__main__":
    main()
