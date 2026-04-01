"""Set piece stats library for UCL 2025-26 analysis."""

from .compare import compare
from .groups import ALL, TOP_8, TOP_16, BARCELONA_OPPONENTS, GROUPS, Group
from .models import AnalysisResult, SetPieceKind

__all__ = [
    "compare",
    "ALL",
    "TOP_8",
    "TOP_16",
    "BARCELONA_OPPONENTS",
    "GROUPS",
    "Group",
    "AnalysisResult",
    "SetPieceKind",
]
