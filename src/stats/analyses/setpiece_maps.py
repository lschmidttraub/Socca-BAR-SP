"""Pitch maps of every set piece type across all of a team's matches.

For each set piece kind, produces a pitch plot with the focus team in
red and opponents in blue.  Opponent coordinates are flipped so that
the focus team always attacks to the right (x = 120).

- Corners: trajectory arrows, single pitch
- Free kicks, throw-ins: trajectory arrows, split into two pitches
- Goal kicks: scatter of where the ball lands, single pitch

Saves all figures to ``assets/setpiece_maps/{team}/``.
"""

from pathlib import Path

import matplotlib.pyplot as plt
from mplsoccer import Pitch

import numpy as np

from .. import filters as f
from ..data import iter_matches
from ..viz.style import FOCUS_COLOR, AVG_COLOR, TEAM_PALETTE, apply_theme, save_fig

ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "setpiece_maps"
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"

# ── Set piece definitions ────────────────────────────────────────────

SET_PIECE_TYPES = [
    ("corners",    lambda e: f.is_corner_pass(e)),
    ("free_kicks", lambda e: f.is_fk_pass(e) or f.is_fk_shot(e)),
    ("throw_ins",  lambda e: f.is_throw_in(e)),
    ("goal_kicks", lambda e: f.is_goal_kick(e)),
]

# These get two separate pitches (one per team)
SPLIT_TYPES = {"free_kicks", "throw_ins"}


# ── Data collection ──────────────────────────────────────────────────

def _team_in_match(team: str, row: dict, events: list[dict]) -> str | None:
    """Return the StatsBomb team name if *team* plays in this match.

    Matches against both the CSV columns (``home``/``away``) and the
    team names inside the events, so that e.g. ``"PSG"`` in the CSV
    still resolves to ``"Paris Saint-Germain"`` in the events.
    """
    home, away = row.get("home", ""), row.get("away", "")
    if team in (home, away):
        # Find the matching StatsBomb name from the events
        event_teams = {e.get("team", {}).get("name") for e in events[:6] if e.get("team")}
        for et in event_teams:
            if et == team:
                return et
        # CSV name differs from event name — match by position
        if team == home:
            return (event_teams - {away}).pop() if len(event_teams) == 2 else None
        return (event_teams - {home}).pop() if len(event_teams) == 2 else None

    # Also check directly against event team names
    event_teams = {e.get("team", {}).get("name") for e in events[:6] if e.get("team")}
    if team in event_teams:
        return team
    return None


def _collect_events(team: str, data_dir: Path) -> dict[str, dict[str, list[dict]]]:
    """Return ``{set_piece: {"team": [...], "opponent": [...]}}``."""
    result = {name: {"team": [], "opponent": []} for name, _ in SET_PIECE_TYPES}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue

        for e in events:
            for sp_name, predicate in SET_PIECE_TYPES:
                if not predicate(e):
                    continue
                if f.by_team(e, sb_name):
                    result[sp_name]["team"].append(e)
                else:
                    result[sp_name]["opponent"].append(e)

    return result


def _flip(x: float, y: float) -> tuple[float, float]:
    """Flip coordinates so the opponent attacks toward x = 0."""
    return 120 - x, 80 - y


# ── Drawing helpers ──────────────────────────────────────────────────

def _draw_arrows(
    pitch: Pitch,
    ax: plt.Axes,
    events: list[dict],
    color: str,
    flip: bool = False,
) -> None:
    """Draw pass/shot arrows for a set of events."""
    for e in events:
        loc = e.get("location")
        end = e.get("pass", {}).get("end_location") or e.get("shot", {}).get("end_location")
        if not loc or not end:
            continue
        x1, y1 = loc[0], loc[1]
        x2, y2 = end[0], end[1]
        if flip:
            x1, y1 = _flip(x1, y1)
            x2, y2 = _flip(x2, y2)
        completed = e.get("pass", {}).get("outcome") is None
        alpha = 0.7 if completed else 0.3
        pitch.arrows(x1, y1, x2, y2, ax=ax,
                     color=color, width=1.5, headwidth=5, headlength=4,
                     alpha=alpha, zorder=2)


def _draw_scatter_end(
    pitch: Pitch,
    ax: plt.Axes,
    events: list[dict],
    color: str,
    label: str,
    flip: bool = False,
) -> None:
    """Scatter end locations for a set of events."""
    xs, ys = [], []
    for e in events:
        end = e.get("pass", {}).get("end_location")
        if not end:
            continue
        x, y = end[0], end[1]
        if flip:
            x, y = _flip(x, y)
        xs.append(x)
        ys.append(y)
    if xs:
        pitch.scatter(xs, ys, ax=ax, s=60,
                      color=color, edgecolors="white", linewidth=0.5,
                      alpha=0.7, zorder=2, label=label)


# ── Plot builders ────────────────────────────────────────────────────

def _make_pitch() -> Pitch:
    return Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#c7d5cc")


def _mirror_y(events: list[dict]) -> list[dict]:
    """Return copies of events with y-coordinates mirrored around y=40.

    Events already on the bottom half (y >= 40) are untouched.
    Top-side events (y < 40) get ``y → 80 - y`` for both
    ``location`` and ``pass.end_location``.
    """
    out = []
    for e in events:
        loc = e.get("location")
        if not loc:
            out.append(e)
            continue
        if loc[1] >= 40:
            out.append(e)
            continue
        # Deep-copy only the fields we mutate
        e2 = {**e, "location": [loc[0], 80 - loc[1]]}
        p = e.get("pass")
        if p:
            e2["pass"] = {**p}
            end = p.get("end_location")
            if end:
                e2["pass"]["end_location"] = [end[0], 80 - end[1]]
        s = e.get("shot")
        if s:
            e2["shot"] = {**s}
            end = s.get("end_location")
            if end:
                e2["shot"]["end_location"] = [end[0], 80 - end[1]]
        out.append(e2)
    return out


def _plot_corners(
    team: str,
    team_events: list[dict],
    opp_events: list[dict],
    title: str,
) -> plt.Figure:
    """Two pitches: full view on top, mirrored half-pitch below."""
    fig = plt.figure(figsize=(12, 16))

    # ── Top: full pitch, both teams ──────────────────────────────
    pitch_full = _make_pitch()
    ax_full = fig.add_axes([0.05, 0.52, 0.9, 0.40])
    pitch_full.draw(ax=ax_full)

    _draw_arrows(pitch_full, ax_full, team_events, FOCUS_COLOR, flip=False)
    _draw_arrows(pitch_full, ax_full, opp_events, AVG_COLOR, flip=True)
    ax_full.set_title(title, fontsize=14, fontweight="bold", pad=10)

    # ── Bottom: full pitch, top-side corners mirrored to bottom ──
    pitch_mirror = _make_pitch()
    ax_mirror = fig.add_axes([0.05, 0.06, 0.9, 0.40])
    pitch_mirror.draw(ax=ax_mirror)

    mirrored_team = _mirror_y(team_events)
    mirrored_opp = _mirror_y(opp_events)

    _draw_arrows(pitch_mirror, ax_mirror, mirrored_team, FOCUS_COLOR, flip=False)
    _draw_arrows(pitch_mirror, ax_mirror, mirrored_opp, AVG_COLOR, flip=True)
    ax_mirror.set_title(
        "All corners normalised to bottom side",
        fontsize=12, fontweight="bold", pad=8,
    )

    _add_legend(fig, team)
    return fig


def _plot_combined_arrows(
    team: str,
    team_events: list[dict],
    opp_events: list[dict],
    title: str,
) -> plt.Figure:
    """Single pitch with both teams' arrows + legend below."""
    pitch = _make_pitch()
    fig, ax = pitch.draw(figsize=(12, 8))

    _draw_arrows(pitch, ax, team_events, FOCUS_COLOR, flip=False)
    _draw_arrows(pitch, ax, opp_events, AVG_COLOR, flip=True)

    _add_legend(fig, team)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    return fig


def _plot_split_arrows(
    team: str,
    team_events: list[dict],
    opp_events: list[dict],
    title: str,
) -> plt.Figure:
    """Two pitches stacked — focus team on top, opponent below."""
    pitch = _make_pitch()
    fig, axes = pitch.draw(nrows=2, ncols=1, figsize=(12, 14))

    ax_team = axes[0]
    ax_opp = axes[1]

    _draw_arrows(pitch, ax_team, team_events, FOCUS_COLOR, flip=False)
    ax_team.set_title(f"{team} ({len(team_events)})", fontsize=12, fontweight="bold", pad=8)

    _draw_arrows(pitch, ax_opp, opp_events, AVG_COLOR, flip=True)
    ax_opp.set_title(f"Opponent ({len(opp_events)})", fontsize=12, fontweight="bold", pad=8)

    fig.suptitle(title, fontsize=14, fontweight="bold", y=0.98)
    return fig


def _plot_combined_scatter(
    team: str,
    team_events: list[dict],
    opp_events: list[dict],
    title: str,
) -> plt.Figure:
    """Single pitch with scatter of landing locations + legend below."""
    pitch = _make_pitch()
    fig, ax = pitch.draw(figsize=(12, 8))

    _draw_scatter_end(pitch, ax, team_events, FOCUS_COLOR, team, flip=False)
    _draw_scatter_end(pitch, ax, opp_events, AVG_COLOR, "Opponent", flip=True)

    _add_legend(fig, team)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    return fig


def _add_legend(fig: plt.Figure, team: str) -> None:
    """Add a legend below the pitch, outside the playing area."""
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=FOCUS_COLOR,
               markersize=10, label=team),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=AVG_COLOR,
               markersize=10, label="Opponent"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=11,
               frameon=False, bbox_to_anchor=(0.5, 0.01))
    fig.subplots_adjust(bottom=0.07)


# ── Penalties ────────────────────────────────────────────────────────

# Goal dimensions in StatsBomb coordinates
GOAL_Y_MIN = 36.0  # left post (yards)
GOAL_Y_MAX = 44.0  # right post (yards)
GOAL_HEIGHT = 2.67  # crossbar height (yards, ≈ 8 ft)


def _collect_penalties(team: str, data_dir: Path) -> dict[str, list[dict]]:
    """Return ``{"team": [...], "opponent": [...]}`` penalty shot events."""
    result: dict[str, list[dict]] = {"team": [], "opponent": []}

    for row, events in iter_matches(data_dir):
        sb_name = _team_in_match(team, row, events)
        if sb_name is None:
            continue
        for e in events:
            if not f.is_penalty_shot(e):
                continue
            if f.by_team(e, sb_name):
                result["team"].append(e)
            else:
                result["opponent"].append(e)

    return result


def _plot_penalties(
    team: str,
    team_events: list[dict],
    opp_events: list[dict],
    title: str,
) -> plt.Figure:
    """Front-view goal plot with per-player colours for the focus team."""
    fig, (ax_team, ax_opp) = plt.subplots(1, 2, figsize=(14, 5))

    # Assign a colour per focus-team player
    players = sorted({f.event_player(e) for e in team_events})
    player_colors = {p: TEAM_PALETTE[i % len(TEAM_PALETTE)] for i, p in enumerate(players)}

    _draw_goal(ax_team)
    for e in team_events:
        _plot_penalty_marker(ax_team, e, player_colors.get(f.event_player(e), FOCUS_COLOR))
    ax_team.set_title(f"{team} ({len(team_events)})", fontsize=12, fontweight="bold")

    # Legend for focus team players
    from matplotlib.lines import Line2D
    handles = []
    for p in players:
        handles.append(Line2D([0], [0], marker="o", color="w",
                              markerfacecolor=player_colors[p], markersize=8, label=p))
    if handles:
        ax_team.legend(handles=handles, loc="upper left", fontsize=8,
                       frameon=True, fancybox=True, framealpha=0.8,
                       bbox_to_anchor=(0.0, -0.02), ncol=min(len(handles), 3))

    _draw_goal(ax_opp)
    for e in opp_events:
        _plot_penalty_marker(ax_opp, e, AVG_COLOR)
    ax_opp.set_title(f"Opponent ({len(opp_events)})", fontsize=12, fontweight="bold")

    # Marker legend (goal vs save/miss)
    marker_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="gray",
               markersize=8, label="Goal"),
        Line2D([0], [0], marker="X", color="w", markerfacecolor="gray",
               markeredgecolor="gray", markersize=8, label="Saved / Missed"),
    ]
    ax_opp.legend(handles=marker_handles, loc="upper left", fontsize=8,
                  frameon=True, fancybox=True, framealpha=0.8,
                  bbox_to_anchor=(0.0, -0.02))

    fig.suptitle(title, fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    return fig


def _draw_goal(ax: plt.Axes) -> None:
    """Draw a front-view goal frame."""
    # Goal frame
    ax.plot(
        [GOAL_Y_MIN, GOAL_Y_MIN, GOAL_Y_MAX, GOAL_Y_MAX],
        [0, GOAL_HEIGHT, GOAL_HEIGHT, 0],
        color="#333333", linewidth=3, zorder=1,
    )
    # Grass
    ax.axhspan(-0.3, 0, color="#a8d5a2", zorder=0)
    # Net shading
    ax.fill_between(
        [GOAL_Y_MIN, GOAL_Y_MAX], 0, GOAL_HEIGHT,
        color="#f0f0f0", zorder=0,
    )

    ax.set_xlim(GOAL_Y_MIN - 1, GOAL_Y_MAX + 1)
    ax.set_ylim(-0.3, GOAL_HEIGHT + 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Width (yards)")
    ax.set_ylabel("Height (yards)")
    ax.tick_params(labelsize=8)


def _plot_penalty_marker(ax: plt.Axes, event: dict, color: str) -> None:
    """Plot a single penalty on the goal-front axes."""
    end = event.get("shot", {}).get("end_location")
    if not end or len(end) < 3:
        return

    y, z = end[1], end[2]
    is_goal = f.is_goal(event)
    marker = "o" if is_goal else "X"
    size = 120 if is_goal else 100

    ax.scatter(y, z, s=size, marker=marker, color=color,
               edgecolors="white" if is_goal else color,
               linewidth=0.8, zorder=3, alpha=0.9)


# ── Entry point ──────────────────────────────────────────────────────

def run(team: str = TEAM, data_dir: Path = DATA, output_dir: Path | None = None) -> None:
    """Generate and save all set piece pitch maps for *team*."""
    if output_dir is None:
        output_dir = ASSETS_ROOT / team

    apply_theme()
    collected = _collect_events(team, data_dir)

    for sp_name, _ in SET_PIECE_TYPES:
        team_evts = collected[sp_name]["team"]
        opp_evts = collected[sp_name]["opponent"]
        label = sp_name.replace("_", " ").title()
        title = f"{team} {label} — all matches ({len(team_evts)} {team}, {len(opp_evts)} opponent)"

        if sp_name == "corners":
            fig = _plot_corners(team, team_evts, opp_evts, title)
        elif sp_name in SPLIT_TYPES:
            fig = _plot_split_arrows(team, team_evts, opp_evts, title)
        elif sp_name == "goal_kicks":
            fig = _plot_combined_scatter(team, team_evts, opp_evts, title)
        else:
            fig = _plot_combined_arrows(team, team_evts, opp_evts, title)

        save_fig(fig, output_dir / f"{sp_name}.png")
        print(f"  {sp_name}: {len(team_evts)} {team}, {len(opp_evts)} opponent → {output_dir / sp_name}.png")

    # Penalties (separate collection — goal-front view)
    pens = _collect_penalties(team, data_dir)
    team_pens = pens["team"]
    opp_pens = pens["opponent"]
    title = f"{team} Penalties — all matches ({len(team_pens)} {team}, {len(opp_pens)} opponent)"
    fig = _plot_penalties(team, team_pens, opp_pens, title)
    save_fig(fig, output_dir / "penalties.png")
    print(f"  penalties: {len(team_pens)} {team}, {len(opp_pens)} opponent → {output_dir / 'penalties.png'}")

    print(f"Done — saved to {output_dir}/")


if __name__ == "__main__":
    run()
