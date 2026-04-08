"""Master runner — regenerate every set piece visualisation.

Runs all four analysis scripts in sequence:

  setpiece_maps      → assets/setpiece_maps/{team}/
  setpiece_counts    → assets/setpiece_counts/{team}/
  setpiece_players   → assets/setpiece_players/{team}/
  setpiece_counts_avg→ assets/setpiece_counts_avg/          (all teams)
                       assets/setpiece_counts_avg/top8/     (top-8 only)

Usage (from the repo root)::

    # Run everything for the default team (Barcelona):
    python -m src.stats.analyses.run_all

    # Or supply a different focus team:
    python -m src.stats.analyses.run_all --team "Real Madrid"

    # Run only specific groups  (maps, counts, players, avg):
    python -m src.stats.analyses.run_all --only maps counts
"""

import argparse
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from stats.analyses import setpiece_maps
    from stats.analyses import setpiece_counts
    from stats.analyses import setpiece_players
    from stats.analyses import setpiece_counts_avg
    from stats.analyses import setpiece_counts_avg_defensive
    from stats.analyses import physicality
else:
    from . import setpiece_maps
    from . import setpiece_counts
    from . import setpiece_players
    from . import setpiece_counts_avg
    from . import setpiece_counts_avg_defensive
    from . import physicality

DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

ALL_GROUPS = ("maps", "counts", "players", "avg", "avg_defensive", "physicality")


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def run(
    team: str = "Barcelona",
    data_dir: Path = DATA,
    only: tuple[str, ...] = ALL_GROUPS,
) -> None:
    """Generate all (or a subset of) set piece visualisations.

    Parameters
    ----------
    team:
        Focus team for per-team charts (maps, counts, players).
    data_dir:
        Root folder containing the StatsBomb event ZIPs / JSONs.
    only:
        Which chart groups to run.  Any subset of
        ``("maps", "counts", "players", "avg", "physicality")``.
    """
    t0 = time.perf_counter()

    if "maps" in only:
        _section(f"Pitch maps  →  assets/setpiece_maps/{team}/")
        setpiece_maps.run(team=team, data_dir=data_dir)

    if "counts" in only:
        _section(f"Per-match counts  →  assets/setpiece_counts/{team}/")
        setpiece_counts.run(team=team, data_dir=data_dir)

    if "players" in only:
        _section(f"Player charts  →  assets/setpiece_players/{team}/")
        setpiece_players.run(team=team, data_dir=data_dir)

    if "avg" in only:
        _section("Avg comparison (all teams + top-8)  ->  assets/setpiece_counts_avg/")
        setpiece_counts_avg.run(focus_team=team, data_dir=data_dir)

    if "avg_defensive" in only:
        _section("Defensive avg comparison (all teams + top-8)  ->  assets/setpiece_counts_avg_defensive/")
        setpiece_counts_avg_defensive.run(focus_team=team, data_dir=data_dir)

    if "physicality" in only:
        _section(f"Physicality / height  →  assets/physicality/")
        physicality.run(focus_team=team, data_dir=data_dir)

    elapsed = time.perf_counter() - t0
    print(f"\n{'═' * 60}")
    print(f"  All done in {elapsed:.1f} s")
    print(f"{'═' * 60}\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate all set piece visualisations.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--team", default="Barcelona",
        help="Focus team name (default: Barcelona)",
    )
    parser.add_argument(
        "--only", nargs="+", choices=list(ALL_GROUPS), default=list(ALL_GROUPS),
        metavar="GROUP",
        help=(
            "Which groups to run.  Choices: maps counts players avg\n"
            "(default: all)"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(team=args.team, only=tuple(args.only))