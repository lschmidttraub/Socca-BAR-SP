"""Team group definitions for comparison.

Each group knows how to resolve itself to a set of team names given a
data directory.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable

from . import data as _data


# ── Internal helpers ─────────────────────────────────────────────────

def _compute_standings(data_dir: Path) -> list[str]:
    """Return team names sorted by league phase points desc, then GD desc."""
    points: dict[str, int] = defaultdict(int)
    gd: dict[str, int] = defaultdict(int)

    for row, events in _data.iter_matches(data_dir):
        try:
            t1, t2 = _data.get_team_names(row)
        except ValueError:
            continue

        goals = {t1: 0, t2: 0}
        for e in events:
            if (
                e.get("type", {}).get("id") == 16
                and e.get("shot", {}).get("outcome", {}).get("name") == "Goal"
            ):
                team = e.get("team", {}).get("name")
                if team in goals:
                    goals[team] += 1

        g1, g2 = goals[t1], goals[t2]
        gd[t1] += g1 - g2
        gd[t2] += g2 - g1
        if g1 > g2:
            points[t1] += 3
        elif g2 > g1:
            points[t2] += 3
        else:
            points[t1] += 1
            points[t2] += 1

    all_teams = set(points) | set(gd)
    return sorted(all_teams, key=lambda t: (points[t], gd[t]), reverse=True)


def _all_teams(data_dir: Path) -> set[str]:
    standings = _compute_standings(data_dir)
    return set(standings)


def _top_n(n: int) -> Callable[[Path], set[str]]:
    def resolver(data_dir: Path) -> set[str]:
        return set(_compute_standings(data_dir)[:n])
    return resolver


def _barcelona_opponents(data_dir: Path) -> set[str]:
    opponents: set[str] = set()
    for row, _events in _data.iter_matches(data_dir):
        try:
            t1, t2 = _data.get_team_names(row)
        except ValueError:
            continue
        if t1 == "Barcelona":
            opponents.add(t2)
        elif t2 == "Barcelona":
            opponents.add(t1)
    return opponents


# ── Group class ──────────────────────────────────────────────────────

class Group:
    """A named set of teams that can be resolved from data."""

    def __init__(self, name: str, resolver: Callable[[Path], set[str]]) -> None:
        self.name = name
        self._resolver = resolver

    def resolve(self, data_dir: Path) -> set[str]:
        """Return the set of team names in this group."""
        return self._resolver(data_dir)

    def __repr__(self) -> str:
        return f"Group({self.name!r})"


# ── Pre-defined groups ───────────────────────────────────────────────

ALL = Group("all", _all_teams)
TOP_8 = Group("top_8", _top_n(8))
TOP_16 = Group("top_16", _top_n(16))
BARCELONA_OPPONENTS = Group("barcelona_opponents", _barcelona_opponents)

# Lookup by CLI name
GROUPS: dict[str, Group] = {
    "all": ALL,
    "top8": TOP_8,
    "top16": TOP_16,
    "barcelona_opponents": BARCELONA_OPPONENTS,
}
