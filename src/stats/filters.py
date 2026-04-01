"""Event filtering predicates for StatsBomb events.

Each function takes a single event dict and returns a bool (or a value).
"""


# ── Type predicates ──────────────────────────────────────────────────

def is_pass(e: dict) -> bool:
    return e.get("type", {}).get("id") == 30


def is_shot(e: dict) -> bool:
    return e.get("type", {}).get("id") == 16


# ── Set piece pass predicates ────────────────────────────────────────

def _pass_type_name(e: dict) -> str | None:
    return e.get("pass", {}).get("type", {}).get("name")


def is_corner_pass(e: dict) -> bool:
    return is_pass(e) and _pass_type_name(e) == "Corner"


def is_fk_pass(e: dict) -> bool:
    return is_pass(e) and _pass_type_name(e) == "Free Kick"


def is_throw_in(e: dict) -> bool:
    return is_pass(e) and _pass_type_name(e) == "Throw-in"


def is_goal_kick(e: dict) -> bool:
    return is_pass(e) and _pass_type_name(e) == "Goal Kick"


# ── Set piece shot predicates ────────────────────────────────────────

def _shot_type_name(e: dict) -> str | None:
    return e.get("shot", {}).get("type", {}).get("name")


def is_corner_shot(e: dict) -> bool:
    return is_shot(e) and _shot_type_name(e) == "Corner"


def is_fk_shot(e: dict) -> bool:
    return is_shot(e) and _shot_type_name(e) == "Free Kick"


def is_penalty_shot(e: dict) -> bool:
    return is_shot(e) and _shot_type_name(e) == "Penalty"


# ── Outcome predicates ───────────────────────────────────────────────

def is_pass_completed(e: dict) -> bool:
    """A completed pass has no outcome (None means success in StatsBomb)."""
    return is_pass(e) and e.get("pass", {}).get("outcome") is None


def is_goal(e: dict) -> bool:
    return e.get("shot", {}).get("outcome", {}).get("name") == "Goal"


def shot_xg(e: dict) -> float:
    return e.get("shot", {}).get("statsbomb_xg", 0.0)


def shot_outcome(e: dict) -> str:
    return e.get("shot", {}).get("outcome", {}).get("name", "Unknown")


# ── Play pattern predicates ──────────────────────────────────────────

_SET_PIECE_PATTERNS = frozenset(
    ["From Corner", "From Free Kick", "From Throw In", "From Goal Kick"]
)


def is_from_set_piece(e: dict) -> bool:
    return e.get("play_pattern", {}).get("name", "") in _SET_PIECE_PATTERNS


def play_pattern(e: dict) -> str:
    return e.get("play_pattern", {}).get("name", "")


# ── Team / player helpers ────────────────────────────────────────────

def event_team(e: dict) -> str:
    return e.get("team", {}).get("name", "")


def event_player(e: dict) -> str:
    return e.get("player", {}).get("name", "")


def by_team(e: dict, team: str) -> bool:
    return event_team(e) == team
