"""Barcelona offensive free kicks — player roles by pitch third.

For each of the three pitch thirds (own, middle, opponents) shows:
  - Top FK takers
  - Top first receivers (pass recipient, or taker if direct shot)

Attacking direction is normalised left-to-right using CSV home/away columns.
Thirds are defined in normalised coordinates (attack toward x=120):
  Own third:        x  0 – 40
  Middle third:     x 40 – 80
  Opponents third:  x 80 – 120

Output: assets/freekick_player_roles_by_zone.png
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT     = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.analyses.setpiece_maps import _team_in_match
from stats.viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig

ASSETS_ROOT = PROJECT_ROOT / "assets"
_SB_ROOT    = PROJECT_ROOT / "data" / "statsbomb"
DATA_DIRS   = [d for d in (_SB_ROOT / phase for phase in ("league_phase", "last16", "playoffs", "quarterfinals")) if d.is_dir()]
DATA        = _SB_ROOT
TEAM        = "Barcelona"

SEQUENCE_MAX_SECONDS = 20.0

THIRDS = ["Own third", "Middle third", "Opponents third"]
THIRD_COLORS = {
    "Own third":        "#4575b4",
    "Middle third":     "#f28e2b",
    "Opponents third":  FOCUS_COLOR,
}


# ── normalisation ─────────────────────────────────────────────────────
# StatsBomb already orients every event so the team in possession attacks
# toward x=120. No y-flip — raw positions used so the pitch third (x)
# is correct and both sides are represented naturally.

def _normalise(loc: list) -> tuple[float, float]:
    return float(loc[0]), float(loc[1])


def _pitch_third(x: float) -> str:
    if x < 40:
        return "Own third"
    if x < 80:
        return "Middle third"
    return "Opponents third"


# ── data collection ───────────────────────────────────────────────────

def _is_fk_event(e: dict) -> bool:
    return f.is_fk_pass(e) or f.is_fk_shot(e)


def _collect(data_dir: Path) -> list[dict]:
    """Return one dict per Barcelona FK event with taker, receiver, third."""
    results: list[dict] = []

    for _d in DATA_DIRS:
        for row, events in iter_matches(_d):
            sb_name = _team_in_match(TEAM, row, events)
            if sb_name is None:
                continue

            for idx, event in enumerate(events):
                if not (_is_fk_event(event) and f.by_team(event, sb_name)):
                    continue
                loc = event.get("location")
                if not loc:
                    continue

                nx, _ = _normalise(loc)

                taker = f.event_player(event) or "Unknown"

                if f.is_fk_pass(event):
                    receiver = (event.get("pass", {})
                                     .get("recipient", {})
                                     .get("name") or "Unknown")
                else:
                    receiver = taker

                results.append({
                    "fk_x":     nx,
                    "third":    _pitch_third(nx),
                    "taker":    taker,
                    "receiver": receiver,
                })

    return results


# ── plotting ──────────────────────────────────────────────────────────

def _hbar(ax: plt.Axes, counter: Counter, title: str, color: str,
          top_n: int = 8, shared_max: float | None = None) -> None:
    top = counter.most_common(top_n)
    if not top:
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_visible(False)
        return

    names, vals = zip(*reversed(top))
    bars = ax.barh(names, vals, color=color, alpha=0.87, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, vals):
        ax.text(val + 0.12, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=8.5)
    ax.set_title(title, fontsize=10, fontweight="bold", pad=6)
    ax.set_xlabel("Count", fontsize=8)
    x_max = (shared_max or max(vals)) * 1.22
    ax.set_xlim(0, x_max)
    ax.tick_params(axis="y", labelsize=8.5)
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", alpha=0.25)


def _plot(sequences: list[dict], output_path: Path) -> None:
    # Split by third
    by_third: dict[str, list[dict]] = {t: [] for t in THIRDS}
    for s in sequences:
        by_third[s["third"]].append(s)

    # Build counters
    taker_counters    = {t: Counter(s["taker"]    for s in by_third[t]
                                    if s["taker"] != "Unknown")
                         for t in THIRDS}
    receiver_counters = {t: Counter(s["receiver"] for s in by_third[t]
                                    if s["receiver"] not in ("Unknown", s["taker"]))
                         for t in THIRDS}

    # Shared x-max per row so bars are comparable across thirds
    taker_max    = max((c.most_common(1)[0][1] if c else 0)
                       for c in taker_counters.values())
    receiver_max = max((c.most_common(1)[0][1] if c else 0)
                       for c in receiver_counters.values())

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    fig.subplots_adjust(top=0.88, bottom=0.06, hspace=0.42, wspace=0.38)

    for col, third in enumerate(THIRDS):
        color  = THIRD_COLORS[third]
        n      = len(by_third[third])
        label  = f"{third}  (n={n})"

        _hbar(axes[0, col], taker_counters[third],
              f"Takers — {label}", AVG_COLOR,
              shared_max=float(taker_max))
        _hbar(axes[1, col], receiver_counters[third],
              f"Receivers — {label}", FOCUS_COLOR,
              shared_max=float(receiver_max))

    fig.text(0.5, 0.965, "Barcelona offensive free kicks — player roles by pitch third",
             ha="center", va="top", fontsize=16, fontweight="bold", color="#111111")
    fig.text(0.5, 0.930,
             "Top FK takers (row 1) and first receivers (row 2)  "
             "|  own third: x 0–40  ·  middle: 40–80  ·  opponents: 80–120  "
             "|  StatsBomb normalises each event: team always attacks right",
             ha="center", va="top", fontsize=9.5, color="#444444")

    save_fig(fig, output_path, tight=False)


# ── entry point ───────────────────────────────────────────────────────

def run(data_dir: Path = DATA, output_dir: Path = ASSETS_ROOT) -> None:
    apply_theme()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Collecting Barcelona FK events (full pitch, normalised) ...")
    sequences = _collect(data_dir)
    print(f"  {len(sequences)} FK events")
    for t in THIRDS:
        n = sum(1 for s in sequences if s["third"] == t)
        print(f"    {t}: {n}")

    out = output_dir / "freekick_player_roles_by_zone.png"
    print("Building figure ...")
    _plot(sequences, out)
    print(f"  Saved: {out}")
    print("Done.")


if __name__ == "__main__":
    run()