"""Pitch geometry utilities for StatsBomb coordinate system.

StatsBomb uses a 120 x 80 yard pitch. The acting team always attacks
toward x = 120.  Goal centre is at (120, 40).
"""

from __future__ import annotations

YARDS_TO_METERS = 0.9144
PITCH_LENGTH = 120  # yards
PITCH_WIDTH = 80  # yards
GOAL_X = 120
GOAL_Y = 40

# 18-yard box boundaries (attacking end)
BOX_X_MIN = 102  # 120 - 18
BOX_Y_MIN = 18  # 40 - 22 (goal is 8yd wide, box extends 22yd each side of centre)
BOX_Y_MAX = 62  # 40 + 22


def distance_to_goal(location: list[float]) -> float:
    """Euclidean distance from *location* to the centre of the attacking goal, in metres."""
    x, y = location[0], location[1]
    dist_yards = ((GOAL_X - x) ** 2 + (GOAL_Y - y) ** 2) ** 0.5
    return dist_yards * YARDS_TO_METERS


def distance_from_baseline(location: list[float]) -> float:
    """Distance from own baseline (x = 0) in metres."""
    return location[0] * YARDS_TO_METERS


def bucket(value: float, size: float = 5.0) -> int:
    """Floor-bucket a value.  ``bucket(17.3, 5) -> 15``."""
    return int(value // size) * int(size)


def bucket_label(b: int, size: float = 5.0) -> str:
    """Human-readable bucket label.  ``bucket_label(15, 5) -> '15–20m'``."""
    return f"{b}\u2013{b + int(size)}m"


def is_in_box(location: list[float]) -> bool:
    """True if *location* is inside the attacking 18-yard box."""
    x, y = location[0], location[1]
    return x >= BOX_X_MIN and BOX_Y_MIN <= y <= BOX_Y_MAX
