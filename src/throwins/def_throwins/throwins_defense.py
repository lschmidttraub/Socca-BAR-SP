"""
throwins_defense.py

Analyse Barcelona's defence against opponent throw-ins.

Three outputs:
  1. Scatter       — opponent throw-ins in Barcelona games, three subplots by zone.
                     Green = Barça won the ball back; red = opponent kept it.
  2. Zone stats    — Barcelona's win-back rate per zone (bar chart).
  3. Team comparison — all teams ranked by defensive win-back rate; Barcelona highlighted.

Coordinate convention
---------------------
Opponent events are flipped so Barcelona's goal is always on the left (x = 0).
    x_barca = 120 − x_opponent

Usage:
    python src/throwins/throwins_defense.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib.pyplot as plt
import pandas as pd
from mplsoccer import Pitch

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    DEFENSIVE_THIRD_MAX,
    ATTACKING_THIRD_MIN,
    _read_matches_df,
    opponent_throw_ins,
    read_statsbomb,
    throw_in_possession_won,
    throw_in_sequence,
)

_PITCH_LENGTH    = 120
_CORRIDOR_Y_MIN  = 80 / 3    # ≈ 26.7
_CORRIDOR_Y_MAX  = 160 / 3   # ≈ 53.3

POSSESSION_COLORS = {
    True:  "#2dc653",   # green — Barça won ball back
    False: "#e63946",   # red   — opponent kept possession
    None:  "#adb5bd",   # grey  — indeterminate
}

ZONE_ORDER = ["Defensive", "Middle", "Attacking"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flip_x(x: float) -> float:
    return _PITCH_LENGTH - x


def _in_middle_corridor(y: float) -> bool:
    return _CORRIDOR_Y_MIN <= y <= _CORRIDOR_Y_MAX


def _def_zone(x_barca: float) -> str:
    if x_barca <= DEFENSIVE_THIRD_MAX:
        return "Defensive"
    if x_barca >= ATTACKING_THIRD_MIN:
        return "Attacking"
    return "Middle"


# ── Data collection (single pass) ─────────────────────────────────────────────

def collect_data() -> tuple[pd.DataFrame, dict[str, dict]]:
    """One pass over all games.

    Returns
    -------
    barca_df   : one row per opponent throw-in in Barcelona games,
                 with coordinates flipped to Barcelona's defensive perspective.
    team_stats : {team_name: {"total": int, "won": int}} for all teams.
    """
    df_matches = _read_matches_df()
    barca_rows: list[dict] = []
    team_stats: dict[str, dict] = {}

    for _, row in df_matches.iterrows():
        if pd.isna(row["statsbomb"]):
            continue
        game_id = int(row["statsbomb"])
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            print(f"Missing events for game {game_id}, skipping.")
            continue

        sorted_events = sorted(events, key=lambda e: e.get("index", -1))
        team_names = {
            ev.get("team", {}).get("name", "")
            for ev in sorted_events
            if ev.get("team", {}).get("name")
        }

        for defending_team in team_names:
            if defending_team not in team_stats:
                team_stats[defending_team] = {
                    "total": 0, "won": 0,
                    "corridor_total": 0, "corridor_won": 0,
                }

            is_barca = BARCELONA.casefold() in defending_team.casefold()

            for ev in opponent_throw_ins(sorted_events, defending_team):
                won_by_opp = throw_in_possession_won(ev, sorted_events)
                def_won    = None if won_by_opp is None else (not won_by_opp)
                end_loc    = ev.get("pass", {}).get("end_location") or [None, None]
                in_corr    = _in_middle_corridor(end_loc[1]) if end_loc[1] is not None else False

                team_stats[defending_team]["total"] += 1
                if def_won is True:
                    team_stats[defending_team]["won"] += 1
                if in_corr:
                    team_stats[defending_team]["corridor_total"] += 1
                    if def_won is True:
                        team_stats[defending_team]["corridor_won"] += 1

                if is_barca:
                    loc = ev.get("location") or [None, None]
                    if loc[0] is None:
                        continue
                    x_b = _flip_x(loc[0])
                    barca_rows.append({
                        "x":         x_b,
                        "y":         loc[1],
                        "end_x":     _flip_x(end_loc[0]) if end_loc[0] is not None else None,
                        "end_y":     end_loc[1],
                        "zone":      _def_zone(x_b),
                        "barca_won": def_won,
                    })

    return pd.DataFrame(barca_rows), team_stats


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_defense_scatter(df: pd.DataFrame, save: bool = True) -> None:
    """Three-panel scatter of opponent throw-ins vs Barcelona, coloured by win-back."""
    df = df.dropna(subset=["x", "y", "end_x", "end_y"])

    pitch = Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#444444")
    fig, axes = pitch.draw(nrows=1, ncols=3, figsize=(20, 7))

    for ax, zone in zip(axes, ZONE_ORDER):
        zone_df = df[df["zone"] == zone]

        for _, r in zone_df.iterrows():
            color = POSSESSION_COLORS.get(r["barca_won"], "#adb5bd")
            ax.annotate(
                "",
                xy=(r["end_x"], r["end_y"]),
                xytext=(r["x"], r["y"]),
                arrowprops=dict(
                    arrowstyle="-|>", color=color,
                    lw=0.8, alpha=0.6, mutation_scale=8,
                ),
                zorder=2,
            )

        for won, label in [(True, "Barça won ball"), (False, "Opp kept ball"), (None, "Unclear")]:
            sub = zone_df[zone_df["barca_won"].isna()] if won is None \
                  else zone_df[zone_df["barca_won"] == won]
            if sub.empty:
                continue
            pitch.scatter(
                sub["end_x"], sub["end_y"], ax=ax,
                color=POSSESSION_COLORS[won], edgecolors="white",
                linewidths=0.5, s=40, label=label, zorder=3,
            )

        n_won = int((zone_df["barca_won"] == True).sum())
        n_lost = int((zone_df["barca_won"] == False).sum())
        n_tot  = len(zone_df)
        pct    = f"{n_won / n_tot * 100:.0f}%" if n_tot else "—"
        ax.set_title(
            f"{zone} zone  (N={n_tot})\n"
            f"Won back {n_won}  ·  Lost {n_lost}  ·  {pct} win-back",
            fontsize=10, pad=8, color="black",
        )
        ax.legend(loc="upper left", bbox_to_anchor=(0, 1), fontsize=8, framealpha=0.7)

    fig.suptitle(
        "Barcelona Defending Throw-ins — Ball Win-back by Zone\n"
        "Green = Barça won ball back  ·  Red = opponent kept possession  "
        "·  Barcelona's goal on the left",
        fontsize=12, y=1.02, color="black",
    )
    fig.set_facecolor("white")
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_scatter.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_zone_stats(df: pd.DataFrame, save: bool = True) -> None:
    """Bar chart of Barcelona's win-back rate per zone when defending throw-ins."""
    rows = []
    for zone in ZONE_ORDER:
        zone_df = df[df["zone"] == zone]
        n_tot  = len(zone_df)
        n_won  = int((zone_df["barca_won"] == True).sum())
        if n_tot:
            rows.append({"zone": zone, "winback_pct": n_won / n_tot * 100, "n": n_tot})

    zone_df_plot = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.set_facecolor("white")
    bars = ax.bar(zone_df_plot["zone"], zone_df_plot["winback_pct"],
                  color=["#4895ef", "#f9c74f", "#e63946"], edgecolor="white")

    for bar, val, n in zip(bars, zone_df_plot["winback_pct"], zone_df_plot["n"]):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.5,
                f"{val:.1f}%\n(n={n})", ha="center", va="bottom", fontsize=9)

    overall_won = int((df["barca_won"] == True).sum())
    overall_tot = len(df)
    overall_pct = overall_won / overall_tot * 100 if overall_tot else 0
    ax.axhline(overall_pct, color="black", linestyle="--", linewidth=1.2,
               label=f"Overall: {overall_pct:.1f}%")

    ax.set_ylabel("Win-back rate (%)")
    ax.set_title("Barcelona — Throw-in win-back rate by defensive zone")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_zone_stats.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_team_comparison(team_stats: dict[str, dict], save: bool = True) -> None:
    """All teams ranked by defensive throw-in win-back rate; Barcelona highlighted."""
    rows = [
        {"team": name, "winback_pct": d["won"] / d["total"] * 100, "total": d["total"]}
        for name, d in team_stats.items()
        if d["total"] >= 10
    ]
    df  = pd.DataFrame(rows).sort_values("winback_pct")
    avg = df["winback_pct"].mean()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.5)))
    fig.set_facecolor("white")
    bars = ax.barh(df["team"], df["winback_pct"], color="steelblue", edgecolor="white")

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    for bar, val, n in zip(bars, df["winback_pct"], df["total"]):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%  (n={n})", va="center", fontsize=7.5)

    ax.axvline(avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {avg:.1f}%")
    ax.set_xlabel("% of opponent throw-ins where possession was won back")
    ax.set_title("Defensive throw-in win-back rate — all teams  (red = Barcelona)")
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_comparison.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_corridor_winback(df: pd.DataFrame, save: bool = True) -> None:
    """Bar chart: Barcelona's win-back rate for throws into the middle corridor vs wide."""
    df = df.dropna(subset=["end_y"]).copy()
    df["in_corridor"] = df["end_y"].apply(_in_middle_corridor)

    cat_rows = []
    for label, mask in [("Middle corridor", df["in_corridor"]), ("Wide", ~df["in_corridor"])]:
        sub   = df[mask]
        n     = len(sub)
        n_won = int((sub["barca_won"] == True).sum())
        if n:
            cat_rows.append({"cat": label, "winback_pct": n_won / n * 100, "n": n})
    cp = pd.DataFrame(cat_rows)

    fig, ax = plt.subplots(figsize=(6, 5))
    fig.set_facecolor("white")
    bars = ax.bar(cp["cat"], cp["winback_pct"], color=["#f4a261", "#4895ef"], edgecolor="white")
    for bar, val, n in zip(bars, cp["winback_pct"], cp["n"]):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.5,
                f"{val:.1f}%\n(n={n})", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("Win-back rate (%)")
    ax.set_title(
        "Barcelona — win-back rate when opponent throws into\n"
        f"middle corridor vs wide  (corridor: y ≈ {_CORRIDOR_Y_MIN:.0f}–{_CORRIDOR_Y_MAX:.0f})"
    )
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_corridor_winback.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_corridor_team_comparison(team_stats: dict[str, dict], save: bool = True) -> None:
    """All teams ranked by win-back rate for throws into the middle corridor; Barcelona highlighted."""
    rows = [
        {
            "team":        name,
            "winback_pct": d["corridor_won"] / d["corridor_total"] * 100,
            "n":           d["corridor_total"],
        }
        for name, d in team_stats.items()
        if d["corridor_total"] >= 5
    ]
    df  = pd.DataFrame(rows).sort_values("winback_pct")
    avg = df["winback_pct"].mean()

    fig, ax = plt.subplots(figsize=(12, max(7, len(df) * 0.6)))
    fig.set_facecolor("white")
    bars = ax.barh(df["team"], df["winback_pct"], color="steelblue",
                   edgecolor="white", height=0.65)

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    max_val = df["winback_pct"].max()
    ax.set_xlim(0, max_val + 18)

    for bar, val, n in zip(bars, df["winback_pct"], df["n"]):
        ax.text(val + 0.8, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%  (n={n})", va="center", fontsize=9)

    ax.axvline(avg, color="black", linestyle="--", linewidth=1.4,
               label=f"League avg: {avg:.1f}%")
    ax.set_xlabel("Win-back rate on middle-corridor throw-ins (%)", fontsize=11)
    ax.tick_params(axis="y", labelsize=10)
    ax.tick_params(axis="x", labelsize=10)
    ax.set_title(
        "When an opponent plays a throw-in into the central corridor, how often does each team win the ball back?\n"
        "Teams ranked by that rate  ·  red = Barcelona  ·  "
        f"middle corridor: central ⅓ of pitch width (y ≈ {_CORRIDOR_Y_MIN:.0f}–{_CORRIDOR_Y_MAX:.0f})",
        fontsize=11, pad=10,
    )
    ax.legend(fontsize=10)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout(pad=1.5)

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_corridor_comparison.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


# ── Lost-sequence data collection & scatter ───────────────────────────────────

def _to_barca_x(x: float, team: str) -> float:
    """Flip x for opponent events so Barcelona's goal stays on the left."""
    return (_PITCH_LENGTH - x) if BARCELONA.casefold() not in team.casefold() else x


def _event_seconds(ev: dict) -> float:
    """Return event time in seconds within its period, using timestamp for precision."""
    ts = ev.get("timestamp", "")
    if ts:
        try:
            h, m, s = ts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except (ValueError, AttributeError):
            pass
    return ev.get("minute", 0) * 60 + ev.get("second", 0)


_TYPE_PASS  = 30
_TYPE_CARRY = 43


def _end_location(ev: dict) -> list | None:
    """Return the ball's destination for pass and carry events, None otherwise.

    Shots are excluded — their end_location can be off-pitch (over the bar, wide).
    """
    type_id = ev.get("type", {}).get("id")
    if type_id == _TYPE_PASS:
        return ev.get("pass", {}).get("end_location")
    if type_id == _TYPE_CARRY:
        return ev.get("carry", {}).get("end_location")
    return None


def _on_pitch(x: float, y: float) -> bool:
    return 0 <= x <= _PITCH_LENGTH and 0 <= y <= 80


def collect_lost_sequences(max_seconds: float = 6.0) -> list[list[tuple[float, float]]]:
    """Return one path per opponent throw-in where Barça did NOT win the ball.

    Each path is an ordered list of (x, y) waypoints in Barcelona's coordinate system
    built by interleaving the location and end_location of every ball-moving event
    (pass, carry) in the sequence. This gives a single continuous line per chain
    with no gaps between actions.
    """
    df_matches = _read_matches_df()
    chains: list[list[tuple[float, float]]] = []

    for _, row in df_matches.iterrows():
        if pd.isna(row["statsbomb"]):
            continue
        game_id = int(row["statsbomb"])
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            continue

        sorted_events = sorted(events, key=lambda e: e.get("index", -1))

        barca_in_game = any(
            BARCELONA.casefold() in ev.get("team", {}).get("name", "").casefold()
            for ev in sorted_events
        )
        if not barca_in_game:
            continue

        for ev in opponent_throw_ins(sorted_events, BARCELONA):
            won_by_opp = throw_in_possession_won(ev, sorted_events)
            if won_by_opp is not True:
                continue

            loc     = ev.get("location")
            end_loc = _end_location(ev)
            if not loc or not end_loc:
                continue

            opp_team     = ev.get("team", {}).get("name", "")
            throw_time   = _event_seconds(ev)
            throw_period = ev.get("period", 0)

            x0 = _to_barca_x(loc[0],     opp_team)
            x1 = _to_barca_x(end_loc[0], opp_team)
            if not (_on_pitch(x0, loc[1]) and _on_pitch(x1, end_loc[1])):
                continue

            path: list[tuple[float, float]] = [(x0, loc[1]), (x1, end_loc[1])]

            for seq_ev in throw_in_sequence(ev, sorted_events):
                if seq_ev.get("period", 0) != throw_period:
                    break
                if _event_seconds(seq_ev) - throw_time > max_seconds:
                    break
                seq_loc  = seq_ev.get("location")
                seq_end  = _end_location(seq_ev)
                seq_team = seq_ev.get("team", {}).get("name", "")
                if not (seq_loc and seq_end):
                    continue
                xs = _to_barca_x(seq_loc[0], seq_team)
                xe = _to_barca_x(seq_end[0], seq_team)
                if _on_pitch(xs, seq_loc[1]) and _on_pitch(xe, seq_end[1]):
                    path.append((xs, seq_loc[1]))
                    path.append((xe, seq_end[1]))

            if len(path) >= 2:
                chains.append(path)

    return chains


_PITCH_WIDTH_HALF = 40.0    # y = 40 is the centre line width-wise


def _changed_side(path: list[tuple[float, float]]) -> bool:
    """True if any waypoint after the throw-in crosses to the opposite y-half.

    A throw-in originates on a touchline (y ≈ 0 or y ≈ 80).  The sequence
    'changed the side' when the ball at any point crosses the y = 40 midline
    relative to the throw-in origin.
    """
    origin_bottom = path[0][1] < _PITCH_WIDTH_HALF
    return any((p[1] < _PITCH_WIDTH_HALF) != origin_bottom for p in path[1:])


def plot_lost_sequences(chains: list[list[tuple[float, float]]], max_seconds: float = 6.0, save: bool = True) -> None:
    """Full-pitch path plot of opponent throw-in sequences where Barcelona did not win the ball.

    Each chain is a single continuous polyline (pass + carry waypoints).
    Blue  = sequence switched side (crossed y = 40 midline).
    Red   = sequence stayed on the same side.
    An arrowhead marks the final point. Barcelona's goal is on the left (x = 0).
    """
    from matplotlib.lines import Line2D

    COLOR_SWITCH  = "#4895ef"   # blue  — changed side
    COLOR_STAY    = "#e63946"   # red   — same side

    n_switch = sum(1 for path in chains if _changed_side(path))
    n_stay   = len(chains) - n_switch

    pitch = Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#444444")
    fig, ax = pitch.draw(figsize=(14, 9))

    for path in chains:
        color = COLOR_SWITCH if _changed_side(path) else COLOR_STAY
        xs = [p[0] for p in path]
        ys = [p[1] for p in path]

        ax.plot(xs, ys, color=color, lw=0.9, alpha=0.35, zorder=2)

        # Arrowhead at the final segment
        if len(path) >= 2:
            ax.annotate(
                "",
                xy=path[-1],
                xytext=path[-2],
                arrowprops=dict(
                    arrowstyle="-|>", color=color,
                    lw=0.9, alpha=0.5, mutation_scale=7,
                ),
                zorder=3,
            )

        # Mark throw-in origin
        pitch.scatter(
            path[0][0], path[0][1], ax=ax,
            color="#f4a261", edgecolors="white", linewidths=0.4,
            s=35, zorder=4, alpha=0.8,
        )

    legend_handles = [
        Line2D([0], [0], color=COLOR_SWITCH, lw=2, label=f"Switched side  (n={n_switch})"),
        Line2D([0], [0], color=COLOR_STAY,   lw=2, label=f"Same side  (n={n_stay})"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#f4a261",
               markersize=8, label="Throw-in origin"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=9, framealpha=0.85)

    ax.set_title(
        f"Opponent throw-in sequences — Barcelona did not win the ball back  "
        f"(N={len(chains)}: {n_switch} switched side · {n_stay} same side)\n"
        f"First {max_seconds:.0f} s  ·  Blue = switched side  ·  Red = same side  "
        "·  Orange dot = throw-in origin  ·  Barcelona's goal on the left",
        fontsize=11, pad=12, color="black",
    )
    fig.set_facecolor("white")
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_lost_sequences.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


