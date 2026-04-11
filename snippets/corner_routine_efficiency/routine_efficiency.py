"""Corner routine efficiency — Barcelona vs the UCL field.

Re-creates the two grouped-bar charts embedded in the *Offensive
Corners* subsection of the BAR-SP wiki page:

* ``attempts_per_corner_bars.png`` — attempts per corner, split by
  short vs crossed routine, Barcelona vs league average.
* ``xg_per_corner_bars.png`` — xG per corner, split by short vs crossed
  routine, Barcelona vs league average.

Corners are classified as **short** when the opener pass length is
≤ 15 yards OR the opener's end-location sits inside the attacking
penalty box (x ≥ 102, 18 ≤ y ≤ 62 after normalising to attacking-right).
Every other corner is a **cross**. Shots are assigned to the most
recent same-team corner with a smaller event index, provided the shot
has ``play_pattern == "From Corner"`` and is not a penalty.

Event data is streamed directly out of
``data/statsbomb/{league_phase,last16,playoffs}.zip`` — the ZIPs are
never extracted to disk. All paths are CWD-relative, so run this from
the project root.

Run with::

    uv run python snippets/corner_routine_efficiency/routine_efficiency.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

# ── Paths (CWD-relative — run from the project root) ────────────────
DATA_DIR = Path("data")
STATSBOMB_DIR = DATA_DIR / "statsbomb"
MATCHES_CSV = DATA_DIR / "matches.csv"
ZIP_NAMES = ("league_phase.zip", "last16.zip", "playoffs.zip")

FOCUS_TEAM = "Barcelona"
DEFAULT_OUTPUT_DIR = Path("corner_routine_plots")

BARCA_COLOR = "#2476b3"
AVG_COLOR = "#ff7e16"

# Corner classification constants (StatsBomb 120×80 pitch).
SHORT_THRESHOLD_YARDS = 15.0
PEN_BOX_X = 102.0
PEN_BOX_Y_MIN = 18.0
PEN_BOX_Y_MAX = 62.0


# ── StatsBomb streaming loader (copied from set_piece_statistics) ────
#
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


def _read_matches_csv(csv_path: Path = MATCHES_CSV) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return rows


def _load_events_from_zips(match_id: str) -> list[dict] | None:
    """Stream event JSON for *match_id* from whichever ZIP contains it."""
    target = f"{match_id}.json"
    for zname in ZIP_NAMES:
        zp = STATSBOMB_DIR / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def _resolve_team_name(csv_team: str, events: list[dict]) -> str | None:
    """Return *csv_team* if it appears verbatim as an event team name."""
    for e in events:
        if e.get("team", {}).get("name") == csv_team:
            return csv_team
    return None


# ── Corner classification helpers ───────────────────────────────────


def _pass_length(start: list[float], end: list[float]) -> float:
    return math.hypot(end[0] - start[0], end[1] - start[1])


def _normalize_attacking_right(
    start: list[float], end: list[float]
) -> tuple[float, float]:
    """Flip coordinates so the attacking goal is always at x=120.

    Direction of attack is inferred from the corner's start location:
    corners from x>60 already attack right, otherwise the pitch is
    mirrored.
    """
    ex, ey = end
    if start[0] > 60:
        return ex, ey
    return 120.0 - ex, 80.0 - ey


def _in_penalty_box(x: float, y: float) -> bool:
    return x >= PEN_BOX_X and PEN_BOX_Y_MIN <= y <= PEN_BOX_Y_MAX


def classify_corner(ev: dict) -> str | None:
    """Return ``"short"``, ``"cross"`` or ``None`` if coords missing."""
    start = ev.get("location")
    end = ev.get("pass", {}).get("end_location")
    if start is None or end is None:
        return None

    end_nx, end_ny = _normalize_attacking_right(start, end)
    if _in_penalty_box(end_nx, end_ny):
        return "short" if _pass_length(start, end) <= SHORT_THRESHOLD_YARDS else "cross"
    return "short" if _pass_length(start, end) <= SHORT_THRESHOLD_YARDS else "cross"


def _is_corner_pass(e: dict) -> bool:
    return (
        e.get("type", {}).get("id") == 30
        and e.get("pass", {}).get("type", {}).get("name") == "Corner"
    )


def _is_from_corner_shot(e: dict) -> bool:
    return (
        e.get("type", {}).get("id") == 16
        and e.get("shot", {}).get("type", {}).get("name") != "Penalty"
        and e.get("play_pattern", {}).get("name") == "From Corner"
    )


def _shot_xg(e: dict) -> float:
    return float(e.get("shot", {}).get("statsbomb_xg", 0.0) or 0.0)


# Note: the original src/attempts_comparison_corner.py first checks the
# penalty box (treating in-box openers as "cross"), whereas this snippet
# follows the wiki spec literally — "short" is opener length ≤ 15 OR
# in-box end location. Under the spec, any opener ≤ 15 yards (including
# a tap inside the box) is short; a longer opener still counts as short
# if it lands in the box (e.g. a short-corner return ball from the
# touchline). Both rules fall out of the single ``classify_corner``
# function above.


# ── Aggregation ──────────────────────────────────────────────────────


def _empty_record() -> dict:
    return {
        "short": {"corners": 0, "attempts": 0, "xg": 0.0},
        "cross": {"corners": 0, "attempts": 0, "xg": 0.0},
    }


def collect_per_team() -> dict[str, dict]:
    """Iterate every match and aggregate per-team corner totals."""
    records: dict[str, dict] = defaultdict(_empty_record)

    for row in _read_matches_csv():
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        events = _load_events_from_zips(match_id)
        if not events:
            continue

        events = sorted(events, key=lambda e: e.get("index", -1))

        # First pass: list every corner with its classification.
        corners: list[dict] = []
        for ev in events:
            if not _is_corner_pass(ev):
                continue
            ctype = classify_corner(ev)
            if ctype is None:
                continue
            corners.append(
                {
                    "index": ev.get("index", -1),
                    "team": ev.get("team", {}).get("name", ""),
                    "type": ctype,
                    "attempts": 0,
                    "xg": 0.0,
                }
            )

        # Second pass: assign each From Corner shot to its most recent
        # same-team corner with a smaller event index.
        for shot in events:
            if not _is_from_corner_shot(shot):
                continue
            shot_team = shot.get("team", {}).get("name", "")
            shot_idx = shot.get("index", -1)

            opener = None
            for c in reversed(corners):
                if c["index"] < shot_idx and c["team"] == shot_team:
                    opener = c
                    break
            if opener is None:
                continue
            opener["attempts"] += 1
            opener["xg"] += _shot_xg(shot)

        # Only aggregate for teams whose CSV spelling matches the
        # event-side spelling verbatim.
        for csv_team in (row.get("home", "").strip(), row.get("away", "").strip()):
            if not csv_team:
                continue
            sb_team = _resolve_team_name(csv_team, events)
            if sb_team is None:
                continue

            rec = records[csv_team]
            for c in corners:
                if c["team"] != sb_team:
                    continue
                bucket = rec[c["type"]]
                bucket["corners"] += 1
                bucket["attempts"] += c["attempts"]
                bucket["xg"] += c["xg"]

    return dict(records)


def per_corner_rates(rec: dict) -> dict:
    """Return ``{"short": {"att_pc", "xg_pc"}, "cross": {...}}``."""
    out: dict[str, dict] = {}
    for t in ("short", "cross"):
        b = rec[t]
        c = b["corners"]
        out[t] = {
            "att_pc": (b["attempts"] / c) if c else 0.0,
            "xg_pc": (b["xg"] / c) if c else 0.0,
        }
    return out


def league_averages(records: dict[str, dict]) -> dict:
    """Mean per-corner attempt/xG rate across teams with ≥ 1 corner."""
    out: dict[str, dict] = {}
    for t in ("short", "cross"):
        teams_att: list[float] = []
        teams_xg: list[float] = []
        for rec in records.values():
            if rec[t]["corners"] > 0:
                rates = per_corner_rates(rec)[t]
                teams_att.append(rates["att_pc"])
                teams_xg.append(rates["xg_pc"])
        n = len(teams_att)
        out[t] = {
            "teams": n,
            "att_pc": (sum(teams_att) / n) if n else 0.0,
            "xg_pc": (sum(teams_xg) / n) if n else 0.0,
        }
    return out


# ── Plotting ────────────────────────────────────────────────────────


def _grouped_bar(
    barca_vals: list[float],
    avg_vals: list[float],
    *,
    title: str,
    ylabel: str,
    focus_team: str,
    output_path: Path,
    value_fmt: str,
) -> None:
    categories = ["Short corners", "Crossed corners"]
    xs = list(range(len(categories)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    b1 = ax.bar(
        [i - width / 2 for i in xs],
        barca_vals,
        width=width,
        label=focus_team,
        color=BARCA_COLOR,
        edgecolor="black",
        linewidth=0.6,
    )
    b2 = ax.bar(
        [i + width / 2 for i in xs],
        avg_vals,
        width=width,
        label="League average",
        color=AVG_COLOR,
        edgecolor="black",
        linewidth=0.6,
    )

    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            ax.annotate(
                format(h, value_fmt),
                xy=(rect.get_x() + rect.get_width() / 2, h),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(xs)
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ymax = max(barca_vals + avg_vals + [0.0])
    ax.set_ylim(0, ymax * 1.18 if ymax > 0 else 1.0)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── Report + plotting entry point ───────────────────────────────────


def main(focus_team: str, output_dir: Path) -> None:
    records = collect_per_team()

    focus = records.get(focus_team)
    if focus is None:
        raise SystemExit(f"No data for team {focus_team!r}")

    focus_rates = per_corner_rates(focus)
    avg = league_averages(records)

    print(f"Corner routine efficiency — {focus_team}")
    print("-" * 60)
    print(f"  Short corners taken       : {focus['short']['corners']}")
    print(f"  Crossed corners taken     : {focus['cross']['corners']}")
    print(f"  Attempts / short corner   : {focus_rates['short']['att_pc']:.3f}")
    print(f"  Attempts / crossed corner : {focus_rates['cross']['att_pc']:.3f}")
    print(f"  xG / short corner         : {focus_rates['short']['xg_pc']:.3f}")
    print(f"  xG / crossed corner       : {focus_rates['cross']['xg_pc']:.3f}")
    print()
    print(
        "League average "
        f"(short n = {avg['short']['teams']}, cross n = {avg['cross']['teams']})"
    )
    print("-" * 60)
    print(f"  Attempts / short corner   : {avg['short']['att_pc']:.3f}")
    print(f"  Attempts / crossed corner : {avg['cross']['att_pc']:.3f}")
    print(f"  xG / short corner         : {avg['short']['xg_pc']:.3f}")
    print(f"  xG / crossed corner       : {avg['cross']['xg_pc']:.3f}")

    barca_att = [focus_rates["short"]["att_pc"], focus_rates["cross"]["att_pc"]]
    avg_att = [avg["short"]["att_pc"], avg["cross"]["att_pc"]]
    barca_xg = [focus_rates["short"]["xg_pc"], focus_rates["cross"]["xg_pc"]]
    avg_xg = [avg["short"]["xg_pc"], avg["cross"]["xg_pc"]]

    print()
    print(f"Saving plots to {output_dir}/ ...")
    attempts_path = output_dir / "attempts_per_corner_bars.png"
    xg_path = output_dir / "xg_per_corner_bars.png"

    _grouped_bar(
        barca_att,
        avg_att,
        title="Attempts per Corner — Short vs Crossed",
        ylabel="Attempts per corner",
        focus_team=focus_team,
        output_path=attempts_path,
        value_fmt=".2f",
    )
    print(f"  saved {attempts_path}")

    _grouped_bar(
        barca_xg,
        avg_xg,
        title="xG per Corner — Short vs Crossed",
        ylabel="xG per corner",
        focus_team=focus_team,
        output_path=xg_path,
        value_fmt=".3f",
    )
    print(f"  saved {xg_path}")


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    main(team, out)
