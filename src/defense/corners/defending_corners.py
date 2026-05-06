import json
import math
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets"
DEF_CORNER_ASSETS_DIR = ASSETS_DIR / "def_corner_analysis"
MATCHES_CSV = Path(__file__).parent.parent.parent.parent / "data" / "matches.csv"
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "statsbomb" / "league_phase"
BARCELONA = "Barcelona"


# ── Match / team helpers ──────────────────────────────────────────────────────

def _read_matches_df(matches_csv: Path = MATCHES_CSV) -> pd.DataFrame:
    return pd.read_csv(
        matches_csv,
        names=["date", "utc", "statsbomb", "skillcorner", "home", "score", "away", "wyscout", "videooffset"],
        header=0,
    )


def team_games(team_name: str, matches_csv: Path = MATCHES_CSV) -> list[int]:
    """Return statsbomb IDs for all matches where team_name is home or away."""
    df = _read_matches_df(matches_csv)
    mask = (
        df["home"].str.contains(team_name, case=False, na=False)
        | df["away"].str.contains(team_name, case=False, na=False)
    )
    return df.loc[mask, "statsbomb"].astype(int).tolist()


def barca_games(matches_csv: Path = MATCHES_CSV) -> list[int]:
    """Return statsbomb IDs for all matches where Barcelona is home or away."""
    return team_games(BARCELONA, matches_csv)


def all_teams(matches_csv: Path = MATCHES_CSV) -> list[str]:
    """Return all unique team names across all matches."""
    df = _read_matches_df(matches_csv)
    teams = pd.concat([df["home"], df["away"]]).dropna().unique().tolist()
    return sorted(teams)


def read_statsbomb(statsbomb_id: int) -> list:
    """Return events from the statsbomb JSON file for the given match ID."""
    path = DATA_DIR / f"{statsbomb_id}.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def playing_teams(statsbomb_id: int) -> tuple[str, str]:
    """Return the two teams playing in a match from the lineups JSON."""
    path = DATA_DIR / f"{statsbomb_id}_lineups.json"
    with open(path, encoding="utf-8") as f:
        lineups = json.load(f)
    return (lineups[0]["team_name"], lineups[1]["team_name"])


def barca_opponent(teams: tuple[str, str]) -> str:
    if teams[0] == "Barcelona": return teams[1]
    elif teams[1] == "Barcelona": return teams[0]
    else: assert "BARCELONA IS NOT PLAYING"


def get_result(statsbomb_id: int) -> list:
    """Return [team1, team2, count1, count2] with the final score of the match."""
    team1, team2 = playing_teams(statsbomb_id)
    events = read_statsbomb(statsbomb_id)
    other = {team1: team2, team2: team1}
    goals = {team1: 0, team2: 0}
    for ev in events:
        team = ev.get("team", {}).get("name")
        type_name = ev.get("type", {}).get("name", "")
        if type_name == "Shot":
            outcome = ev.get("shot", {}).get("outcome", {}).get("name")
            if outcome == "Goal" and team in goals:
                goals[team] += 1
            elif outcome == "Own Goal For" and team in other:
                goals[other[team]] += 1
        elif type_name == "Own Goal Against" and team in other:
            goals[other[team]] += 1
    return [team1, team2, goals[team1], goals[team2]]


def print_game_result(result: list) -> str:
    """Print the game result in a readable format."""
    team1, team2, count1, count2 = result
    return (f"  {team1:<30} {count1} – {count2}  {team2}")


# ── Corner classification ─────────────────────────────────────────────────────

TYPE_SHOT         = 16
TYPE_CLEARANCE    = 9
TYPE_GOALKEEPER   = 23
TYPE_INTERCEPTION = 10
TYPE_BLOCK        = 6
TYPE_FOUL_WON     = 21
TYPE_FOUL_COMMIT  = 22

SHORT_CORNER_LENGTH = 10  # metres — passes shorter than this are treated as short corners


def corner_sequence(corner_ev: dict, events: list) -> list:
    """Return all events belonging to the corner sequence (play_pattern='From Corner')
    that follow the given corner kick event, in index order."""
    corner_index = corner_ev.get("index", -1)
    result = []
    for ev in sorted(events, key=lambda e: e.get("index", -1)):
        if ev.get("index", -1) <= corner_index:
            continue
        if ev.get("play_pattern", {}).get("name") == "From Corner":
            result.append(ev)
        else:
            break
    return result


def classify_corner_outcome(corner_ev: dict, events: list) -> str:
    """
    Classify the outcome of a single defending corner sequence.

    Priority (highest to lowest):
      Goal          – sequence contained a shot that went in
      Shot          – sequence contained a shot (no goal)
      Goalkeeper    – goalkeeper action (claim, punch, etc.)
      Clearance     – defending team headed/kicked it clear
      Interception  – defending team intercepted
      Block         – player blocked a shot/pass
      Foul          – foul committed or won during the sequence
      Short Corner  – corner kick delivered short (pass length < threshold)
      Out of Play   – no events followed the corner kick
      Other         – anything else
    """
    length = corner_ev.get("pass", {}).get("length", float("inf"))
    if length < SHORT_CORNER_LENGTH:
        return "Short Corner"

    sequence = corner_sequence(corner_ev, events)

    if not sequence:
        return "Out of Play"

    has_shot = False
    for ev in sequence:
        type_id = ev.get("type", {}).get("id")
        if type_id == TYPE_SHOT:
            outcome = ev.get("shot", {}).get("outcome", {}).get("name", "")
            if outcome == "Goal":
                return "Goal"
            has_shot = True

    if has_shot:
        return "Shot"

    for ev in sequence:
        type_id = ev.get("type", {}).get("id")
        if type_id == TYPE_GOALKEEPER:
            return "Goalkeeper"
        if type_id == TYPE_CLEARANCE:
            return "Clearance"
        if type_id == TYPE_INTERCEPTION:
            return "Interception"
        if type_id == TYPE_BLOCK:
            return "Block"
        if type_id in (TYPE_FOUL_WON, TYPE_FOUL_COMMIT):
            return "Foul"

    return "Other"


# ── Distribution helpers ──────────────────────────────────────────────────────

def team_defend_corners(events: list, team_name: str) -> list:
    """Return all corner kick events taken against team_name."""
    return [
        ev for ev in events
        if ev.get("type", {}).get("id") == 30
        and ev.get("pass", {}).get("type", {}).get("name") == "Corner"
        and team_name.casefold() not in ev.get("team", {}).get("name", "").casefold()
    ]


def barca_defend_corners(events: list) -> list:
    """Return all corner kick events taken against Barcelona."""
    return team_defend_corners(events, BARCELONA)


def build_pairs(team_name: str) -> list[tuple]:
    """Return (corner_ev, events) pairs for all defending corners of team_name."""
    pairs = []
    for game_id in team_games(team_name):
        path = DATA_DIR / f"{game_id}.json"
        if not path.exists():
            print(f"Missing statsbomb file for game {game_id}, skipping.")
            continue
        events = read_statsbomb(game_id)
        for corner in team_defend_corners(events, team_name):
            pairs.append((corner, events))
    return pairs


def compute_outcome_pcts(corner_event_pairs: list[tuple]) -> dict[str, float]:
    """Return outcome -> % distribution for the given (corner, events) pairs."""
    counts: dict[str, int] = {}
    for corner, events in corner_event_pairs:
        outcome = classify_corner_outcome(corner, events)
        counts[outcome] = counts.get(outcome, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: 100 * v / total for k, v in counts.items()}


def average_distributions(dists: list[dict[str, float]]) -> dict[str, float]:
    """Average a list of outcome distributions, giving each team equal weight.
    Outcomes absent for a team are treated as 0%."""
    all_keys = {k for d in dists for k in d}
    return {
        k: sum(d.get(k, 0.0) for d in dists) / len(dists)
        for k in all_keys
    }


# ── Side helper ──────────────────────────────────────────────────────────────

def corner_side(corner_ev: dict) -> str:
    """Return 'Left' or 'Right' based on the y-coordinate of the corner kick location."""
    y = corner_ev.get("location", [None, None])[1]
    if y is None:
        return "Unknown"
    return "Left" if y < 40 else "Right"


# ── Normalisation helper ──────────────────────────────────────────────────────

def normalize_to_right(loc: list, corner_loc: list) -> list:
    """Return loc with x flipped if the corner kick is in the left half (x < 60),
    so all defending corners are shown as if Barcelona's goal is at x = 120.
    This aligns with mplsoccer's half=True view (x: 60–120)."""
    x, y = loc
    if corner_loc[0] < 60:
        x = 120 - x
    return [x, y]


# ── Aerial classifier ────────────────────────────────────────────────────────

def action_body_part(event: dict) -> str | None:
    """Return the body part name used in an event (e.g. 'Head', 'Left Foot').
    Checks all common sub-dicts that carry a body_part field."""
    for key in ("clearance", "pass", "shot", "goalkeeper", "interception", "duel", "miscontrol"):
        bp = event.get(key, {}).get("body_part", {}).get("name")
        if bp:
            return bp
    return None


def is_aerial(event: dict) -> bool:
    """Return True if the action was performed with the head."""
    return action_body_part(event) == "Head"


# ── Distance helpers ──────────────────────────────────────────────────────────

def distance(loc1: list, loc2: list) -> float:
    """Euclidean distance between two [x, y] locations."""
    return math.hypot(loc1[0] - loc2[0], loc1[1] - loc2[1])


def first_sequence_action(corner_ev: dict, events: list) -> dict | None:
    """Return the first event in the corner sequence after the corner kick itself."""
    seq = corner_sequence(corner_ev, events)
    return seq[0] if seq else None


def corner_to_first_action_distance(corner_ev: dict, events: list) -> float | None:
    """Distance from the corner kick location to the first action in the sequence.
    Returns None if the sequence is empty or either location is missing."""
    first = first_sequence_action(corner_ev, events)
    if first is None:
        return None
    corner_loc = corner_ev.get("location")
    action_loc = first.get("location")
    if corner_loc is None or action_loc is None:
        return None
    return distance(corner_loc, action_loc)


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_corner_classes(
    barca_pcts: dict[str, float],
    avg_pcts: dict[str, float],
    barca_n: int,
    avg_n: float,
    save: bool = True,
) -> None:
    """Plot Barcelona's defending corner outcome distribution vs. the league average.

    barca_n: total Barcelona defending corners
    avg_n:   average defending corners per team across the league
    """
    labels = sorted(barca_pcts, key=barca_pcts.get, reverse=True)
    for k in avg_pcts:
        if k not in labels:
            labels.append(k)

    barca_vals = [barca_pcts.get(l, 0.0) for l in labels]
    avg_vals   = [avg_pcts.get(l, 0.0)   for l in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    bars_b = ax.bar(x - width / 2, barca_vals, width, label=f"Barcelona (N={barca_n})",          color="steelblue",  edgecolor="white")
    bars_a = ax.bar(x + width / 2, avg_vals,   width, label=f"League average (M={avg_n:.1f})",   color="darkorange", edgecolor="white")

    for bar in bars_b:
        h = bar.get_height()
        count = round(h / 100 * barca_n)
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3, f"{h:.1f}%\n({count})", ha="center", va="bottom", fontsize=8)
    for bar in bars_a:
        h = bar.get_height()
        count = round(h / 100 * avg_n)
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3, f"{h:.1f}%\n({count})", ha="center", va="bottom", fontsize=8)

    ax.set_ylabel("% of defending corners")
    ax.set_title(f"Defending Corners – Barcelona vs. League Average")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "defending_corners.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


def plot_corner_classes_by_side(pairs: list[tuple], save: bool = True) -> None:
    """Plot defending corner outcome distribution split by left vs. right corner."""
    # "left" or "right" is from Barcelonas perspective
    left_pairs  = [(c, e) for c, e in pairs if corner_side(c) == "Left"]
    right_pairs = [(c, e) for c, e in pairs if corner_side(c) == "Right"]

    def _counts(pairs):
        c = {}
        for corner, events in pairs:
            outcome = classify_corner_outcome(corner, events)
            c[outcome] = c.get(outcome, 0) + 1
        return c

    left_counts  = _counts(left_pairs)
    right_counts = _counts(right_pairs)

    labels = sorted(left_counts, key=left_counts.get, reverse=True)
    for k in right_counts:
        if k not in labels:
            labels.append(k)

    left_vals  = [left_counts.get(l, 0)  for l in labels]
    right_vals = [right_counts.get(l, 0) for l in labels]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    bars_l = ax.bar(x - width / 2, left_vals,  width, label=f"Left (N={len(left_pairs)})",   color="steelblue",  edgecolor="white")
    bars_r = ax.bar(x + width / 2, right_vals, width, label=f"Right (N={len(right_pairs)})",  color="darkorange", edgecolor="white")

    for bar in (bars_l, bars_r):
        for b in bar:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, h + 0.1, str(int(h)),
                    ha="center", va="bottom", fontsize=8)

    ax.set_ylabel("Number of defending corners")
    ax.set_title(f"Defending Corners by Side – Barcelona (N={len(pairs)})")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    plt.tight_layout()

    if save:
        DEF_CORNER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEF_CORNER_ASSETS_DIR / "defending_corners_by_side.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"Plot saved to {out_path}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    barca_pairs = build_pairs(BARCELONA)
    barca_n = len(barca_pairs)
    print(f"Barcelona defending corners: {barca_n}")
    barca_pcts = compute_outcome_pcts(barca_pairs)

    teams = [t for t in all_teams() if BARCELONA.casefold() not in t.casefold()]
    team_pairs = [build_pairs(t) for t in teams]
    avg_pcts = average_distributions([compute_outcome_pcts(p) for p in team_pairs])
    avg_n = sum(len(p) for p in team_pairs) / len(team_pairs)
    print(f"League average defending corners per team: {avg_n:.1f}")

    # Plots corners by Barcelona vs AVG grouped by outcome
    #plot_corner_classes(barca_pcts, avg_pcts, barca_n, avg_n)
    # Plots corners grouped by side, outcome
    #plot_corner_classes_by_side(barca_pairs)
    
