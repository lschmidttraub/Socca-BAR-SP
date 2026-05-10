"""
def_fk_runs.py

Per-FK trajectory map.  For every defensive free kick conceded by
Barcelona we follow the ball from the opponent's FK taker through every
subsequent opponent action (pass / carry / shot) until Barcelona
regains possession or the ball leaves play.  Each edge is colour-coded
by event type:

    Pass   – blue
    Carry  – orange
    Shot   – red

Runs that end in a shot are drawn slightly thicker so dangerous
sequences stand out.

Outputs:
  def_fk_runs.png         All runs overlaid on a full pitch
  def_fk_runs_shots.png   Subset of runs that ended in a shot

Usage:
    python src/defense/free_kicks/def_fk_runs.py
"""

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mplsoccer import Pitch

from defending_free_kicks import (
    BARCELONA,
    DEF_FK_ASSETS_DIR,
    is_fk_event,
    is_fk_pass,
    is_fk_shot,
    read_statsbomb,
    team_games,
)


def collect_all_defending_fk_pairs() -> list[tuple]:
    """Like ``build_pairs`` but without the attacking-half restriction
    — every opponent free-kick anywhere on the pitch is included."""
    pairs: list[tuple] = []
    for game_id in team_games(BARCELONA):
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue
        for ev in events:
            if not is_fk_event(ev):
                continue
            team = ev.get("team", {}).get("name", "")
            if BARCELONA.casefold() in team.casefold():
                continue
            pairs.append((ev, events))
    return pairs


# ── Colour scheme ─────────────────────────────────────────────────────────────

COLOR_PASS = "#1f77b4"
COLOR_CARRY = "#ff7f0e"
COLOR_SHOT = "#d62728"

EDGE_COLORS = {
    "pass":  COLOR_PASS,
    "carry": COLOR_CARRY,
    "shot":  COLOR_SHOT,
}

# Opponent-side events that end possession (ball dead / lost on the ball).
OPP_TERMINATING_TYPES = {"Miscontrol", "Dispossessed", "Offside", "Foul Committed"}

# Barcelona-side events that mean Barca actually touched the ball — i.e.
# possession is regained.  Off-ball events such as ``Pressure``, ``Duel``
# (defensive), tactical shifts, etc. do NOT end the run, since the ball
# is still with the opponent during them.
BARCA_TERMINATING_TYPES = {
    "Clearance", "Interception", "Block",
    "Ball Recovery", "Goal Keeper",
    "Foul Won",  # Barcelona drew a foul -> opp possession ends
}


# ── Run construction ─────────────────────────────────────────────────────────

def _xy(loc) -> list[float] | None:
    """Coerce a StatsBomb location (which may be 2D or 3D for shots)
    to a 2D ``[x, y]`` list, or ``None`` if missing/invalid."""
    if not isinstance(loc, (list, tuple)) or len(loc) < 2:
        return None
    return [float(loc[0]), float(loc[1])]


def build_fk_run(fk_ev: dict, events: list, fk_loc: list[float]) -> list[dict]:
    """Walk events forward from *fk_ev* and return one edge dict per
    movement of the ball, until the opponent loses possession.

    Each edge is ``{"start": [x,y], "end": [x,y], "kind": pass|carry|shot}``
    with coordinates already normalised to the right half of the pitch.
    """
    opp = fk_ev.get("team", {}).get("name", "")
    fk_index = fk_ev.get("index", -1)

    edges: list[dict] = []

    def _add(start: list[float], end: list[float], kind: str,
             goal: bool = False) -> None:
        """Append an edge while keeping the path visually connected
        (StatsBomb event locations can drift between consecutive
        events).  For shots the *shot's* real start is preserved and
        the previous edge is extended to meet it, so that shot
        geometry stays accurate.  For all other edges the new edge's
        start is snapped to the previous edge's end."""
        if edges:
            if kind == "shot":
                edges[-1]["end"] = start
            else:
                start = edges[-1]["end"]
        edges.append({"start": start, "end": end, "kind": kind, "goal": goal})

    # Edge 0: the FK itself.
    if is_fk_shot(fk_ev):
        end = _xy(fk_ev.get("shot", {}).get("end_location"))
        if end is not None:
            outcome = (fk_ev.get("shot", {}).get("outcome") or {}).get("name")
            _add(fk_loc, end, "shot", goal=(outcome == "Goal"))
        return edges

    # Free-kick pass.
    pass_data = fk_ev.get("pass", {}) or {}
    end = _xy(pass_data.get("end_location"))
    if end is not None:
        _add(fk_loc, end, "pass")
    # An incomplete FK pass already ended the possession.
    if pass_data.get("outcome"):
        return edges

    # Walk subsequent events in index order.
    for ev in sorted(events, key=lambda e: e.get("index", -1)):
        idx = ev.get("index", -1)
        if idx <= fk_index:
            continue
        team = ev.get("team", {}).get("name", "")
        ev_type = (ev.get("type") or {}).get("name")

        if team == opp:
            if ev_type == "Pass":
                start = _xy(ev.get("location"))
                pdata = ev.get("pass") or {}
                p_end = _xy(pdata.get("end_location"))
                if start and p_end:
                    _add(start, p_end, "pass")
                # Incomplete pass (out / intercepted / etc.) ends the run.
                if pdata.get("outcome"):
                    break

            elif ev_type == "Carry":
                start = _xy(ev.get("location"))
                c_end = _xy((ev.get("carry") or {}).get("end_location"))
                if start and c_end:
                    _add(start, c_end, "carry")

            elif ev_type == "Shot":
                start = _xy(ev.get("location"))
                shot_data = ev.get("shot") or {}
                s_end = _xy(shot_data.get("end_location"))
                outcome = (shot_data.get("outcome") or {}).get("name")
                if start:
                    _add(
                        start,
                        s_end if s_end else start,
                        "shot",
                        goal=(outcome == "Goal"),
                    )
                break

            elif ev_type in OPP_TERMINATING_TYPES:
                break

            # Other opponent-side events (Ball Receipt*, Duel, etc.) do
            # not move the ball and do not end the run.

        else:
            # Barcelona event during opponent possession.  Only end the
            # run if Barca actually touched the ball; off-ball actions
            # like Pressure/Duel/tactical shifts must not split a run.
            if ev_type in BARCA_TERMINATING_TYPES:
                break

    return edges


def _flip180(loc: list[float]) -> list[float]:
    """Rotate a StatsBomb pitch coordinate 180° around the centre,
    so the opponent attacks toward x=0 (Barca's goal on the left)."""
    return [120.0 - loc[0], 80.0 - loc[1]]


def collect_runs(pairs: list[tuple]) -> list[dict]:
    """One record per defensive FK with a non-empty run."""
    runs: list[dict] = []
    for fk, events in pairs:
        if not (is_fk_pass(fk) or is_fk_shot(fk)):
            continue
        fk_loc = _xy(fk.get("location"))
        if fk_loc is None:
            continue
        edges = build_fk_run(fk, events, fk_loc)
        if not edges:
            continue
        for edge in edges:
            edge["start"] = _flip180(edge["start"])
            edge["end"]   = _flip180(edge["end"])
        ended_in_shot = edges[-1]["kind"] == "shot"
        runs.append({
            "edges": edges,
            "fk_origin": _flip180(fk_loc),
            "shot_ending": ended_in_shot,
        })
    return runs


# ── Plotting ─────────────────────────────────────────────────────────────────

def _draw_directed_edge(
    pitch: Pitch, ax, start: list[float], end: list[float],
    color: str, lw: float, alpha: float, zorder: float = 2,
) -> None:
    """Draw a connected line from *start* to *end* and overlay an
    arrowhead annotation.  The line itself is drawn end-to-end (no
    shrink) so consecutive edges in a path always butt up cleanly; the
    arrowhead sits on top with a small shrink for legibility."""
    pitch.lines(
        start[0], start[1], end[0], end[1],
        ax=ax, color=color, lw=lw, alpha=alpha, zorder=zorder,
    )
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if (dx * dx + dy * dy) < 0.25:
        return
    ax.annotate(
        "",
        xy=(end[0], end[1]),
        xytext=(start[0], start[1]),
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "lw": lw,
            "alpha": min(alpha + 0.1, 1.0),
            "shrinkA": 0,
            "shrinkB": 0,
            "mutation_scale": 10,
        },
        zorder=zorder + 0.2,
    )


def _draw_runs(ax, pitch: Pitch, runs: list[dict]) -> None:
    base_lw = 1.4
    base_alpha = 0.8

    for run in runs:
        for edge in run["edges"]:
            color = EDGE_COLORS[edge["kind"]]
            lw = base_lw + (0.4 if edge["kind"] == "shot" else 0.0)
            _draw_directed_edge(
                pitch, ax, edge["start"], edge["end"],
                color, lw, base_alpha,
            )

        # Mark FK origin so the start of every run is visible.
        ox, oy = run["fk_origin"]
        pitch.scatter(
            ox, oy, ax=ax, s=28, color="white",
            edgecolors="black", linewidths=0.8, zorder=4,
        )

        # Goal / non-goal marker at the end of any shot.
        for edge in run["edges"]:
            if edge["kind"] != "shot":
                continue
            ex, ey = edge["end"]
            marker = "x" if edge.get("goal") else "o"
            pitch.scatter(
                ex, ey, ax=ax, marker=marker, s=30,
                color="black", linewidths=1.2, zorder=5,
            )


def _legend_handles() -> list[Line2D]:
    return [
        Line2D([0], [0], color=COLOR_PASS, lw=2.2, label="Pass"),
        Line2D([0], [0], color=COLOR_CARRY, lw=2.2, label="Carry"),
        Line2D([0], [0], color=COLOR_SHOT, lw=2.2, label="Shot"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor="black", markersize=7, lw=0,
               label="FK origin"),
        Line2D([0], [0], marker="o", color="black", lw=0,
               markersize=5, label="Shot end (no goal)"),
        Line2D([0], [0], marker="x", color="black", lw=0,
               markersize=7, markeredgewidth=1.4, label="Shot end (goal)"),
    ]


def plot_runs(runs: list[dict], save: bool = True) -> None:
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#c7d5cc",
    )
    fig, ax = pitch.draw(figsize=(14, 9))

    _draw_runs(ax, pitch, runs)

    n_total = len(runs)
    n_shot = sum(1 for r in runs if r["shot_ending"])
    ax.set_title(
        f"Barcelona Defensive FK Runs – Origin to Possession Loss"
        f"   (N={n_total} · {n_shot} ended in shot)\n"
        "All opponent FKs (any pitch zone) – opponent attacks toward x=0 (Barca's goal)",
        fontsize=12, pad=12,
    )
    ax.legend(
        handles=_legend_handles(), loc="upper left",
        bbox_to_anchor=(1.01, 1.0), framealpha=0.85,
        fontsize=9, title="Edge type", title_fontsize=10,
    )
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = DEF_FK_ASSETS_DIR / "def_fk_runs.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out}")
    plt.show()


def plot_shot_runs(runs: list[dict], save: bool = True) -> None:
    """Restricted view: only runs that culminated in a shot."""
    shot_runs = [r for r in runs if r["shot_ending"]]
    if not shot_runs:
        print("No FK runs ended in a shot – skipping shot-only plot.")
        return

    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color="white",
        line_color="#c7d5cc",
    )
    fig, ax = pitch.draw(figsize=(14, 9))
    _draw_runs(ax, pitch, shot_runs)

    ax.set_title(
        f"Barcelona Defensive FK Runs that Ended in a Shot (N={len(shot_runs)})",
        fontsize=12, pad=12,
    )
    ax.legend(
        handles=_legend_handles(), loc="upper left",
        bbox_to_anchor=(1.01, 1.0), framealpha=0.85,
        fontsize=9, title="Edge type", title_fontsize=10,
    )
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = DEF_FK_ASSETS_DIR / "def_fk_runs_shots.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out}")
    plt.show()


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> None:
    pairs = collect_all_defending_fk_pairs()
    runs = collect_runs(pairs)
    n_shot = sum(1 for r in runs if r["shot_ending"])
    print(
        f"Defensive FKs: {len(pairs)}  ·  runs built: {len(runs)}  ·  "
        f"shot endings: {n_shot}"
    )
    plot_runs(runs)
    plot_shot_runs(runs)


if __name__ == "__main__":
    run()
