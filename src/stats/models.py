"""Result types and enums for set piece analysis."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class SetPieceKind(enum.Enum):
    CORNER = "corner"
    FREE_KICK = "free_kick"
    PENALTY = "penalty"
    THROW_IN = "throw_in"
    GOAL_KICK = "goal_kick"


@dataclass
class AnalysisResult:
    """Standard envelope returned by every analysis."""

    analysis: str
    team: str
    matches: int
    metrics: dict = field(default_factory=dict)
    breakdowns: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "team": self.team,
            "matches": self.matches,
            "metrics": self.metrics,
            "breakdowns": self.breakdowns,
        }
