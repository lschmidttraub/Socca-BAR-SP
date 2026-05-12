"""Yellow and red cards per defensive player, left side vs right side.

Self-contained snippet — no dependency on the project's ``src/`` library.
All paths are CWD-relative; run from the project root.
"""

from __future__ import annotations

import csv
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

DATA_DIR = Path("data")
STATSBOMB_DIR = DATA_DIR / "statsbomb"
MATCHES_CSV = DATA_DIR / "matches.csv"
ZIP_NAMES = ("league_phase.zip", "last16.zip", "playoffs.zip", "quarterfinals.zip")

LEFT_POSITIONS = {"Left Back", "Left Wing Back", "Left Center Back"}
RIGHT_POSITIONS = {"Right Back", "Right Wing Back", "Right Center Back"}
CENTER_POSITIONS = {"Center Back"}
DEFENSIVE_POSITIONS = LEFT_POSITIONS | RIGHT_POSITIONS | CENTER_POSITIONS

YELLOW_COLOR = "#f1c232"
RED_COLOR = "#a02828"

DEFAULT_OUTPUT = Path("defensive_cards_by_side.png")


@dataclass
class CardCounts:
    yellow: int = 0
    red: int = 0  # red cards + second-yellow dismissals

    @property
    def total(self) -> int:
        return self.yellow + self.red


def iter_focus_match_events(team: str):
    """Yield event lists for every match in matches.csv that includes *team*."""
    with open(MATCHES_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    file_to_zip: dict[str, str] = {}
    for zn in ZIP_NAMES:
        zp = STATSBOMB_DIR / zn
        if not zp.is_file():
            continue
        with zipfile.ZipFile(zp) as zf:
            for n in zf.namelist():
                base = n.rsplit("/", 1)[-1]
                if base.endswith(".json") and not base.endswith("_lineups.json"):
                    file_to_zip[base.removesuffix(".json")] = zn

    for row in rows:
        if team not in (row.get("home", ""), row.get("away", "")):
            continue
        mid = (row.get("statsbomb") or "").strip()
        zn = file_to_zip.get(mid)
        if not zn:
            continue
        with zipfile.ZipFile(STATSBOMB_DIR / zn) as zf:
            target = f"{mid}.json"
            entry = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == target), None)
            if entry is None:
                continue
            with zf.open(entry) as fh:
                yield row, json.load(fh)


def card_name(e: dict) -> str | None:
    bb = (e.get("bad_behaviour") or {}).get("card")
    if bb:
        return bb.get("name")
    fc = (e.get("foul_committed") or {}).get("card")
    if fc:
        return fc.get("name")
    return None


def classify_side(position: str) -> str | None:
    if position in LEFT_POSITIONS:
        return "left"
    if position in RIGHT_POSITIONS:
        return "right"
    if position in CENTER_POSITIONS:
        return "center"
    return None


def collect(team: str) -> tuple[
    dict[str, Counter],            # player -> position frequency
    dict[str, CardCounts],         # player -> card counts
    int,                           # matches counted
]:
    pos_freq: dict[str, Counter] = defaultdict(Counter)
    cards: dict[str, CardCounts] = defaultdict(CardCounts)
    n_matches = 0

    for _row, events in iter_focus_match_events(team):
        n_matches += 1
        for e in events:
            if (e.get("team") or {}).get("name") != team:
                continue
            player = (e.get("player") or {}).get("name")
            pos = (e.get("position") or {}).get("name")
            if player and pos:
                pos_freq[player][pos] += 1

            card = card_name(e)
            if card and player:
                if card == "Yellow Card":
                    cards[player].yellow += 1
                elif card == "Second Yellow":
                    cards[player].red += 1
                elif card == "Red Card":
                    cards[player].red += 1

    return pos_freq, cards, n_matches


def primary_position(freq: Counter) -> str:
    return freq.most_common(1)[0][0]


def print_report(
    team: str,
    n_matches: int,
    rows: list[tuple[str, str, str, CardCounts]],
) -> None:
    print(f"Defensive players' cards — {team}")
    print(f"  Matches counted: {n_matches}")
    print("-" * 72)
    print(f"{'Side':<7} {'Primary position':<20} {'Player':<28} {'Y':>3} {'R':>3}")
    print("-" * 72)

    for side in ("left", "right", "center"):
        side_rows = [r for r in rows if r[0] == side]
        if not side_rows:
            continue
        side_rows.sort(key=lambda r: (-r[3].total, r[2]))
        for s, pos, player, c in side_rows:
            print(f"{s:<7} {pos:<20} {player:<28} {c.yellow:>3} {c.red:>3}")
        ty = sum(r[3].yellow for r in side_rows)
        tr = sum(r[3].red for r in side_rows)
        print(f"{'':<7} {'':<20} {'TOTAL ' + side:<28} {ty:>3} {tr:>3}")
        print("-" * 72)


def short_name(full: str) -> str:
    """Compact display name.

    Heuristics, in order:
    - 2 tokens         → last token              ("Jules Koundé" → "Koundé")
    - token before a   → that token              ("Araújo da Silva" → "Araújo")
      lineage particle
    - 3 tokens         → second token            ("Pau Cubarsí Paredes" → "Cubarsí";
                                                  Spanish convention: paternal surname)
    - 4+ tokens        → last token              ("João Pedro Cavaco Cancelo" → "Cancelo")
    """
    particles = {"da", "de", "del", "dos", "di", "van", "von", "la", "le"}
    tokens = full.split()
    if len(tokens) <= 2:
        return tokens[-1]
    for i in range(1, len(tokens)):
        if tokens[i].lower() in particles:
            return tokens[i - 1]
    if len(tokens) == 3:
        return tokens[1]
    return tokens[-1]


def plot(
    rows: list[tuple[str, str, str, CardCounts]],
    team: str,
    output_path: Path,
) -> None:
    def carded(side: str) -> list[tuple[str, str, str, CardCounts]]:
        carded = [r for r in rows if r[0] == side and r[3].total > 0]
        carded.sort(key=lambda r: (r[3].total, r[3].red), reverse=False)
        return carded

    left = carded("left")
    right = carded("right")

    if not left and not right:
        print("  no carded left/right-side defensive players — skipping plot")
        return

    n = max(len(left), len(right), 1)
    fig, (ax_l, ax_r) = plt.subplots(
        2, 1,
        figsize=(8.5, 1.0 + 0.7 * (len(left) + len(right))),
        sharex=True,
        gridspec_kw={"height_ratios": [max(len(left), 1), max(len(right), 1)]},
    )

    x_max = max((r[3].total for r in left + right), default=1)

    def draw(ax, side_rows, side_label):
        if not side_rows:
            ax.text(0.5, 0.5, f"{side_label}: no cards",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=11, color="#666")
            ax.set_yticks([])
            for spine in ("top", "right", "left"):
                ax.spines[spine].set_visible(False)
            return
        labels = [short_name(r[2]) for r in side_rows]
        yel = [r[3].yellow for r in side_rows]
        red = [r[3].red for r in side_rows]
        y = np.arange(len(side_rows))
        bar_h = 0.55
        ax.barh(y, yel, bar_h, color=YELLOW_COLOR, edgecolor="white", linewidth=0.8)
        ax.barh(y, red, bar_h, left=yel, color=RED_COLOR, edgecolor="white", linewidth=0.8)

        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=10)
        ax.set_title(side_label, fontsize=12, fontweight="bold",
                     loc="left", pad=4)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color("#cccccc")
        ax.spines["bottom"].set_color("#cccccc")
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)

    draw(ax_l, left, "Left-side defenders")
    draw(ax_r, right, "Right-side defenders")

    ax_r.set_xlabel("Cards")
    ax_r.set_xlim(0, x_max + 0.3)
    ax_r.set_xticks(np.arange(0, x_max + 1, 1))

    fig.suptitle(f"Defensive cards by side — {team}",
                 fontsize=14, fontweight="bold")
    fig.legend(
        handles=[
            Patch(facecolor=YELLOW_COLOR, label="Yellow"),
            Patch(facecolor=RED_COLOR, label="Red (incl. 2nd yellow)"),
        ],
        loc="lower right", bbox_to_anchor=(0.98, 0.0),
        frameon=False, fontsize=9, ncol=2,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.0, 0.03, 1.0, 0.95))
    fig.savefig(output_path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  saved {output_path}")


def main(team: str, output_path: Path) -> None:
    pos_freq, cards, n_matches = collect(team)

    rows: list[tuple[str, str, str, CardCounts]] = []
    for player, freq in pos_freq.items():
        pos = primary_position(freq)
        if pos not in DEFENSIVE_POSITIONS:
            continue
        side = classify_side(pos)
        if side is None:
            continue
        rows.append((side, pos, player, cards.get(player, CardCounts())))

    print_report(team, n_matches, rows)
    print()
    print(f"Saving plot to {output_path} ...")
    plot(rows, team, output_path)


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else "Barcelona"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    main(team, out)
