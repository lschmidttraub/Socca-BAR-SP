"""Top corner takers and first-delivery receivers for FC Barcelona.

Generates the two horizontal bar charts embedded in the *Offensive
Corners* subsection of the BAR-SP wiki page:

* ``corner_takers_single.png``      — top 8 Barcelona corner takers
* ``delivery_receivers_single.png`` — top 8 Barcelona delivery receivers

Run with::

    uv run python snippets/corner_player_roles/top_takers_and_receivers.py
    uv run python snippets/corner_player_roles/top_takers_and_receivers.py Barcelona out_dir
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt  # noqa: E402

from _loader import collect_corner_data  # noqa: E402

FOCUS_TEAM = "Barcelona"
DEFAULT_OUTPUT_DIR = Path("corner_player_plots")
BARCELONA_RED = "#a50026"
TOP_N = 8


def _plot_horizontal_counts(
    items: list[tuple[str, int]],
    *,
    title: str,
    xlabel: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(10, max(4.5, len(items) * 0.55)))
    if not items:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return

    # Highest-count bar on top, so reverse for matplotlib's bottom-up order.
    names = [name for name, _ in items][::-1]
    vals = [val for _, val in items][::-1]
    bars = ax.barh(names, vals, color=BARCELONA_RED, edgecolor="white", linewidth=0.6)
    xmax = max(vals) if vals else 1
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_width() + max(xmax, 1) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
            fontsize=10,
        )
    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, xmax * 1.18 if xmax > 0 else 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _print_ranking(header: str, items: list[tuple[str, int]]) -> None:
    print(header)
    print("-" * 60)
    if not items:
        print("  (no data)")
        return
    width = max(len(name) for name, _ in items)
    for name, count in items:
        print(f"  {name:<{width}}  {count:>3}")


def main(focus_team: str, output_dir: Path) -> None:
    records = collect_corner_data(focus_team=focus_team)
    if not records:
        raise SystemExit(f"No corner data for team {focus_team!r}")

    taker_counts = Counter(
        r["taker"] for r in records if r["taker"] not in ("", "Unknown")
    ).most_common(TOP_N)
    receiver_counts = Counter(
        r["delivery_receiver"]
        for r in records
        if r["delivery_receiver"] not in ("", "Unknown")
    ).most_common(TOP_N)

    print(f"Corner player roles — {focus_team}")
    print("-" * 60)
    print(f"  Corners taken (with a known taker): {sum(c for _, c in taker_counts)}")
    print(f"  Total corners tracked             : {len(records)}")
    print()
    _print_ranking(f"Top {TOP_N} corner takers — {focus_team}", taker_counts)
    print()
    _print_ranking(f"Top {TOP_N} first-delivery receivers — {focus_team}", receiver_counts)
    print()
    print(f"Saving plots to {output_dir}/ ...")

    takers_path = output_dir / "corner_takers_single.png"
    receivers_path = output_dir / "delivery_receivers_single.png"

    _plot_horizontal_counts(
        taker_counts,
        title=f"{focus_team} corners - top takers",
        xlabel="Corners taken",
        output_path=takers_path,
    )
    print(f"  saved {takers_path}")

    _plot_horizontal_counts(
        receiver_counts,
        title=f"{focus_team} corners - top first receivers",
        xlabel="Deliveries received",
        output_path=receivers_path,
    )
    print(f"  saved {receivers_path}")


if __name__ == "__main__":
    team = sys.argv[1] if len(sys.argv) > 1 else FOCUS_TEAM
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    main(team, out)
