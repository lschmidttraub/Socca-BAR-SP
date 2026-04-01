"""Result types, enums, and base class for set piece analysis."""

import enum
from abc import ABC, abstractmethod
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


class Analysis(ABC):
    """Base class for a set piece analysis.

    Subclasses must set ``name`` and implement ``analyze_match`` and
    ``summarize``.
    """

    name: str

    @abstractmethod
    def analyze_match(self, events: list[dict], team: str) -> dict:
        """Return raw additive counts for one team in one match.

        All leaf values must be numbers (int or float) that can be
        summed across matches.
        """

    @abstractmethod
    def summarize(self, totals: dict, n_matches: int) -> dict:
        """Compute derived metrics from aggregated totals.

        Must return ``{"metrics": {...}, "breakdowns": {...}}``.
        """
