"""Per-match top-6 outfield-player height: Barcelona vs each opponent.

Generates the second physicality plot embedded in the BAR-SP wiki: a
grouped bar chart of the mean height of the 6 tallest outfield players
each side put on the pitch in every Barcelona fixture.

For each Barcelona match the script:

1. loads the StatsBomb lineup file,
2. picks every outfield player (non-goalkeeper) who actually appeared
   (non-empty ``positions`` list),
3. takes the 6 tallest of those players for both sides, and
4. averages their heights.

Heights come from the StatsBomb lineup files (``*_lineups.json``)
bundled inside ``data/statsbomb/league_phase.zip`` and
``data/statsbomb/playoffs.zip``. ``last16.zip`` ships without lineup
files, so a couple of fixtures are skipped.

Usage
-----

    python barca_match_height.py [team] [output.png]

Both arguments are optional: ``team`` defaults to ``Barcelona`` and
``output.png`` defaults to ``barca_match_height.png`` in the current
working directory. The team-name argument exists for symmetry with the
sibling script — for any team other than Barcelona the script will
report on that team's matches instead.
"""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

STATSBOMB_DIR = Path("data/statsbomb")
MATCHES_CSV = Path("data/matches.csv")
DEFAULT_OUTPUT = Path("barca_match_height.png")

FOCUS_TEAM = "Barcelona"
TOP_N = 6
LINEUP_ZIPS = ("league_phase.zip", "playoffs.zip", "quarterfinals.zip")

# CSV team names that differ from their StatsBomb event/lineup spelling.
# Applied when reading matches.csv so every downstream lookup is
# an exact match against the lineup files.
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


FOCUS_COLOR = "#a50026"
OPPONENT_COLOR = "#4575b4"


# ── Lineup loading ────────────────────────────────────────────────────


def _load_lineup(match_id: str) -> list[dict] | None:
    target = f"{match_id}_lineups.json"
    for zname in LINEUP_ZIPS:
        zp = STATSBOMB_DIR / zname
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                if n.rsplit("/", 1)[-1] == target:
                    with zf.open(n) as fh:
                        return json.load(fh)
    return None


def _read_matches_csv() -> list[dict]:
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        row["home"] = _normalise_team(row.get("home", ""))
        row["away"] = _normalise_team(row.get("away", ""))
    return rows


# ── Player helpers ────────────────────────────────────────────────────


def _is_goalkeeper(player: dict) -> bool:
    return any(
        "Goalkeeper" in pos.get("position", "")
        for pos in player.get("positions", [])
    )


def _actually_played(player: dict) -> bool:
    return len(player.get("positions", [])) > 0


def _top_n_mean(heights: list[float], n: int = TOP_N) -> float | None:
    top = sorted(heights, reverse=True)[:n]
    if len(top) < n:
        return None
    return sum(top) / n


def _outfield_heights(players: list[dict]) -> list[float]:
    return [
        float(p["player_height"])
        for p in players
        if _actually_played(p) and not _is_goalkeeper(p) and p.get("player_height")
    ]


# ── Data collection ───────────────────────────────────────────────────


def collect_match_heights(focus_team: str) -> list[dict]:
    """Return ``[{label, focus, opponent}, ...]`` for every focus-team match.

    Lineup entries don't carry the matches.csv team name, so we look up
    the focus team's StatsBomb name by exact-match against the lineup's
    ``team_name`` fields. Lineups have exactly two teams; whichever
    isn't the focus team is treated as the opponent.
    """
    out: list[dict] = []
    for row in _read_matches_csv():
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue
        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        if focus_team not in (home_csv, away_csv):
            continue

        lineup = _load_lineup(match_id)
        if lineup is None or len(lineup) != 2:
            continue

        sb_names = [td.get("team_name", "") for td in lineup]
        if focus_team not in sb_names:
            # CSV names are normalised at load time; a miss here means
            # a mapping is absent — skip as a safety net.
            continue

        focus_idx = sb_names.index(focus_team)
        opp_idx = 1 - focus_idx

        focus_h = _top_n_mean(_outfield_heights(lineup[focus_idx].get("lineup", [])))
        opp_h = _top_n_mean(_outfield_heights(lineup[opp_idx].get("lineup", [])))
        if focus_h is None or opp_h is None:
            continue

        opponent_csv = away_csv if focus_team == home_csv else home_csv
        out.append({
            "label": f"vs {opponent_csv}",
            "focus": focus_h,
            "opponent": opp_h,
        })

    return out


# ── Plotting ──────────────────────────────────────────────────────────


def plot(matches: list[dict], focus_team: str, output_path: Path) -> None:
    if not matches:
        raise SystemExit(f"No matches with lineup data found for {focus_team!r}.")

    labels = [m["label"] for m in matches]
    focus_vals = [m["focus"] for m in matches]
    opp_vals = [m["opponent"] for m in matches]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.3), 6))
    ax.bar(x - width / 2, focus_vals, width, label=focus_team, color=FOCUS_COLOR)
    ax.bar(x + width / 2, opp_vals, width, label="Opponent", color=OPPONENT_COLOR, alpha=0.7)

    all_vals = focus_vals + opp_vals
    y_min = min(all_vals) - 2.0
    y_max = max(all_vals)
    span = y_max - y_min if y_max > y_min else 1.0

    for xi, (fv, ov) in enumerate(zip(focus_vals, opp_vals)):
        ax.text(xi - width / 2, fv + span * 0.01, f"{fv:.1f}",
                ha="center", va="bottom", fontsize=7.5)
        ax.text(xi + width / 2, ov + span * 0.01, f"{ov:.1f}",
                ha="center", va="bottom", fontsize=7.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Mean height (cm)")
    ax.set_ylim(y_min, y_max + span * 0.18)
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title(
        f"{focus_team} — Mean Height of {TOP_N} Tallest Outfield Players per Match",
        fontsize=14, fontweight="bold",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Plot saved to {output_path}")


# ── Entry point ───────────────────────────────────────────────────────


def main(focus_team: str = FOCUS_TEAM, output_path: Path = DEFAULT_OUTPUT) -> None:
    matches = collect_match_heights(focus_team)
    print(f"{focus_team} matches with lineup data: {len(matches)}")
    for m in matches:
        gap = m["opponent"] - m["focus"]
        print(f"  {m['label']:30s} {focus_team[:12]:12s}={m['focus']:5.1f} cm  opp={m['opponent']:5.1f} cm  Δ={gap:+.1f} cm")
    plot(matches, focus_team, output_path)


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    main(team, out)
