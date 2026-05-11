"""
def_fk_outcomes.py

Two charts:

  def_fk_outcomes.png         Distribution of defending-FK outcomes for
                              Barcelona vs the league average (per-team
                              equal weighting), shown as percentages.

  def_fk_outcomes_by_zone.png Same Barcelona distribution split by FK
                              origin zone (Wide vs Central, then by
                              distance band) — shows whether outcomes
                              depend on where the FK is taken from.

Usage:
    python src/defense/free_kicks/def_fk_outcomes.py
"""

import matplotlib.pyplot as plt
import numpy as np

from defending_free_kicks import (
    BARCELONA,
    DEF_FK_ASSETS_DIR,
    OUTCOME_COLORS,
    all_teams,
    average_distributions,
    build_pairs,
    classify_fk_outcome,
    fk_distance_band,
    fk_outcome_pcts,
    fk_side,
    order_outcomes,
)


# ── Bar chart: Barcelona vs league average ───────────────────────────────────

def plot_barca_vs_league(
    barca_pcts: dict[str, float],
    avg_pcts: dict[str, float],
    barca_n: int,
    avg_n: float,
    save: bool = True,
) -> None:
    labels = order_outcomes(list(set(barca_pcts) | set(avg_pcts)))
    barca_vals = [barca_pcts.get(l, 0.0) for l in labels]
    avg_vals   = [avg_pcts.get(l, 0.0)   for l in labels]

    x = np.arange(len(labels))
    width = 0.38

    fig, ax = plt.subplots(figsize=(13, 5.5))
    bars_b = ax.bar(
        x - width / 2, barca_vals, width,
        label=f"Barcelona (N={barca_n})",
        color="steelblue", edgecolor="white",
    )
    bars_a = ax.bar(
        x + width / 2, avg_vals, width,
        label=f"League average (M={avg_n:.1f})",
        color="darkorange", edgecolor="white",
    )

    for bars, n in ((bars_b, barca_n), (bars_a, avg_n)):
        for b in bars:
            h = b.get_height()
            if h <= 0:
                continue
            count = round(h / 100 * n)
            ax.text(
                b.get_x() + b.get_width() / 2, h + 0.3,
                f"{h:.1f}%\n({count})",
                ha="center", va="bottom", fontsize=8,
            )

    ax.set_ylabel("% of defending free kicks")
    ax.set_title("Defending Free Kicks – Barcelona vs League Average")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_outcomes.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Stacked bar: Barcelona outcomes split by origin zone ─────────────────────

def _zone_label(fk_ev: dict) -> str:
    side = fk_side(fk_ev)
    band = fk_distance_band(fk_ev)
    if side == "Central":
        return f"Central ({band})"
    return f"Wide {side.lower()} ({band})"


_ZONE_ORDER = [
    "Central (Direct)",
    "Central (Crossing)",
    "Central (Long Range)",
    "Wide left (Direct)",
    "Wide left (Crossing)",
    "Wide left (Long Range)",
    "Wide right (Direct)",
    "Wide right (Crossing)",
    "Wide right (Long Range)",
]


def _outcome_by_zone(pairs: list[tuple]) -> dict[str, dict[str, int]]:
    """Return ``{zone: {outcome: count}}`` for the focus team."""
    out: dict[str, dict[str, int]] = {}
    for fk, events in pairs:
        zone = _zone_label(fk)
        outcome = classify_fk_outcome(fk, events)
        bucket = out.setdefault(zone, {})
        bucket[outcome] = bucket.get(outcome, 0) + 1
    return out


def plot_outcomes_by_zone(pairs: list[tuple], save: bool = True) -> None:
    by_zone = _outcome_by_zone(pairs)
    zones = [z for z in _ZONE_ORDER if z in by_zone]
    zones += sorted(z for z in by_zone if z not in _ZONE_ORDER)
    if not zones:
        print("No zones with data — skipping plot.")
        return

    all_outcomes = set()
    for z in zones:
        all_outcomes.update(by_zone[z])
    outcomes = order_outcomes(list(all_outcomes))

    # Convert to percentages within each zone for fair comparison
    matrix = np.zeros((len(outcomes), len(zones)))
    zone_totals = []
    for j, z in enumerate(zones):
        total = sum(by_zone[z].values())
        zone_totals.append(total)
        for i, o in enumerate(outcomes):
            matrix[i, j] = 100.0 * by_zone[z].get(o, 0) / total if total else 0.0

    fig, ax = plt.subplots(figsize=(13, 6))
    bottom = np.zeros(len(zones))
    x = np.arange(len(zones))
    for i, o in enumerate(outcomes):
        vals = matrix[i]
        ax.bar(
            x, vals, bottom=bottom, width=0.7,
            color=OUTCOME_COLORS.get(o, "#888888"),
            edgecolor="white", linewidth=0.5,
            label=o,
        )
        # Inline labels for visible segments
        for j, v in enumerate(vals):
            if v >= 8.0:
                ax.text(
                    x[j], bottom[j] + v / 2, f"{v:.0f}%",
                    ha="center", va="center", fontsize=8, color="white",
                )
        bottom += vals

    xticks = [f"{z}\n(N={n})" for z, n in zip(zones, zone_totals)]
    ax.set_xticks(x)
    ax.set_xticklabels(xticks, fontsize=9)
    ax.set_ylabel("% of defending FKs in this zone")
    ax.set_ylim(0, 100)
    ax.set_title(
        f"Barcelona Defending FK Outcomes by Origin Zone (N={sum(zone_totals)})"
    )
    ax.legend(
        loc="upper left", bbox_to_anchor=(1.01, 1.0),
        fontsize=8, frameon=False,
    )
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_FK_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_FK_ASSETS_DIR / "def_fk_outcomes_by_zone.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    barca_pairs = build_pairs(BARCELONA)
    barca_n = len(barca_pairs)
    print(f"Barcelona defending FKs (attacking half): {barca_n}")
    barca_pcts = fk_outcome_pcts(barca_pairs)

    teams = [t for t in all_teams() if BARCELONA.casefold() not in t.casefold()]
    team_pairs = [build_pairs(t) for t in teams]
    avg_pcts = average_distributions([fk_outcome_pcts(p) for p in team_pairs])
    avg_n = sum(len(p) for p in team_pairs) / len(team_pairs) if team_pairs else 0.0
    print(f"League average defending FKs per team: {avg_n:.1f}")

    plot_barca_vs_league(barca_pcts, avg_pcts, barca_n, avg_n)
    plot_outcomes_by_zone(barca_pairs)


if __name__ == "__main__":
    run()
