"""Set pieces by player for the focus team.

For each set piece type, produces a horizontal bar chart of how many
set pieces each player took, coloured by position group
(defence / midfield / attack).

Free kicks and throw-ins are split into attacking half (x >= 60) and
defending half (x < 60) charts.

Saves all figures to ``assets/setpiece_players/{team}/``.
"""

from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .. import filters as f
from ..data import iter_matches
from ..viz.style import apply_theme, save_fig
from .setpiece_maps import _team_in_match

ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "setpiece_players"
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"

# ── Position classification ──────────────────────────────────────────

DEFENCE_COLOR = "#2166ac"
MIDFIELD_COLOR = "#66c2a5"
ATTACK_COLOR = "#d6604d"

_DEFENCE_KEYWORDS = {"Back", "Center Back"}
_ATTACK_KEYWORDS = {"Forward", "Wing"}


def _position_group(position_name: str) -> str:
    """Classify a StatsBomb position name into defence / midfield / attack."""
    if any(kw in position_name for kw in _ATTACK_KEYWORDS):
        return "attack"
    if any(kw in position_name for kw in _DEFENCE_KEYWORDS):
        return "defence"
    if "Goalkeeper" in position_name:
        return "defence"
    return "midfield"


GROUP_COLORS = {
    "defence": DEFENCE_COLOR,
    "midfield": MIDFIELD_COLOR,
    "attack": ATTACK_COLOR,
}

# ── Set piece definitions ────────────────────────────────────────────

# (key, predicate) — corners and penalties are not split by half
SIMPLE_TYPES = [
    ("corners",   lambda e: f.is_corner_pass(e)),
    ("penalties",  lambda e: f.is_penalty_shot(e)),
]

# These are split into attacking / defending halves
SPLIT_TYPES = [
    ("free_kicks", lambda e: f.is_fk_pass(e) or f.is_fk_shot(e)),
    ("throw_ins",  lambda e: f.is_throw_in(e)),
]

HALF_LINE = 60  # x >= 60 → attacking half


# ── Data collection ──────────────────────────────────────────────────

def _collect_player_positions(team_sb: str, events: list[dict]) -> dict[str, str]:
    """Return {player_name: position_group} from Starting XI events."""
    positions: dict[str, str] = {}
    for e in events:
        if e.get("type", {}).get("id") != 35:
            continue
        if e.get("team", {}).get("name") != team_sb:
            continue
        for p in e.get("tactics", {}).get("lineup", []):
            name = p["player"]["name"]
            pos = p["position"]["name"]
            if name not in positions:
                positions[name] = _position_group(pos)
    return positions


def _collect(
    team: str, data_dir: Path,
) -> tuple[dict[str, dict[str, int]], dict[str, str]]:
    """Collect per-player set piece counts and position mappings.

    Returns (counts, positions) where:
    - counts: {key: {player: count}}
      Keys include e.g. "corners", "penalties",
      "free_kicks_attacking", "free_kicks_defending", etc.
    - positions: {player: "defence" | "midfield" | "attack"}
    """
    keys = [name for name, _ in SIMPLE_TYPES]
    for name, _ in SPLIT_TYPES:
        keys.append(f"{name}_attacking")
        keys.append(f"{name}_defending")

    counts: dict[str, dict[str, int]] = {k: defaultdict(int) for k in keys}
    positions: dict[str, str] = {}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue

        match_positions = _collect_player_positions(sb_name, events)
        for name, group in match_positions.items():
            if name not in positions:
                positions[name] = group

        for e in events:
            if not f.by_team(e, sb_name):
                continue
            player = f.event_player(e)
            if not player:
                continue

            for sp_name, predicate in SIMPLE_TYPES:
                if predicate(e):
                    counts[sp_name][player] += 1

            for sp_name, predicate in SPLIT_TYPES:
                if not predicate(e):
                    continue
                loc = e.get("location")
                if loc and loc[0] >= HALF_LINE:
                    counts[f"{sp_name}_attacking"][player] += 1
                else:
                    counts[f"{sp_name}_defending"][player] += 1

    return counts, positions


# ── Plotting ─────────────────────────────────────────────────────────

def _position_legend() -> list[Line2D]:
    return [
        Line2D([0], [0], marker="s", color="w", markerfacecolor=DEFENCE_COLOR,
               markersize=10, label="Defence"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=MIDFIELD_COLOR,
               markersize=10, label="Midfield"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=ATTACK_COLOR,
               markersize=10, label="Attack"),
    ]


def _plot_player_bars(
    team: str,
    title: str,
    player_counts: dict[str, int],
    positions: dict[str, str],
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Horizontal bar chart of per-player counts, coloured by position."""
    ranked = sorted(player_counts.items(), key=lambda x: x[1], reverse=True)
    ranked = [(p, c) for p, c in ranked if c > 0]

    if ax is None:
        fig, ax = plt.subplots(figsize=(10, max(4, len(ranked) * 0.35)))
    else:
        fig = ax.figure

    if not ranked:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=14,
                transform=ax.transAxes)
        ax.set_axis_off()
        return fig, ax

    names = [p for p, _ in ranked]
    vals = [c for _, c in ranked]
    colors = [GROUP_COLORS.get(positions.get(p, "midfield"), MIDFIELD_COLOR) for p in names]

    ax.barh(names, vals, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel("Count")
    ax.set_title(title, fontsize=12, fontweight="bold")

    return fig, ax


def _plot_simple(
    team: str,
    sp_name: str,
    player_counts: dict[str, int],
    positions: dict[str, str],
) -> plt.Figure:
    """Single chart for corners / penalties."""
    sp_label = sp_name.replace("_", " ").title()
    total = sum(player_counts.values())
    title = f"{team} {sp_label} by player ({total} total)"
    fig, ax = _plot_player_bars(team, title, player_counts, positions)
    ax.legend(handles=_position_legend(), loc="lower right", fontsize=9,
              frameon=True, fancybox=True, framealpha=0.8)
    return fig


def _plot_split(
    team: str,
    sp_name: str,
    attacking: dict[str, int],
    defending: dict[str, int],
    positions: dict[str, str],
) -> plt.Figure:
    """Two charts side by side: attacking half vs defending half."""
    sp_label = sp_name.replace("_", " ").title()
    total = sum(attacking.values()) + sum(defending.values())

    # Figure out height from the busier chart
    n_atk = sum(1 for c in attacking.values() if c > 0)
    n_def = sum(1 for c in defending.values() if c > 0)
    n_max = max(n_atk, n_def, 3)

    fig, (ax_atk, ax_def) = plt.subplots(1, 2, figsize=(16, max(5, n_max * 0.35)))

    _plot_player_bars(
        team, f"Attacking half ({sum(attacking.values())})",
        attacking, positions, ax=ax_atk,
    )
    _plot_player_bars(
        team, f"Defending half ({sum(defending.values())})",
        defending, positions, ax=ax_def,
    )

    ax_def.legend(handles=_position_legend(), loc="lower right", fontsize=9,
                  frameon=True, fancybox=True, framealpha=0.8)

    fig.suptitle(f"{team} {sp_label} by player ({total} total)",
                 fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


# ── Entry point ──────────────────────────────────────────────────────

def run(team: str = TEAM, data_dir: Path = DATA, output_dir: Path | None = None) -> None:
    """Generate and save per-player set piece charts for *team*."""
    if output_dir is None:
        output_dir = ASSETS_ROOT / team

    apply_theme()
    counts, positions = _collect(team, data_dir)

    for sp_name, _ in SIMPLE_TYPES:
        fig = _plot_simple(team, sp_name, counts[sp_name], positions)
        save_fig(fig, output_dir / f"{sp_name}.png")
        total = sum(counts[sp_name].values())
        print(f"  {sp_name}: {total} total → {output_dir / sp_name}.png")

    for sp_name, _ in SPLIT_TYPES:
        atk = counts[f"{sp_name}_attacking"]
        dfn = counts[f"{sp_name}_defending"]
        fig = _plot_split(team, sp_name, atk, dfn, positions)
        save_fig(fig, output_dir / f"{sp_name}.png")
        total = sum(atk.values()) + sum(dfn.values())
        print(f"  {sp_name}: {total} total (atk {sum(atk.values())}, def {sum(dfn.values())}) → {output_dir / sp_name}.png")

    print(f"Done — saved to {output_dir}/")


if __name__ == "__main__":
    run()
