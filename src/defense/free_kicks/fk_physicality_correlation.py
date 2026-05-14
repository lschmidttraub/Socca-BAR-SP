"""
fk_physicality_correlation.py

Does Barcelona man-mark more on defensive free kicks against physically
bigger opponents?

Per opponent, pairs:
  * Barca's mean man-marking fraction on defensive FKs (fk_zonal_analysis)
  * the opponent's aerial-size proxy — mean height of their TOP_N tallest
    outfield players who actually played, pooled from every StatsBomb
    lineup in the dataset.

A ``player_id → height`` table is built from all lineup files in
``league_phase``, ``playoffs`` and ``quarterfinals`` zips. ``last16.zip``
ships no lineups, but every Champions League team plays the league phase,
so all of Barca's knockout opponents are still covered.

Caveats surfaced in the output:
  * n ≈ 9 opponents → Spearman ρ only, treat as suggestive not conclusive.
  * Stage is a confounder — knockout opponents are both bigger *and*
    more man-marked. Points are coloured by stage so this is visible.

Outputs
-------
assets/defense/free_kicks/7_manmarking_vs_physicality.png

Usage
-----
    uv run python src/defense/free_kicks/fk_physicality_correlation.py
"""

import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ── Reuse sibling modules ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corners"))
from defending_corners import read_statsbomb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fk_zonal_analysis import (  # noqa: E402
    TEAM, OUT_DIR, C_ZONAL, C_MAN, C_GREY, _caption, _set_style,
    collect_marking_rows,
)

PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent.parent
STATSBOMB_DIR = PROJECT_ROOT / "data" / "statsbomb"
LINEUP_ZIPS   = ("league_phase.zip", "playoffs.zip", "quarterfinals.zip")
TOP_N         = 6              # tallest-N outfield players → aerial-size proxy
KNOCKOUT_FROM = "2026-02-01"   # CL knockout rounds start February 2026


# ─────────────────────────────────────────────────────────────────────────────
# StatsBomb lineup → height table
# ─────────────────────────────────────────────────────────────────────────────
def _is_goalkeeper(player: dict) -> bool:
    return any("Goalkeeper" in p.get("position", "") for p in player.get("positions", []))


def _played(player: dict) -> bool:
    """A player appeared on the pitch ↔ their positions list is non-empty."""
    return len(player.get("positions", [])) > 0


def build_height_table() -> dict[str, dict[int, float]]:
    """Return ``{statsbomb_team_name: {player_id: height_cm}}`` for every
    outfield player who actually played, pooled across all lineup files."""
    table: dict[str, dict[int, float]] = defaultdict(dict)
    for zip_name in LINEUP_ZIPS:
        zip_path = STATSBOMB_DIR / zip_name
        if not zip_path.is_file():
            continue
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if not member.endswith("_lineups.json"):
                    continue
                with zf.open(member) as fh:
                    lineup = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                for team in lineup:
                    name = team.get("team_name")
                    for p in team.get("lineup", []):
                        h = p.get("player_height")
                        if h is None or not _played(p) or _is_goalkeeper(p):
                            continue
                        table[name][int(p["player_id"])] = float(h)
    return table


def opponent_top_n_height(team_heights: dict[str, dict[int, float]],
                          sb_name: str) -> float | None:
    """Mean height of the opponent's TOP_N tallest outfield players."""
    heights = sorted(team_heights.get(sb_name, {}).values(), reverse=True)[:TOP_N]
    return float(np.mean(heights)) if len(heights) >= TOP_N else None


def sb_opponent_name(sb_id: int) -> str | None:
    """The opponent's StatsBomb team name = the non-Barca team in the events.

    Works for every match including last16 (events exist there even though
    lineup files do not)."""
    try:
        events = read_statsbomb(sb_id)
    except FileNotFoundError:
        return None
    for ev in events:
        name = ev.get("team", {}).get("name")
        if name and TEAM.casefold() not in name.casefold():
            return name
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────
def build_opponent_table(per_fk: pd.DataFrame,
                          team_heights: dict[str, dict[int, float]]) -> pd.DataFrame:
    """One row per opponent: mean man-fraction, tallest-6 height, stage."""
    per_fk = per_fk.copy()
    sb_ids = [int(s) for s in per_fk["statsbomb"].dropna().unique()]
    name_of = {s: sb_opponent_name(s) for s in sb_ids}
    per_fk["sb_opponent"] = per_fk["statsbomb"].map(
        lambda s: name_of.get(int(s)) if pd.notna(s) else None
    )
    per_fk["is_ko"] = per_fk["date"] >= KNOCKOUT_FROM

    rows = []
    for sb_opp, g in per_fk.groupby("sb_opponent"):
        if not sb_opp:
            continue
        height = opponent_top_n_height(team_heights, sb_opp)
        if height is None:
            print(f"  no height data for {sb_opp!r} — skipped")
            continue
        rows.append({
            "opponent":      sb_opp,
            "n_fks":         len(g),
            "mean_man_frac": float(g["man_frac"].mean()),
            "height_top6":   height,
            # An opponent is "knockout" if Barca met them in a knockout round
            # at any point (Newcastle spans league + last-16).
            "knockout":      bool(g["is_ko"].any()),
        })
    return pd.DataFrame(rows).sort_values("height_top6").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Plot
# ─────────────────────────────────────────────────────────────────────────────
def plot_correlation(agg: pd.DataFrame, out: Path) -> None:
    x = agg["height_top6"].to_numpy()
    y = agg["mean_man_frac"].to_numpy() * 100.0
    rho, p = spearmanr(x, y)

    fig, ax = plt.subplots(figsize=(8.5, 6))

    # Regression line (visual aid only).
    if len(x) >= 2:
        slope, intercept = np.polyfit(x, y, 1)
        xs = np.linspace(x.min() - 0.4, x.max() + 0.4, 50)
        ax.plot(xs, slope * xs + intercept, color=C_GREY, linewidth=1.0,
                linestyle="--", alpha=0.7, zorder=1)

    for ko, color, label in [(False, C_ZONAL, "League phase"),
                             (True,  C_MAN,   "Knockout")]:
        sub = agg[agg["knockout"] == ko]
        if sub.empty:
            continue
        ax.scatter(
            sub["height_top6"], sub["mean_man_frac"] * 100.0,
            s=40 + sub["n_fks"] * 26,
            color=color, edgecolors="white", linewidths=0.8,
            alpha=0.85, zorder=3, label=label,
        )

    for r in agg.itertuples():
        ax.annotate(
            r.opponent,
            (r.height_top6, r.mean_man_frac * 100.0),
            textcoords="offset points", xytext=(7, 4),
            fontsize=8, color="#333",
        )

    ax.set_xlabel(f"Opponent aerial size — mean height of {TOP_N} tallest outfielders (cm)")
    ax.set_ylabel("Mean man-marking fraction on defensive FKs (%)")
    ax.set_title(f"{TEAM}: man-marking vs opponent physicality")
    ax.grid(alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, title="Opponent met in")

    fig.text(
        0.5, 0.94,
        f"Spearman ρ = {rho:+.2f}  (p = {p:.2f}, n = {len(agg)})  •  marker size ∝ number of defensive FKs",
        ha="center", fontsize=9.5, color="#444",
    )
    _caption(fig, "Height pooled from all StatsBomb lineups • stage is a confounder: "
                  "knockout opponents are both bigger and more man-marked")
    plt.tight_layout(rect=(0, 0, 1, 0.93))
    plt.savefig(out, bbox_inches="tight", dpi=160)
    plt.close(fig)
    return rho, p


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    _set_style()

    print("Collecting SkillCorner FK marking rows…")
    per_fk, _, _ = collect_marking_rows()
    print(f"  {len(per_fk)} defensive FKs classified.")

    print("Building height table from StatsBomb lineups…")
    team_heights = build_height_table()
    print(f"  {len(team_heights)} teams, "
          f"{sum(len(v) for v in team_heights.values())} player-height records.")

    agg = build_opponent_table(per_fk, team_heights)
    if agg.empty or len(agg) < 3:
        print("Not enough opponents with height data to correlate.")
        return

    out = OUT_DIR / "7_manmarking_vs_physicality.png"
    rho, p = plot_correlation(agg, out)

    print("\nPer-opponent table (sorted by height):")
    print(f"  {'opponent':22s} {'n_fk':>4s} {'man%':>6s} {'top6_h':>8s}  stage")
    for _, r in agg.iterrows():
        stage = "knockout" if r["knockout"] else "league"
        print(f"  {r['opponent']:22s} {int(r['n_fks']):4d} "
              f"{r['mean_man_frac']*100:5.0f}% {r['height_top6']:7.1f}   {stage}")

    print(f"\nSpearman ρ = {rho:+.3f}  (p = {p:.3f}, n = {len(agg)})")
    # Same correlation within the league phase only — strips the stage confounder.
    league = agg[~agg["knockout"]]
    if len(league) >= 4:
        lr, lp = spearmanr(league["height_top6"], league["mean_man_frac"])
        print(f"League-phase opponents only: ρ = {lr:+.3f}  (p = {lp:.3f}, n = {len(league)})")

    print(f"\nPlot written to: {out}")


if __name__ == "__main__":
    main()
