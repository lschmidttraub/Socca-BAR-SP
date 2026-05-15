"""
defensive_cards_pitch.py

Half-pitch map of where Barcelona received cards from defensive fouls
that produced an opponent free-kick — same population as the foul → FK
panel in `fouls_freekicks.py`.

Each card is plotted at the foul's location in Barcelona's attacking
frame (own goal at x = 0). Yellow / Second Yellow / Red are coloured
distinctly; player names are annotated next to each dot.

Usage
-----
    python src/defense/fouls/defensive_cards_pitch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT     = PROJECT_ROOT / "src"
FOULS_DIR    = Path(__file__).parent

for _p in (str(SRC_ROOT), str(FOULS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fouls import setpiece_after_foul
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats import filters as f

ASSETS_DIR = PROJECT_ROOT / "assets" / "defense" / "fouls"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
_SB_ROOT  = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS = [
    d for d in (
        _SB_ROOT / phase
        for phase in ("league_phase", "last16", "playoffs", "quarterfinals")
    )
    if d.is_dir()
]
# Fall back to the legacy single-dir layout if the per-phase dirs aren't there.
if not DATA_DIRS and _SB_ROOT.is_dir():
    DATA_DIRS = [_SB_ROOT]


# Visual styling per card type.
CARD_STYLES: dict[str, dict] = {
    "Yellow Card":   {"color": "#F1C40F", "edge": "#7D6608", "label": "Yellow"},
    "Second Yellow": {"color": "#E67E22", "edge": "#6E2C00", "label": "2nd Yellow"},
    "Red Card":      {"color": "#C0392B", "edge": "#641E16", "label": "Red"},
}

# Map StatsBomb full names to the commonly-known short form. The default
# `name.split()[-1]` heuristic fails for compound / multi-surname players
# (e.g. "Ronald Federico Araújo da Silva" → "Silva" instead of "Araújo").
PLAYER_DISPLAY_NAMES: dict[str, str] = {
    "Ronald Federico Araújo da Silva":   "Araújo",
    "Pau Cubarsí Paredes":               "Cubarsí",
    "Eric García Martret":               "Eric García",
    "Pablo Martín Páez Gavira":          "Gavi",
    "Frenkie de Jong":                   "de Jong",
    "Gerard Martín Langreo":             "Gerard Martín",
    "Alejandro Balde Martínez":          "Balde",
    "João Pedro Cavaco Cancelo":         "Cancelo",
    "Lamine Yamal Nasraoui Ebana":       "Yamal",
    "Daniel Olmo Carvajal":              "Olmo",
    "Marc Casadó Torras":                "Casadó",
    "Fermin Lopez Marin":                "Fermín",
    "Jules Koundé":                      "Koundé",
}


def _short_name(full: str) -> str:
    """Best-effort short/known-as form of a StatsBomb full player name."""
    if not full:
        return ""
    if full in PLAYER_DISPLAY_NAMES:
        return PLAYER_DISPLAY_NAMES[full]
    return full.split()[-1]


# ── Data ──────────────────────────────────────────────────────────────────────

def _event_card(ev: dict) -> str | None:
    """Card name on either a Foul Committed or a Bad Behaviour event."""
    for sub_key in ("foul_committed", "bad_behaviour"):
        sub = ev.get(sub_key)
        if isinstance(sub, dict):
            c = sub.get("card")
            if isinstance(c, dict) and c.get("name"):
                return c["name"]
    return None


def _proxy_location(
    events: list[dict], ev_idx: int, player_name: str,
) -> tuple[float, float] | None:
    """Nearest in-event-index event by the same player that has a location.
    Used as a fallback for Bad Behaviour cards (no native location)."""
    n = len(events)
    for d in range(1, n):
        for j in (ev_idx - d, ev_idx + d):
            if not (0 <= j < n):
                continue
            cand = events[j]
            if cand.get("player", {}).get("name") != player_name:
                continue
            loc = cand.get("location")
            if loc and len(loc) >= 2:
                return float(loc[0]), float(loc[1])
    return None


def load_defensive_cards() -> tuple[
    list[float], list[float], list[str], list[str], list[bool],
]:
    """Return (xs, ys, card_names, player_names, off_ball) for every
    Barcelona card on a defensive play in Barca's defending half.

    Two event types are considered:
      • Foul Committed (type 22) — native location, no restart filter
        (penalty restarts excluded only because they sit at x ≥ 102 inside
        the box of the *opposing* attack — but our `x < 60` cut would
        already drop them; we no longer require a FK restart, so every
        card counts).
      • Bad Behaviour (type 24) — off-ball cards (dissent, etc.). Location,
        if missing, is filled in from the same player's nearest event in
        the match (and the card is flagged `off_ball=True`).

    Filters applied to both:
      • team = Barcelona
      • possession_team ≠ Barcelona (Barca was defending)
      • card was issued
      • foul location in Barca's defending half (x < 60)

    Coordinates are in Barca's attacking frame (own goal at x = 0).
    """
    xs: list[float] = []
    ys: list[float] = []
    cards: list[str] = []
    players: list[str] = []
    off_ball: list[bool] = []

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            barca_sb = _team_in_match("Barcelona", row, events)
            if barca_sb is None:
                continue

            for idx, ev in enumerate(events):
                type_id = ev.get("type", {}).get("id")
                if type_id not in (22, 24):  # Foul Committed, Bad Behaviour
                    continue
                if ev.get("team", {}).get("name", "") != barca_sb:
                    continue
                if ev.get("possession_team", {}).get("name", "") == barca_sb:
                    continue  # only defensive plays

                card_name = _event_card(ev)
                if not card_name:
                    continue

                # Resolve location (native or proxy for Bad Behaviour).
                loc = ev.get("location")
                if loc and len(loc) >= 2:
                    x, y = float(loc[0]), float(loc[1])
                    is_off = (type_id == 24)
                else:
                    if type_id != 24:
                        continue  # Foul Committed with no location: skip
                    proxy = _proxy_location(
                        events, idx, ev.get("player", {}).get("name", ""),
                    )
                    if proxy is None:
                        continue
                    x, y = proxy
                    is_off = True

                # Defending half only.
                if x >= 60.0:
                    continue

                xs.append(x)
                ys.append(y)
                cards.append(card_name)
                players.append(ev.get("player", {}).get("name", "") or "")
                off_ball.append(is_off)

    return xs, ys, cards, players, off_ball


# ── Plot ──────────────────────────────────────────────────────────────────────

def plot_defensive_cards(
    xs: list[float], ys: list[float],
    cards: list[str], players: list[str], off_ball: list[bool],
    output_dir: Path,
) -> Path:
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#bbbbbb",
        linewidth=1.2,
    )

    fig, ax = plt.subplots(figsize=(10, 9))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(top=0.84, bottom=0.06, left=0.06, right=0.94)
    pitch.draw(ax=ax)
    ax.set_xlim(-1, 61)

    counts: dict[str, int] = {}
    n_off_ball = 0
    for x, y, c, p, is_off in zip(xs, ys, cards, players, off_ball):
        style = CARD_STYLES.get(c, {"color": "#888888", "edge": "#222222"})
        counts[c] = counts.get(c, 0) + 1
        if is_off:
            n_off_ball += 1

        pitch.scatter(
            x, y, ax=ax,
            s=240,
            color=style["color"],
            edgecolors=style["edge"],
            linewidths=1.4,
            # Off-ball cards (Bad Behaviour) get a hatched fill and lower
            # alpha so the proxy location is visually distinct.
            hatch="//" if is_off else None,
            alpha=0.55 if is_off else 0.92,
            zorder=4,
        )
        # Common short name — keeps annotations short and recognisable.
        short = _short_name(p)
        if short:
            suffix = "*" if is_off else ""
            ax.text(
                x, y - 2.5, short + suffix,
                ha="center", va="top",
                fontsize=7.5, color="#222222",
                zorder=5,
            )

    # Legend with per-card totals
    legend_items = []
    for card_name, style in CARD_STYLES.items():
        n = counts.get(card_name, 0)
        if n == 0:
            continue
        legend_items.append(Line2D(
            [0], [0], marker="o", color="w",
            markerfacecolor=style["color"], markeredgecolor=style["edge"],
            markersize=11, markeredgewidth=1.4,
            label=f"{style['label']} (n = {n})",
        ))
    if legend_items:
        ax.legend(
            handles=legend_items, loc="upper right",
            fontsize=9, frameon=True, framealpha=0.92,
        )

    fig.text(
        0.5, 0.95,
        "Barcelona defensive cards (out-of-possession fouls → opponent FK)",
        ha="center", va="top",
        fontsize=15, fontweight="bold", color="#111111",
    )
    off_note = f"  ·  hatched* = off-ball (Bad Behaviour, proxy loc): {n_off_ball}" if n_off_ball else ""
    fig.text(
        0.5, 0.91,
        f"Defending half only (Barca's goal on LEFT)  ·  total cards: {len(xs)}{off_note}",
        ha="center", va="top",
        fontsize=10, color="#555555",
    )

    out_path = output_dir / "defensive_cards_pitch.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"Saved -> {out_path}")
    plt.show()
    return out_path


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading Barcelona defensive cards …")
    xs, ys, cards, players, off_ball = load_defensive_cards()
    print(f"  Total cards: {len(xs)}")
    from collections import Counter
    for name, n in Counter(cards).most_common():
        print(f"    {name}: {n}")
    n_off = sum(off_ball)
    if n_off:
        print(f"  Off-ball (Bad Behaviour, proxy location): {n_off}")
    plot_defensive_cards(xs, ys, cards, players, off_ball, ASSETS_DIR)
