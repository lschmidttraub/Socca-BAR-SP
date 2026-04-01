"""Analysis module registry."""

from . import corners, free_kicks, penalties, throw_ins, goal_kicks, defensive

ANALYSES: dict[str, object] = {
    "corners": corners,
    "free_kicks": free_kicks,
    "penalties": penalties,
    "throw_ins": throw_ins,
    "goal_kicks": goal_kicks,
    "defensive": defensive,
}
