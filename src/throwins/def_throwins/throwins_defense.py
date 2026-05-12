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

        # KDE heatmap of throw-in landing points (background layer)
        if len(zone_df) >= 5:
            pitch.kdeplot(
                zone_df["end_x"], zone_df["end_y"], ax=ax,
                cmap="Blues", fill=True, alpha=0.45,
                levels=10, thresh=0.05, zorder=1,
            )

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


def plot_normalized_landing_heatmap(df: pd.DataFrame, save: bool = True) -> None:
    """Normalized throw-in landing heatmap with win-back arrows.

    Coordinates relative to throw-in origin:
      dx > 0  = toward opponent's goal (away from Barcelona's goal)
      dy > 0  = into the pitch (always, regardless of which touchline)
    """
    try:
        from scipy.ndimage import gaussian_filter
        _has_scipy = True
    except ImportError:
        _has_scipy = False

    import numpy as np

    df = df.dropna(subset=["x", "y", "end_x", "end_y"]).copy()
    df["dx"] = df["end_x"] - df["x"]
    df["dy"] = np.where(df["y"] < 40, df["end_y"] - df["y"], df["y"] - df["end_y"])

    _DX     = (-50, 70)
    _DY     = (-5,  40)
    _N_BINS = 40

    def _make_heatmap(sub: pd.DataFrame) -> np.ndarray:
        if len(sub) < 3:
            return np.zeros((_N_BINS, _N_BINS))
        xs = np.clip(sub["dx"].values, *_DX)
        ys = np.clip(sub["dy"].values, *_DY)
        h, _, _ = np.histogram2d(xs, ys, bins=_N_BINS, range=[_DX, _DY])
        if _has_scipy:
            h = gaussian_filter(h, sigma=1.5)
        h = h / h.max() if h.max() > 0 else h
        return h.T

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.set_facecolor("white")

    for ax, zone in zip(axes, ZONE_ORDER):
        zone_df = df[df["zone"] == zone]

        ax.imshow(
            _make_heatmap(zone_df),
            origin="lower", extent=[*_DX, *_DY],
            aspect="auto", cmap="Blues",
            vmin=0, vmax=1, alpha=0.85,
        )

        for _, r in zone_df.iterrows():
            color = POSSESSION_COLORS.get(r["barca_won"], "#adb5bd")
            ax.annotate(
                "",
                xy=(r["dx"], r["dy"]),
                xytext=(0, 0),
                arrowprops=dict(
                    arrowstyle="-|>", color=color,
                    lw=0.8, alpha=0.55, mutation_scale=8,
                ),
                zorder=3,
            )

        for won, label in [(True, "Barça won ball"), (False, "Opp kept ball")]:
            sub = zone_df[zone_df["barca_won"] == won]
            if sub.empty:
                continue
            ax.scatter(
                sub["dx"], sub["dy"],
                color=POSSESSION_COLORS[won], edgecolors="white",
                linewidths=0.4, s=35, label=label, zorder=4, alpha=0.8,
            )

        ax.plot(0, 0, "o", color="cyan", markersize=9, zorder=6)
        ax.axhline(0, color="white", lw=1.5, alpha=0.7)
        ax.axvline(0, color="white", lw=1.0, alpha=0.4, linestyle="--")

        n_tot = len(zone_df)
        n_won = int((zone_df["barca_won"] == True).sum())
        pct   = f"{n_won / n_tot * 100:.0f}%" if n_tot else "—"
        ax.set_title(
            f"{zone} zone  (N={n_tot})  ·  {pct} win-back",
            fontsize=10, pad=8, color="black",
        )
        ax.set_facecolor("#1a1a2e")
        ax.set_xlim(*_DX)
        ax.set_ylim(*_DY)
        ax.set_xlabel(
            "← toward Barça goal  |  toward Opp goal →\n(StatsBomb units, relative to throw-in)",
            fontsize=8,
        )
        ax.legend(loc="upper right", fontsize=8, framealpha=0.7)

    axes[0].set_ylabel("Into pitch →  (StatsBomb units)", fontsize=8)

    fig.suptitle(
        "Opponent throw-in landing points — normalised to throw-in origin\n"
        "Heatmap = landing density  ·  Green = Barça won ball back  "
        "·  Red = opponent kept possession  ·  Cyan dot = throw-in origin",
        fontsize=12, y=1.02, color="black",
    )
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_scatter_normalized.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_combined_defense_heatmap(
    df: pd.DataFrame,
    positions: dict,
    save: bool = True,
) -> None:
    """Barcelona defensive shape overlaid with opponent throw-in landing points.

    Green heatmap  = Barcelona player density at throw-in moment (SkillCorner, metres).
    Blue heatmap   = opponent throw-in landing point density (StatsBomb → metres).
    Arrows         = individual throw-ins coloured by win-back outcome.
    All coordinates normalised to throw-in origin = (0, 0).

    StatsBomb → metres: x × (105/120), y × (68/80).
    """
    try:
        from scipy.ndimage import gaussian_filter
        _has_scipy = True
    except ImportError:
        _has_scipy = False

    import numpy as np

    _SB_X_TO_M = 105 / 120
    _SB_Y_TO_M = 68  / 80
    _DX    = (-50, 50)
    _DY    = (-2,  70)
    _BINS  = 40

    def _heatmap(xs, ys):
        if len(xs) < 3:
            return np.zeros((_BINS, _BINS))
        h, _, _ = np.histogram2d(
            np.clip(xs, *_DX), np.clip(ys, *_DY),
            bins=_BINS, range=[_DX, _DY],
        )
        if _has_scipy:
            h = gaussian_filter(h, sigma=1.5)
        h = h / h.max() if h.max() > 0 else h
        return h.T

    df = df.dropna(subset=["x", "y", "end_x", "end_y"]).copy()
    df["dx_m"] = (df["end_x"] - df["x"]) * _SB_X_TO_M
    df["dy_m"] = np.where(
        df["y"] < 40,
        (df["end_y"] - df["y"]) * _SB_Y_TO_M,
        (df["y"] - df["end_y"]) * _SB_Y_TO_M,
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.set_facecolor("white")

    for ax, zone in zip(axes, ZONE_ORDER):
        zone_df   = df[df["zone"] == zone]
        barca_pts = positions.get(zone, {}).get("barca", [])

        # Barcelona player positioning (SkillCorner, already in metres)
        if barca_pts:
            bx = np.array([p[0] for p in barca_pts])
            by = np.array([p[1] for p in barca_pts])
            ax.imshow(
                _heatmap(bx, by),
                origin="lower", extent=[*_DX, *_DY],
                aspect="auto", cmap="Greens",
                vmin=0, vmax=1, alpha=0.70, zorder=1,
            )

        # Individual throw-in arrows
        for _, r in zone_df.iterrows():
            color = POSSESSION_COLORS.get(r["barca_won"], "#adb5bd")
            ax.annotate(
                "",
                xy=(r["dx_m"], r["dy_m"]),
                xytext=(0, 0),
                arrowprops=dict(
                    arrowstyle="-|>", color=color,
                    lw=0.8, alpha=0.50, mutation_scale=8,
                ),
                zorder=3,
            )

        for won, label in [(True, "Barça won ball"), (False, "Opp kept ball")]:
            sub = zone_df[zone_df["barca_won"] == won]
            if sub.empty:
                continue
            ax.scatter(
                sub["dx_m"], sub["dy_m"],
                color=POSSESSION_COLORS[won], edgecolors="white",
                linewidths=0.4, s=30, label=label, zorder=4, alpha=0.85,
            )

        ax.plot(0, 0, "o", color="cyan", markersize=9, zorder=6)
        ax.axhline(0, color="white", lw=1.5, alpha=0.7)
        ax.axvline(0, color="white", lw=1.0, alpha=0.4, linestyle="--")

        n_tot = len(zone_df)
        n_won = int((zone_df["barca_won"] == True).sum())
        n_sk  = positions.get(zone, {}).get("count", 0)
        pct   = f"{n_won / n_tot * 100:.0f}%" if n_tot else "—"
        ax.set_title(
            f"{zone} zone  ·  StatsBomb N={n_tot}  ·  SkillCorner n={n_sk}  ·  {pct} win-back",
            fontsize=9, pad=8, color="black",
        )
        ax.set_facecolor("#1a1a2e")
        ax.set_xlim(*_DX)
        ax.set_ylim(*_DY)
        ax.set_xlabel(
            "← toward Barça goal  |  toward Opp goal →\n(metres, relative to throw-in origin)",
            fontsize=8,
        )
        ax.legend(loc="upper right", fontsize=8, framealpha=0.7)

    axes[0].set_ylabel("Into pitch →  (metres)", fontsize=8)

    fig.suptitle(
        "Opponent throw-in landing points vs. Barcelona defensive shape — normalised to throw-in origin\n"
        "Green = Barcelona player positions (SkillCorner)  ·  "
        "Arrows = throw-in landing points (StatsBomb)  ·  Cyan dot = throw-in origin",
        fontsize=11, y=1.02, color="black",
    )
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_combined.png"
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


def plot_opponent_throw_direction(team_stats: dict[str, dict], save: bool = True) -> None:
    """Stacked horizontal bars: % of opponent throws that are central vs wide per defending team.

    'Central' = throw lands in the middle corridor (y ≈ 26.7–53.3).
    'Wide'    = throw stays near the touchline it started from.
    Sorted by central %, Barcelona highlighted in red.
    """
    rows = [
        {
            "team":        name,
            "central_pct": d["corridor_total"] / d["total"] * 100,
            "wide_pct":    (d["total"] - d["corridor_total"]) / d["total"] * 100,
            "n":           d["total"],
        }
        for name, d in team_stats.items()
        if d["total"] >= 10
    ]
    df = pd.DataFrame(rows).sort_values("central_pct")
    league_central = df["central_pct"].mean()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.5)))
    fig.set_facecolor("white")

    bars_wide = ax.barh(
        df["team"], df["wide_pct"],
        color="#4895ef", edgecolor="white", label="Wide",
    )
    bars_central = ax.barh(
        df["team"], df["central_pct"],
        left=df["wide_pct"],
        color="#f4a261", edgecolor="white", label="Central (corridor)",
    )

    # Label the central % on each bar; colour Barcelona's row red
    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar_w, bar_c, pct, n, is_barca in zip(
        bars_wide, bars_central, df["central_pct"], df["n"], barca_mask
    ):
        if is_barca:
            bar_w.set_color("#e63946")
            bar_c.set_color("#c9184a")
        ax.text(
            101, bar_c.get_y() + bar_c.get_height() / 2,
            f"{pct:.1f}%  (n={n})", va="center", fontsize=7.5,
        )

    ax.axvline(league_central + df["wide_pct"].mean(), color="black",
               linestyle="--", linewidth=1.2,
               label=f"League avg central: {league_central:.1f}%")

    ax.set_xlim(0, 130)
    ax.set_xlabel("Share of opponent throw-ins (%)")
    ax.set_title(
        "How do opponents play throw-ins against each team?  (red = Barcelona)\n"
        f"Central = ball played into middle corridor (y ≈ {_CORRIDOR_Y_MIN:.0f}–{_CORRIDOR_Y_MAX:.0f})"
        "  ·  Wide = near touchline  ·  sorted by central %",
        fontsize=11,
    )
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_throw_direction.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


def plot_corridor_winback(df: pd.DataFrame, team_stats: dict[str, dict] | None = None, save: bool = True) -> None:
    """Bar chart: Barcelona's win-back rate for throws into the middle corridor vs wide.

    If team_stats is provided, a dashed league-average line is drawn on each bar.
    """
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

    # League averages per category from team_stats
    league_avgs: dict[str, float] = {}
    if team_stats:
        corr_total = sum(d["corridor_total"] for d in team_stats.values())
        corr_won   = sum(d["corridor_won"]   for d in team_stats.values())
        wide_total = sum(d["total"] - d["corridor_total"] for d in team_stats.values())
        wide_won   = sum(d["won"]   - d["corridor_won"]   for d in team_stats.values())
        if corr_total:
            league_avgs["Middle corridor"] = corr_won / corr_total * 100
        if wide_total:
            league_avgs["Wide"] = wide_won / wide_total * 100

    fig, ax = plt.subplots(figsize=(6, 5))
    fig.set_facecolor("white")
    bars = ax.bar(cp["cat"], cp["winback_pct"], color=["#f4a261", "#4895ef"], edgecolor="white")
    for bar, val, n in zip(bars, cp["winback_pct"], cp["n"]):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.5,
                f"{val:.1f}%\n(n={n})", ha="center", va="bottom", fontsize=10)

    # Draw league-average line segment over each bar
    for bar, row in zip(bars, cp.itertuples()):
        avg = league_avgs.get(row.cat)
        if avg is None:
            continue
        x_mid = bar.get_x() + bar.get_width() / 2
        half  = bar.get_width() * 0.45
        ax.plot([x_mid - half, x_mid + half], [avg, avg],
                color="black", linestyle="--", linewidth=1.6, zorder=5)
        ax.text(x_mid + half + 0.03, avg, f"avg {avg:.1f}%",
                va="center", fontsize=8, color="black")

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


def collect_side_change_stats(max_seconds: float = 6.0) -> dict[str, dict]:
    """For every team, count lost throw-in sequences that changed side within max_seconds.

    Uses the same path-building logic as collect_lost_sequences / _changed_side so
    that Barcelona's numbers here match the blue/total ratio in plot_lost_sequences.

    Returns {team_name: {"total_lost": int, "side_changed": int}}.
    """
    df_matches = _read_matches_df()
    stats: dict[str, dict] = {}

    for _, row in df_matches.iterrows():
        if pd.isna(row["statsbomb"]):
            continue
        game_id = int(row["statsbomb"])
        try:
            events = read_statsbomb(game_id)
        except FileNotFoundError:
            continue

        sorted_events = sorted(events, key=lambda e: e.get("index", -1))
        team_names = {
            ev.get("team", {}).get("name", "")
            for ev in sorted_events
            if ev.get("team", {}).get("name")
        }

        for defending_team in team_names:
            if defending_team not in stats:
                stats[defending_team] = {"total_lost": 0, "side_changed": 0}

            for ev in opponent_throw_ins(sorted_events, defending_team):
                won_by_opp = throw_in_possession_won(ev, sorted_events)
                if won_by_opp is not True:
                    continue

                loc     = ev.get("location")
                end_loc = _end_location(ev)
                if not loc or not end_loc:
                    continue
                if not (_on_pitch(loc[0], loc[1]) and _on_pitch(end_loc[0], end_loc[1])):
                    continue

                throw_time   = _event_seconds(ev)
                throw_period = ev.get("period", 0)

                path: list[tuple[float, float]] = [(loc[0], loc[1]), (end_loc[0], end_loc[1])]

                for seq_ev in throw_in_sequence(ev, sorted_events):
                    if seq_ev.get("period", 0) != throw_period:
                        break
                    if _event_seconds(seq_ev) - throw_time > max_seconds:
                        break
                    seq_loc = seq_ev.get("location")
                    seq_end = _end_location(seq_ev)
                    if not (seq_loc and seq_end):
                        continue
                    if _on_pitch(seq_loc[0], seq_loc[1]) and _on_pitch(seq_end[0], seq_end[1]):
                        path.append((seq_loc[0], seq_loc[1]))
                        path.append((seq_end[0], seq_end[1]))

                stats[defending_team]["total_lost"] += 1
                if _changed_side(path):
                    stats[defending_team]["side_changed"] += 1

    return stats


def plot_side_change_rate(
    side_stats: dict[str, dict],
    max_seconds: float = 6.0,
    save: bool = True,
) -> None:
    """All teams ranked by % of lost throw-in sequences that changed side; Barcelona highlighted."""
    rows = [
        {
            "team": name,
            "pct":  d["side_changed"] / d["total_lost"] * 100,
            "n":    d["total_lost"],
        }
        for name, d in side_stats.items()
        if d["total_lost"] >= 10
    ]
    df  = pd.DataFrame(rows).sort_values("pct")
    avg = df["pct"].mean()

    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.5)))
    fig.set_facecolor("white")
    bars = ax.barh(df["team"], df["pct"], color="steelblue", edgecolor="white")

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    for bar, val, n in zip(bars, df["pct"], df["n"]):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%  (n={n})", va="center", fontsize=7.5)

    ax.axvline(avg, color="black", linestyle="--", linewidth=1.2,
               label=f"League avg: {avg:.1f}%")
    ax.set_xlabel("% of lost throw-in sequences that changed side")
    ax.set_title(
        f"When the opponent wins the ball from a throw-in, how often does play switch side within {max_seconds:.0f} s?\n"
        "(red = Barcelona  ·  sorted by side-change rate  ·  only sequences where defending team lost possession)",
        fontsize=11,
    )
    ax.legend(fontsize=9)
    ax.grid(axis="x", alpha=0.25)
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_side_change.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")
    plt.show()


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


