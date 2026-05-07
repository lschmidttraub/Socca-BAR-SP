"""Barcelona offensive-corner analysis.

This script builds a tactical corner-analysis package around mechanism rather
than only end-product. It uses StatsBomb event JSON plus lineup JSON to study:

1. Routine types and route choices
2. Delivery target zones
3. Player role patterns (takers, receivers, shooters)
4. Second-phase and recycled-possession value
5. Matchup adaptation against taller opponents

Outputs are written to ``assets/offensive_corners/``.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from mplsoccer import Pitch

def _find_project_root(start: Path) -> Path:
    """Walk upward until the repository root is found."""
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"

import sys

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.viz.style import (
    AVG_COLOR,
    FOCUS_COLOR,
    NEUTRAL_COLOR,
    POSITIVE_COLOR,
    apply_theme,
    save_fig,
)
from stats.analyses.setpiece_maps import _team_in_match

ASSETS_ROOT = (
    PROJECT_ROOT / "assets" / "offensive_corners"
)
DATA = PROJECT_ROOT / "data" / "statsbomb" / "league_phase"

TEAM = "Barcelona"
SHORT_CORNER_MAX_LEN = 15.0
SEQUENCE_MAX_SECONDS = 20.0
TOP_N_HEIGHT = 6

ROUTINE_ORDER = [
    "Direct inswing",
    "Direct outswing",
    "Direct other",
    "Short corner",
]

ZONE_ORDER = [
    "Near post",
    "Central six-yard",
    "Far post",
    "Penalty spot",
    "Edge of box",
    "Wide recycle",
]

ROUTINE_COLORS = {
    "Direct inswing": FOCUS_COLOR,
    "Direct outswing": "#f28e2b",
    "Direct other": "#8c6bb1",
    "Short corner": AVG_COLOR,
}

ZONE_COLORS = {
    "Near post": "#d73027",
    "Central six-yard": "#fc8d59",
    "Far post": "#4575b4",
    "Penalty spot": "#66bd63",
    "Edge of box": "#984ea3",
    "Wide recycle": "#878787",
}

DARK_FIG_COLOR = "white"
DARK_PITCH_COLOR = "white"
DARK_LINE_COLOR = "#c7d5cc"

FIRST_TOUCH_COLORS = {
    "Shot": "#ff4d6d",
    "Pass": "#3b82f6",
    "Carry": "#ffd43b",
}

SHOT_OUTCOME_COLORS = {
    "Goal": "#ff4d6d",
    "Saved": "#ffb000",
    "Other": "#7aa6ff",
}


def _event_time_seconds(event: dict) -> float:
    ts = event.get("timestamp", "")
    if ts:
        hh, mm, ss = ts.split(":")
        return int(hh) * 3600 + int(mm) * 60 + float(ss)
    return float(event.get("minute", 0) * 60 + event.get("second", 0))


def _flip_location(loc: list[float] | None, flip_y: bool) -> tuple[float, float] | None:
    if not loc or len(loc) < 2:
        return None
    x, y = float(loc[0]), float(loc[1])
    if flip_y:
        y = 80.0 - y
    return x, y


def _team_label(row: dict, team: str) -> str:
    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    if team == home:
        return away
    if team == away:
        return home
    return away if team in home else home


def _load_lineup(data_dir: Path, match_id: str) -> list[dict] | None:
    path = data_dir / f"{match_id}_lineups.json"
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _match_lineup_to_csv(
    lineup: list[dict], home_csv: str, away_csv: str
) -> dict[str, list[dict]]:
    if len(lineup) != 2:
        return {}

    sb_names = [td["team_name"] for td in lineup]
    players_by_sb = {td["team_name"]: td["lineup"] for td in lineup}

    def _score(csv_name: str, sb_name: str) -> int:
        a, b = csv_name.lower(), sb_name.lower()
        if a == b:
            return 3
        if a in b or b in a:
            return 2
        return len(set(a.split()) & set(b.split()))

    best_sb_home = max(sb_names, key=lambda sb_name: _score(home_csv, sb_name))
    best_sb_away = next(sb for sb in sb_names if sb != best_sb_home)

    return {
        home_csv: players_by_sb[best_sb_home],
        away_csv: players_by_sb[best_sb_away],
    }


def _actually_played(player: dict) -> bool:
    return len(player.get("positions", [])) > 0


def _is_goalkeeper(player: dict) -> bool:
    return any("Goalkeeper" in pos.get("position", "") for pos in player.get("positions", []))


def _top_n_mean(heights: list[float], n: int = TOP_N_HEIGHT) -> float | None:
    top = sorted(heights, reverse=True)[:n]
    return float(np.mean(top)) if len(top) >= n else None


def _match_physical_profile(row: dict, data_dir: Path) -> tuple[float | None, float | None]:
    match_id = row.get("statsbomb", "").strip()
    lineup = _load_lineup(data_dir, match_id)
    if lineup is None:
        return None, None

    home = row.get("home", "").strip()
    away = row.get("away", "").strip()
    mapping = _match_lineup_to_csv(lineup, home, away)
    if not mapping:
        return None, None

    team_name = next((name for name in (home, away) if TEAM in name), None)
    if not team_name:
        return None, None
    opp_name = away if team_name == home else home

    def _height_list(players: list[dict]) -> list[float]:
        return [
            float(p["player_height"])
            for p in players
            if _actually_played(p) and not _is_goalkeeper(p) and p.get("player_height")
        ]

    team_h = _top_n_mean(_height_list(mapping.get(team_name, [])))
    opp_h = _top_n_mean(_height_list(mapping.get(opp_name, [])))
    return team_h, opp_h


def _sequence_events(events: list[dict], start_idx: int) -> list[dict]:
    start = events[start_idx]
    possession = start.get("possession")
    period = start.get("period")
    t0 = _event_time_seconds(start)
    seq = [start]

    for event in events[start_idx + 1:]:
        if event.get("period") != period or event.get("possession") != possession:
            break
        if _event_time_seconds(event) - t0 > SEQUENCE_MAX_SECONDS:
            break
        seq.append(event)

    return seq


def _routine_type(corner: dict) -> str:
    length = float(corner.get("pass", {}).get("length", 0.0) or 0.0)
    if length <= SHORT_CORNER_MAX_LEN:
        return "Short corner"

    technique = corner.get("pass", {}).get("technique", {}).get("name")
    inswing = corner.get("pass", {}).get("inswinging")
    if inswing is True or technique == "Inswinging":
        return "Direct inswing"
    if inswing is False or technique == "Outswinging":
        return "Direct outswing"
    return "Direct other"


def _meaningful_delivery(sequence: list[dict], team_sb: str) -> dict | None:
    corner = sequence[0]
    if _routine_type(corner) != "Short corner":
        return corner

    for event in sequence[1:]:
        if not f.by_team(event, team_sb):
            continue
        if f.is_shot(event):
            return event
        if not f.is_pass(event):
            continue
        loc = event.get("location")
        end = event.get("pass", {}).get("end_location")
        if not loc or not end:
            continue
        if end[0] >= 96 or loc[0] >= 105 or float(event.get("pass", {}).get("length", 0.0) or 0.0) >= 12:
            return event

    return corner


def _delivery_receiver(delivery: dict, sequence: list[dict], team_sb: str) -> str:
    recipient = delivery.get("pass", {}).get("recipient", {}).get("name")
    if recipient:
        return recipient

    delivery_id = delivery.get("id")
    found_delivery = False
    for event in sequence:
        if delivery_id and event.get("id") == delivery_id:
            found_delivery = True
            continue
        if not found_delivery:
            continue
        if f.by_team(event, team_sb):
            player = f.event_player(event)
            if player:
                return player
    return "Unknown"


def _classify_zone(loc: tuple[float, float] | None) -> str:
    if loc is None:
        return "Wide recycle"

    x, y = loc
    if x >= 114 and y < 33:
        return "Near post"
    if x >= 114 and y > 47:
        return "Far post"
    if x >= 114:
        return "Central six-yard"
    if x >= 102 and 28 <= y <= 52:
        return "Penalty spot"
    if x >= 96:
        return "Edge of box"
    return "Wide recycle"


def _event_type_name(event: dict) -> str:
    return event.get("type", {}).get("name", "")


def _is_carry(event: dict) -> bool:
    return _event_type_name(event) == "Carry"


def _is_actionable(event: dict) -> bool:
    return f.is_pass(event) or f.is_shot(event) or _is_carry(event)


def _action_kind(event: dict) -> str | None:
    if f.is_shot(event):
        return "Shot"
    if f.is_pass(event):
        return "Pass"
    if _is_carry(event):
        return "Carry"
    return None


def _clip_to_pitch(loc: tuple[float, float] | None) -> tuple[float, float] | None:
    if loc is None:
        return None
    x, y = loc
    return max(60.0, min(120.0, x)), max(0.0, min(80.0, y))


def _event_end_location(event: dict, flip_y: bool) -> tuple[float, float] | None:
    end = None
    if f.is_pass(event):
        end = event.get("pass", {}).get("end_location")
    elif _is_carry(event):
        end = event.get("carry", {}).get("end_location")
    elif f.is_shot(event):
        end = event.get("shot", {}).get("end_location")
    return _clip_to_pitch(_flip_location(end, flip_y))


def _first_touch_after_corner(
    sequence: list[dict],
    team_sb: str,
    flip_y: bool,
) -> dict[str, Any] | None:
    tracked_types = {
        "Ball Receipt*",
        "Ball Recovery",
        "Carry",
        "Dribble",
        "Duel",
        "Pass",
        "Shot",
    }

    first_touch = None
    first_idx = None
    for idx, event in enumerate(sequence[1:], start=1):
        if not f.by_team(event, team_sb):
            continue
        if _event_type_name(event) not in tracked_types:
            continue
        if not event.get("location"):
            continue
        first_touch = event
        first_idx = idx
        break

    if first_touch is None or first_idx is None:
        return None

    action_event = first_touch if _is_actionable(first_touch) else None
    if action_event is None:
        for event in sequence[first_idx + 1:]:
            if not f.by_team(event, team_sb):
                continue
            if _is_actionable(event):
                action_event = event
                break

    if action_event is None:
        return None

    start = _clip_to_pitch(_flip_location(first_touch.get("location"), flip_y))
    if start is None:
        start = _clip_to_pitch(_flip_location(action_event.get("location"), flip_y))
    end = _event_end_location(action_event, flip_y)
    kind = _action_kind(action_event)
    if start is None or kind is None:
        return None

    return {
        "start": start,
        "end": end,
        "kind": kind,
        "player": f.event_player(action_event) or "Unknown",
    }


def _shot_outcome_bucket(shot: dict) -> str:
    if f.is_goal(shot):
        return "Goal"
    outcome = shot.get("shot", {}).get("outcome", {}).get("name", "")
    if "Saved" in outcome:
        return "Saved"
    return "Other"


def _shot_links(
    sequence: list[dict],
    team_sb: str,
    flip_y: bool,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []

    for idx, event in enumerate(sequence):
        if not (f.by_team(event, team_sb) and f.is_shot(event)):
            continue

        prev_pass = None
        for prev in reversed(sequence[:idx]):
            if f.by_team(prev, team_sb) and f.is_pass(prev):
                prev_pass = prev
                break

        pass_start = _clip_to_pitch(_flip_location(prev_pass.get("location"), flip_y)) if prev_pass else None
        pass_end = _event_end_location(prev_pass, flip_y) if prev_pass else None
        shot_loc = _clip_to_pitch(_flip_location(event.get("location"), flip_y))

        links.append({
            "pass_start": pass_start,
            "pass_end": pass_end,
            "shot_loc": shot_loc,
            "outcome": _shot_outcome_bucket(event),
            "shooter": f.event_player(event) or "Unknown",
        })

    return links


def _goal_sequence_actions(
    sequence: list[dict],
    team_sb: str,
    flip_y: bool,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    order = 1
    tracked_types = {
        "Ball Receipt*",
        "Ball Recovery",
        "Carry",
        "Duel",
        "Dribble",
        "Pass",
        "Shot",
    }

    for event in sequence:
        if not f.by_team(event, team_sb):
            continue
        type_name = _event_type_name(event)
        if type_name not in tracked_types:
            continue
        start = _clip_to_pitch(_flip_location(event.get("location"), flip_y))
        if start is None:
            continue
        actions.append({
            "order": order,
            "type": type_name,
            "start": start,
            "end": _event_end_location(event, flip_y),
            "player": f.event_player(event) or "Unknown",
            "is_goal": f.is_shot(event) and f.is_goal(event),
        })
        order += 1
        if f.is_shot(event) and f.is_goal(event):
            break

    return actions


def _side_title(side: str) -> str:
    if side == "bottom":
        return "Left-side corner"
    return "Right-side corner"


def _side_label(side: str) -> str:
    return _side_title(side)


def _side_slug(side: str) -> str:
    return "bottom_side" if side == "bottom" else "top_side"


def _display_point(point: tuple[float, float] | None, side: str) -> tuple[float, float] | None:
    if point is None:
        return None
    x, y = point
    if x is None or y is None:
        return None
    if side == "top":
        return x, 80.0 - y
    return x, y


def _iter_side_subsets(sequences: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    return [
        (side, [seq for seq in sequences if seq["corner_side"] == side])
        for side in ("bottom", "top")
    ]


def _shot_phase(sequence: list[dict], team_sb: str) -> tuple[str, dict | None]:
    corner_time = _event_time_seconds(sequence[0])
    action_index = 0

    for event in sequence[1:]:
        if not f.by_team(event, team_sb):
            continue
        if f.is_pass(event) or f.is_shot(event):
            action_index += 1
        if not f.is_shot(event):
            continue
        dt = _event_time_seconds(event) - corner_time
        if action_index <= 3 and dt <= 8.0:
            return "Immediate shot", event
        return "Second-phase shot", event

    return "No shot", None


def _all_team_shots(sequence: list[dict], team_sb: str) -> list[dict]:
    return [event for event in sequence if f.by_team(event, team_sb) and f.is_shot(event)]


def _abbr(label: str) -> str:
    tokens = [tok for tok in label.replace("vs ", "").split() if tok]
    if not tokens:
        return label
    if len(tokens) == 1:
        return tokens[0][:4]
    return "".join(tok[0] for tok in tokens[:3]).upper()


def _collect(team: str, data_dir: Path) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []

    for row, events in iter_matches(data_dir):
        team_sb = _team_in_match(team, row, events)
        if team_sb is None:
            continue

        opponent = _team_label(row, team)
        team_h, opp_h = _match_physical_profile(row, data_dir)

        for idx, event in enumerate(events):
            if not (f.is_pass(event) and f.is_corner_pass(event) and f.by_team(event, team_sb)):
                continue

            sequence = _sequence_events(events, idx)
            delivery = _meaningful_delivery(sequence, team_sb)
            phase, first_shot = _shot_phase(sequence, team_sb)
            shots = _all_team_shots(sequence, team_sb)
            total_xg = float(sum(f.shot_xg(shot) for shot in shots))
            first_shot_xg = float(f.shot_xg(first_shot)) if first_shot else 0.0
            added_xg = max(total_xg - first_shot_xg, 0.0)
            total_obv = float(
                sum(
                    float(e.get("obv_total_net", 0.0) or 0.0)
                    for e in sequence
                    if f.by_team(e, team_sb)
                )
            )

            flip_y = bool(event.get("location") and event["location"][1] > 40)
            corner_start = _flip_location(event.get("location"), flip_y)
            corner_end = _flip_location(event.get("pass", {}).get("end_location"), flip_y)
            delivery_start = _flip_location(delivery.get("location"), flip_y) if delivery else None
            delivery_end = (
                _flip_location(delivery.get("pass", {}).get("end_location"), flip_y)
                if delivery and f.is_pass(delivery)
                else _flip_location(delivery.get("location"), flip_y) if delivery else None
            )

            first_receiver = event.get("pass", {}).get("recipient", {}).get("name") or "Unknown"
            delivery_receiver = _delivery_receiver(delivery, sequence, team_sb) if delivery else "Unknown"
            shooter = f.event_player(first_shot) if first_shot else "No shot"
            first_shot_loc = _flip_location(first_shot.get("location"), flip_y) if first_shot else None
            first_touch = _first_touch_after_corner(sequence, team_sb, flip_y)
            shot_links = _shot_links(sequence, team_sb, flip_y)
            goal_actions = _goal_sequence_actions(sequence, team_sb, flip_y) if any(f.is_goal(shot) for shot in shots) else []

            sequences.append({
                "match_id": row.get("statsbomb", "").strip(),
                "match_label": f"vs {opponent}",
                "opponent": opponent,
                "minute": int(event.get("minute", 0)),
                "corner_taker": f.event_player(event) or "Unknown",
                "corner_side": "top" if flip_y else "bottom",
                "routine_type": _routine_type(event),
                "corner_length": float(event.get("pass", {}).get("length", 0.0) or 0.0),
                "corner_recipient": first_receiver,
                "delivery_receiver": delivery_receiver,
                "delivery_zone": _classify_zone(delivery_end),
                "shot_phase": phase,
                "shot_generated": bool(first_shot),
                "first_shot_player": shooter,
                "first_shot_xg": first_shot_xg,
                "total_xg": total_xg,
                "added_xg": added_xg,
                "shots_in_sequence": len(shots),
                "goals_in_sequence": sum(1 for shot in shots if f.is_goal(shot)),
                "total_obv": total_obv,
                "team_top6_height": team_h,
                "opponent_top6_height": opp_h,
                "height_gap": (opp_h - team_h) if team_h is not None and opp_h is not None else None,
                "corner_start_x": corner_start[0] if corner_start else None,
                "corner_start_y": corner_start[1] if corner_start else None,
                "corner_end_x": corner_end[0] if corner_end else None,
                "corner_end_y": corner_end[1] if corner_end else None,
                "delivery_start_x": delivery_start[0] if delivery_start else None,
                "delivery_start_y": delivery_start[1] if delivery_start else None,
                "delivery_end_x": delivery_end[0] if delivery_end else None,
                "delivery_end_y": delivery_end[1] if delivery_end else None,
                "first_shot_x": first_shot_loc[0] if first_shot_loc else None,
                "first_shot_y": first_shot_loc[1] if first_shot_loc else None,
                "first_touch_kind": first_touch["kind"] if first_touch else "",
                "first_touch_player": first_touch["player"] if first_touch else "",
                "first_touch_x": first_touch["start"][0] if first_touch else None,
                "first_touch_y": first_touch["start"][1] if first_touch else None,
                "first_touch_end_x": first_touch["end"][0] if first_touch and first_touch["end"] else None,
                "first_touch_end_y": first_touch["end"][1] if first_touch and first_touch["end"] else None,
                "shot_links": shot_links,
                "goal_actions": goal_actions,
            })

    return sequences


def _ordered_counts(values: list[str], order: list[str]) -> tuple[list[str], list[int]]:
    counter = Counter(values)
    labels = [label for label in order if counter.get(label, 0) > 0]
    counts = [counter[label] for label in labels]
    return labels, counts


def _plot_routine_profile(sequences: list[dict[str, Any]], output_path: Path) -> None:
    labels, counts = _ordered_counts([s["routine_type"] for s in sequences], ROUTINE_ORDER)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.subplots_adjust(top=0.86, bottom=0.08, hspace=0.32, wspace=0.24)
    ax_count, ax_rate, ax_xg, ax_zone = axes.flat

    colors = [ROUTINE_COLORS[label] for label in labels]
    ax_count.bar(labels, counts, color=colors)
    ax_count.set_title("Corner routine mix")
    ax_count.set_ylabel("Count")
    ax_count.tick_params(axis="x", rotation=20)

    shot_rates = []
    total_xg = []
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        shot_rates.append(np.mean([float(s["shot_generated"]) for s in subset]))
        total_xg.append(np.mean([s["total_xg"] for s in subset]))

    ax_rate.bar(labels, shot_rates, color=colors)
    ax_rate.set_title("Shot generation rate")
    ax_rate.set_ylabel("Share of corners with a shot")
    ax_rate.set_ylim(0, max(0.55, max(shot_rates, default=0.0) * 1.2))
    ax_rate.tick_params(axis="x", rotation=20)

    ax_xg.bar(labels, total_xg, color=colors)
    ax_xg.set_title("Average xG per corner sequence")
    ax_xg.set_ylabel("xG / corner")
    ax_xg.tick_params(axis="x", rotation=20)

    zone_shares = defaultdict(list)
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        n = len(subset) or 1
        counter = Counter(s["delivery_zone"] for s in subset)
        for zone in ZONE_ORDER:
            zone_shares[zone].append(counter.get(zone, 0) / n)

    bottom = np.zeros(len(labels))
    for zone in ZONE_ORDER:
        vals = zone_shares[zone]
        if not any(vals):
            continue
        ax_zone.bar(
            labels,
            vals,
            bottom=bottom,
            label=zone,
            color=ZONE_COLORS[zone],
            alpha=0.92,
        )
        bottom += np.array(vals)
    ax_zone.set_title("Target-zone share by routine")
    ax_zone.set_ylabel("Share of sequences")
    ax_zone.tick_params(axis="x", rotation=20)
    ax_zone.legend(loc="upper right", fontsize=8)

    _apply_light_header(
        fig,
        "Barcelona offensive corners - routine profile",
        "Routine mix, shot generation, xG and target-zone share",
    )
    save_fig(fig, output_path, tight=False)


def _draw_zone_boxes(
    ax: plt.Axes,
    *,
    line_color: str = NEUTRAL_COLOR,
    text_color: str = NEUTRAL_COLOR,
) -> None:
    boxes = [
        (114, 0, 6, 33, "Near post"),
        (114, 33, 6, 14, "Central six-yard"),
        (114, 47, 6, 33, "Far post"),
        (102, 28, 12, 24, "Penalty spot"),
        (96, 18, 6, 44, "Edge"),
    ]
    for x, y, w, h, label in boxes:
        rect = Rectangle((x, y), w, h, fill=False, lw=1.2, ls="--", ec=line_color, alpha=0.65)
        ax.add_patch(rect)


def _apply_dark_header(
    fig: plt.Figure,
    title: str,
    subtitle: str | None = None,
    *,
    title_y: float = 0.975,
    subtitle_y: float = 0.935,
    title_size: int = 18,
    subtitle_size: float = 11.0,
) -> None:
    fig.text(0.5, title_y, title, ha="center", va="top", color="#111111", fontsize=title_size, fontweight="bold")
    if subtitle:
        fig.text(0.5, subtitle_y, subtitle, ha="center", va="top", color="#333333", fontsize=subtitle_size)


def _apply_light_header(
    fig: plt.Figure,
    title: str,
    subtitle: str | None = None,
    *,
    title_y: float = 0.98,
    subtitle_y: float = 0.945,
    title_size: int = 16,
    subtitle_size: float = 11.0,
) -> None:
    fig.text(0.5, title_y, title, ha="center", va="top", color="#111111", fontsize=title_size, fontweight="bold")
    if subtitle:
        fig.text(0.5, subtitle_y, subtitle, ha="center", va="top", color="#333333", fontsize=subtitle_size)


def _plot_spatial_profile(sequences: list[dict[str, Any]], output_path: Path) -> None:
    pitch = Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#c7d5cc", half=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.subplots_adjust(top=0.82, bottom=0.08, wspace=0.22)

    for ax in axes:
        pitch.draw(ax=ax)

    for seq in sequences:
        sx = seq["delivery_start_x"]
        sy = seq["delivery_start_y"]
        ex = seq["delivery_end_x"]
        ey = seq["delivery_end_y"]
        if None not in (sx, sy, ex, ey):
            pitch.arrows(
                sx, sy, ex, ey, ax=axes[0],
                color=ROUTINE_COLORS[seq["routine_type"]],
                width=1.5, headwidth=4, headlength=4, alpha=0.55,
            )

    axes[0].set_title("First meaningful delivery routes")
    axes[0].legend(
        handles=[
            Line2D([0], [0], color=ROUTINE_COLORS[label], lw=2, label=label)
            for label in ROUTINE_ORDER
            if any(s["routine_type"] == label for s in sequences)
        ],
        loc="lower left",
        fontsize=8,
    )

    _draw_zone_boxes(axes[1])
    for zone in ZONE_ORDER:
        pts = [
            (s["delivery_end_x"], s["delivery_end_y"])
            for s in sequences
            if s["delivery_zone"] == zone and s["delivery_end_x"] is not None and s["delivery_end_y"] is not None
        ]
        if not pts:
            continue
        xs, ys = zip(*pts)
        pitch.scatter(
            xs, ys, ax=axes[1], s=55, color=ZONE_COLORS[zone],
            edgecolors="white", linewidth=0.5, alpha=0.85, label=zone,
        )
    axes[1].set_title("Delivery endpoints and target zones")
    axes[1].legend(loc="lower left", fontsize=8)

    shots = [s for s in sequences if s["first_shot_x"] is not None and s["first_shot_y"] is not None]
    if shots:
        xs = [s["first_shot_x"] for s in shots]
        ys = [s["first_shot_y"] for s in shots]
        sizes = [max(s["first_shot_xg"] * 1200, 40) for s in shots]
        pitch.scatter(
            xs, ys, ax=axes[2], s=sizes, color=FOCUS_COLOR,
            edgecolors="white", linewidth=0.7, alpha=0.8,
        )
    axes[2].set_title("First-shot locations (size = xG)")

    _apply_light_header(
        fig,
        "Barcelona offensive corners - spatial profile",
        "Delivery routes, endpoints and first-shot locations",
        title_y=0.975,
        subtitle_y=0.935,
    )
    save_fig(fig, output_path, tight=False)


def _dark_pitch_figure(
    ncols: int,
    *,
    figsize: tuple[float, float],
) -> tuple[plt.Figure, list[plt.Axes], Pitch]:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color=DARK_PITCH_COLOR,
        line_color=DARK_LINE_COLOR,
        linewidth=1.7,
    )
    fig, axes = plt.subplots(1, ncols, figsize=figsize)
    if ncols == 1:
        axes = [axes]
    else:
        axes = list(axes)
    fig.patch.set_facecolor(DARK_FIG_COLOR)

    for ax in axes:
        ax.set_facecolor(DARK_FIG_COLOR)
        ax.grid(False)
        pitch.draw(ax=ax)
        ax.set_xticks([])
        ax.set_yticks([])

    fig.subplots_adjust(top=0.8, bottom=0.14, wspace=0.22)
    return fig, axes, pitch


def _draw_corner_marker(pitch: Pitch, ax: plt.Axes, side: str) -> None:
    y = 79.4 if side == "top" else 0.6
    marker = "v" if side == "top" else "^"
    pitch.scatter(
        [119.6], [y], ax=ax, marker=marker, s=260,
        color="#ffd100", edgecolors=DARK_FIG_COLOR, linewidth=0.8, zorder=6,
    )


def _add_dark_legend(fig: plt.Figure, handles: list[Any], ncol: int = 4) -> None:
    legend = fig.legend(
        handles=handles,
        loc="lower center",
        ncol=ncol,
        frameon=True,
        bbox_to_anchor=(0.5, 0.02),
        fontsize=10,
    )
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#cccccc")
    for text in legend.get_texts():
        text.set_color("#111111")


def _plot_delivery_routes_by_side(sequences: list[dict[str, Any]], output_path: Path) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        "Barcelona corners - first meaningful deliveries by side",
        "Arrow = delivery route   Dot = delivery endpoint   Colour = routine type",
    )

    for ax, (side, subset) in zip(axes, _iter_side_subsets(sequences)):
        _draw_corner_marker(pitch, ax, side)
        for seq in subset:
            start = _display_point((seq["delivery_start_x"], seq["delivery_start_y"]), side)
            end = _display_point((seq["delivery_end_x"], seq["delivery_end_y"]), side)
            if start is None or end is None:
                continue
            color = ROUTINE_COLORS[seq["routine_type"]]
            pitch.arrows(
                start[0], start[1], end[0], end[1], ax=ax,
                color=color, width=1.6, headwidth=4.5, headlength=4.5,
                alpha=0.55, zorder=2,
            )
            pitch.scatter([end[0]], [end[1]], ax=ax, s=42, color=color, edgecolors="white", linewidth=0.5, zorder=3)

        counts = Counter(seq["routine_type"] for seq in subset)
        text = "\n".join(
            f"{label}: {counts[label]}"
            for label in ROUTINE_ORDER
            if counts.get(label, 0) > 0
        )
        ax.set_title(
            f"{_side_title(side)}  -  n = {len(subset)}",
            color="#111111",
            fontsize=13,
            pad=12,
        )
        ax.text(
            62, 5, text or "No corners", color="#111111", fontsize=9,
            bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "alpha": 0.9, "pad": 4},
        )

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], color=ROUTINE_COLORS[label], lw=3, label=label)
            for label in ROUTINE_ORDER
            if any(seq["routine_type"] == label for seq in sequences)
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=5,
    )
    save_fig(fig, output_path, tight=False)


def _plot_delivery_endpoints_by_side(sequences: list[dict[str, Any]], output_path: Path) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        "Barcelona corners - delivery endpoints by side",
        "Dot = first meaningful delivery endpoint   Dashed boxes = target-zone guide",
    )

    for ax, (side, subset) in zip(axes, _iter_side_subsets(sequences)):
        _draw_zone_boxes(ax, line_color=DARK_LINE_COLOR, text_color=DARK_LINE_COLOR)
        _draw_corner_marker(pitch, ax, side)
        for zone in ZONE_ORDER:
            pts = [
                _display_point((seq["delivery_end_x"], seq["delivery_end_y"]), side)
                for seq in subset
                if seq["delivery_zone"] == zone
            ]
            pts = [pt for pt in pts if pt is not None]
            if not pts:
                continue
            xs, ys = zip(*pts)
            pitch.scatter(
                xs, ys, ax=ax, s=58, color=ZONE_COLORS[zone],
                edgecolors="white", linewidth=0.55, alpha=0.9, label=zone,
            )
        ax.set_title(
            f"{_side_title(side)}  -  n = {len(subset)}",
            color="#111111",
            fontsize=13,
            pad=12,
        )

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=ZONE_COLORS[zone],
                   markeredgecolor="white", markersize=8, lw=0, label=zone)
            for zone in ZONE_ORDER
            if any(seq["delivery_zone"] == zone for seq in sequences)
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=4,
    )
    save_fig(fig, output_path, tight=False)


def _plot_first_touch_map(sequences: list[dict[str, Any]], output_path: Path) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        "Barcelona corners - first touch after the corner",
        "Dot = first touch location   Arrow = what Barcelona did next with that first touch",
    )

    for ax, (side, subset) in zip(axes, _iter_side_subsets(sequences)):
        _draw_corner_marker(pitch, ax, side)
        action_counter = Counter()
        for seq in subset:
            kind = seq["first_touch_kind"]
            start = _display_point((seq["first_touch_x"], seq["first_touch_y"]), side)
            end = _display_point((seq["first_touch_end_x"], seq["first_touch_end_y"]), side)
            if kind not in FIRST_TOUCH_COLORS or start is None:
                continue
            action_counter[kind] += 1
            color = FIRST_TOUCH_COLORS[kind]
            pitch.scatter([start[0]], [start[1]], ax=ax, s=64, color=color, edgecolors="white", linewidth=0.65, zorder=4)
            if end is not None:
                pitch.arrows(
                    start[0], start[1], end[0], end[1], ax=ax,
                    color=color, width=1.7, headwidth=4.5, headlength=4.5,
                    alpha=0.82, zorder=3,
                )
        ax.set_title(
            f"{_side_title(side)}  -  n = {len(subset)}",
            color="#111111",
            fontsize=13,
            pad=12,
        )
        summary = "   ".join(
            f"{label.lower()}s: {action_counter.get(label, 0)}"
            for label in ("Shot", "Pass", "Carry")
        )
        ax.text(
            62, 1.2, summary, color="#111111", fontsize=9,
            bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "alpha": 0.9, "pad": 3},
        )

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=FIRST_TOUCH_COLORS[label],
                   markeredgecolor="white", markersize=8, lw=0, label=label)
            for label in ("Shot", "Pass", "Carry")
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=4,
    )
    save_fig(fig, output_path, tight=False)


def _plot_shot_assist_map(sequences: list[dict[str, Any]], output_path: Path) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))

    _apply_dark_header(
        fig,
        "Barcelona corner sequences - last pass before shot",
        "Faded dot + arrow = last pass   Star = shot location   Colour = outcome",
    )

    for ax, (side, subset) in zip(axes, _iter_side_subsets(sequences)):
        _draw_corner_marker(pitch, ax, side)
        links = [link for seq in subset for link in seq["shot_links"]]
        counts = Counter(link["outcome"] for link in links)
        for link in links:
            color = SHOT_OUTCOME_COLORS[link["outcome"]]
            pass_start = _display_point(link["pass_start"], side)
            pass_end = _display_point(link["pass_end"], side)
            shot_loc = _display_point(link["shot_loc"], side)
            if pass_start is not None:
                pitch.scatter(
                    [pass_start[0]], [pass_start[1]], ax=ax,
                    s=28, color="#cfcfcf", edgecolors="white", linewidth=0.3, alpha=0.45, zorder=2,
                )
            if pass_start is not None and pass_end is not None:
                pitch.arrows(
                    pass_start[0], pass_start[1], pass_end[0], pass_end[1], ax=ax,
                    color=color, width=1.5, headwidth=4.2, headlength=4.2,
                    alpha=0.55, zorder=2,
                )
            if shot_loc is not None:
                pitch.scatter(
                    [shot_loc[0]], [shot_loc[1]], ax=ax, marker="*",
                    s=130, color=color, edgecolors="white", linewidth=0.8, zorder=4,
                )

        ax.set_title(
            f"{_side_title(side)}  -  n = {len(links)} shots",
            color="#111111",
            fontsize=13,
            pad=12,
        )
        summary = "   ".join(
            f"{label.lower()}: {counts.get(label, 0)}"
            for label in ("Goal", "Saved", "Other")
        )
        ax.text(
            62, 1.2, summary, color="#111111", fontsize=9,
            bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "alpha": 0.9, "pad": 3},
        )

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Goal"],
                   markeredgecolor="white", markersize=11, lw=0, label="Goal"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Saved"],
                   markeredgecolor="white", markersize=11, lw=0, label="Saved"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Other"],
                   markeredgecolor="white", markersize=11, lw=0, label="Off target / blocked"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#cfcfcf",
                   markeredgecolor="white", markersize=7, lw=0, alpha=0.45, label="Pass start"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=5,
    )
    save_fig(fig, output_path, tight=False)


def _plot_goal_sequences(sequences: list[dict[str, Any]], output_path: Path) -> None:
    goal_sequences = [seq for seq in sequences if seq["goal_actions"]]
    if not goal_sequences:
        return

    fig, axes, pitch = _dark_pitch_figure(len(goal_sequences), figsize=(7.6 * len(goal_sequences), 8))
    _apply_dark_header(
        fig,
        "Barcelona goals from corners - full sequence maps",
        "Blue = pass   Yellow = carry   Grey = intermediate contact   Red star = goal shot",
    )

    for ax, seq in zip(axes, goal_sequences):
        _draw_corner_marker(pitch, ax, seq["corner_side"])
        for action in seq["goal_actions"]:
            start = _display_point(action["start"], seq["corner_side"])
            end = _display_point(action["end"], seq["corner_side"])
            if start is None:
                continue
            type_name = action["type"]
            if type_name == "Pass":
                color = "#3b82f6"
                pitch.arrows(
                    start[0], start[1], end[0], end[1], ax=ax,
                    color=color, width=1.9, headwidth=4.8, headlength=4.8,
                    alpha=0.8, zorder=2,
                )
                pitch.scatter([start[0]], [start[1]], ax=ax, s=55, color=color, edgecolors="white", linewidth=0.5, zorder=3)
            elif type_name == "Carry":
                color = "#ffd43b"
                if end is not None:
                    pitch.arrows(
                        start[0], start[1], end[0], end[1], ax=ax,
                        color=color, width=1.9, headwidth=4.8, headlength=4.8,
                        alpha=0.8, zorder=2,
                    )
                pitch.scatter([start[0]], [start[1]], ax=ax, s=55, color=color, edgecolors="white", linewidth=0.5, zorder=3)
            elif type_name == "Shot":
                pitch.scatter(
                    [start[0]], [start[1]], ax=ax, marker="*",
                    s=170, color="#ff4d6d", edgecolors="white", linewidth=0.8, zorder=5,
                )
                if end is not None:
                    pitch.arrows(
                        start[0], start[1], end[0], end[1], ax=ax,
                        color="#ff4d6d", width=1.5, headwidth=4.5, headlength=4.5,
                        alpha=0.6, zorder=4,
                    )
            else:
                pitch.scatter([start[0]], [start[1]], ax=ax, s=42, color="#d9d9d9", edgecolors="white", linewidth=0.35, alpha=0.85, zorder=3)

        scorer = next((action["player"] for action in seq["goal_actions"] if action["is_goal"]), "Unknown")
        ax.set_title(
            f"{seq['match_label']}, {seq['minute']}' - {scorer}",
            color="#111111",
            fontsize=12,
            pad=12,
        )

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], color="#3b82f6", lw=3, label="Pass"),
            Line2D([0], [0], color="#ffd43b", lw=3, label="Carry"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#d9d9d9",
                   markeredgecolor="white", markersize=7, lw=0, label="Intermediate contact"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor="#ff4d6d",
                   markeredgecolor="white", markersize=12, lw=0, label="Goal shot"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=5,
    )
    save_fig(fig, output_path, tight=False)


def _dark_single_pitch() -> tuple[plt.Figure, plt.Axes, Pitch]:
    pitch = Pitch(
        pitch_type="statsbomb",
        half=True,
        pitch_color=DARK_PITCH_COLOR,
        line_color=DARK_LINE_COLOR,
        linewidth=1.8,
    )
    fig, ax = plt.subplots(figsize=(8.8, 8.2))
    fig.patch.set_facecolor(DARK_FIG_COLOR)
    ax.set_facecolor(DARK_FIG_COLOR)
    ax.grid(False)
    pitch.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.subplots_adjust(top=0.8, bottom=0.15)
    return fig, ax, pitch


def _single_pitch_title(fig: plt.Figure, title: str, subtitle: str = "") -> None:
    _apply_dark_header(fig, title, subtitle, title_y=0.975, subtitle_y=0.935, title_size=17, subtitle_size=11.0)


def _annotate_pitch_footer(ax: plt.Axes, text: str) -> None:
    ax.text(
        62, 1.2, text, color="#111111", fontsize=10,
        bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "alpha": 0.9, "pad": 3.2},
    )


def _plot_delivery_routes_side(
    sequences: list[dict[str, Any]],
    side: str,
    output_path: Path,
) -> None:
    subset = [seq for seq in sequences if seq["corner_side"] == side]
    fig, ax, pitch = _dark_single_pitch()
    _single_pitch_title(
        fig,
        f"Barcelona corners - first meaningful deliveries ({_side_label(side)})",
        "Arrow = delivery route   Dot = delivery endpoint   Colour = routine type",
    )
    _draw_corner_marker(pitch, ax, side)

    counts = Counter()
    for seq in subset:
        start = _display_point((seq["delivery_start_x"], seq["delivery_start_y"]), side)
        end = _display_point((seq["delivery_end_x"], seq["delivery_end_y"]), side)
        if start is None or end is None:
            continue
        color = ROUTINE_COLORS[seq["routine_type"]]
        counts[seq["routine_type"]] += 1
        pitch.arrows(
            start[0], start[1], end[0], end[1], ax=ax,
            color=color, width=1.8, headwidth=4.8, headlength=4.8,
            alpha=0.6, zorder=2,
        )
        pitch.scatter([end[0]], [end[1]], ax=ax, s=46, color=color, edgecolors="white", linewidth=0.55, zorder=3)

    ax.set_title(f"n = {len(subset)}", color="#111111", fontsize=13, pad=10)
    _annotate_pitch_footer(
        ax,
        "   ".join(f"{label}: {counts.get(label, 0)}" for label in ROUTINE_ORDER if counts.get(label, 0) > 0) or "No corners",
    )
    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], color=ROUTINE_COLORS[label], lw=3, label=label)
            for label in ROUTINE_ORDER if counts.get(label, 0) > 0
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick")
        ],
        ncol=3,
    )
    save_fig(fig, output_path, tight=False)


def _plot_delivery_endpoints_side(
    sequences: list[dict[str, Any]],
    side: str,
    output_path: Path,
) -> None:
    subset = [seq for seq in sequences if seq["corner_side"] == side]
    fig, ax, pitch = _dark_single_pitch()
    _single_pitch_title(
        fig,
        f"Barcelona corners - delivery endpoints ({_side_label(side)})",
        "Dot = first meaningful delivery endpoint   Dashed boxes = coded target zones",
    )
    _draw_zone_boxes(ax, line_color=DARK_LINE_COLOR, text_color=DARK_LINE_COLOR)
    _draw_corner_marker(pitch, ax, side)

    counts = Counter()
    for zone in ZONE_ORDER:
        pts = []
        for seq in subset:
            end = _display_point((seq["delivery_end_x"], seq["delivery_end_y"]), side)
            if seq["delivery_zone"] == zone and end is not None:
                pts.append(end)
        if not pts:
            continue
        counts[zone] = len(pts)
        xs, ys = zip(*pts)
        pitch.scatter(xs, ys, ax=ax, s=58, color=ZONE_COLORS[zone], edgecolors="white", linewidth=0.55, alpha=0.92)

    ax.set_title(f"n = {len(subset)}", color="#111111", fontsize=13, pad=10)
    _annotate_pitch_footer(
        ax,
        "   ".join(f"{zone}: {counts.get(zone, 0)}" for zone in ZONE_ORDER if counts.get(zone, 0) > 0) or "No deliveries",
    )
    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=ZONE_COLORS[zone],
                   markeredgecolor="white", markersize=8, lw=0, label=zone)
            for zone in ZONE_ORDER if counts.get(zone, 0) > 0
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick")
        ],
        ncol=3,
    )
    save_fig(fig, output_path, tight=False)


def _plot_first_touch_side(
    sequences: list[dict[str, Any]],
    side: str,
    output_path: Path,
) -> None:
    subset = [seq for seq in sequences if seq["corner_side"] == side]
    fig, ax, pitch = _dark_single_pitch()
    _single_pitch_title(
        fig,
        f"Barcelona corners - first touch after the corner ({_side_label(side)})",
        "Dot = first touch location   Arrow = what Barcelona did next with that first touch",
    )
    _draw_corner_marker(pitch, ax, side)

    action_counter = Counter()
    for seq in subset:
        kind = seq["first_touch_kind"]
        if kind not in FIRST_TOUCH_COLORS:
            continue
        start = _display_point((seq["first_touch_x"], seq["first_touch_y"]), side)
        end = _display_point((seq["first_touch_end_x"], seq["first_touch_end_y"]), side)
        if start is None:
            continue
        action_counter[kind] += 1
        color = FIRST_TOUCH_COLORS[kind]
        pitch.scatter([start[0]], [start[1]], ax=ax, s=66, color=color, edgecolors="white", linewidth=0.65, zorder=4)
        if end is not None:
            pitch.arrows(
                start[0], start[1], end[0], end[1], ax=ax,
                color=color, width=1.8, headwidth=4.8, headlength=4.8,
                alpha=0.82, zorder=3,
            )

    ax.set_title(f"n = {len(subset)}", color="#111111", fontsize=13, pad=10)
    _annotate_pitch_footer(
        ax,
        f"shots: {action_counter.get('Shot', 0)}   passes: {action_counter.get('Pass', 0)}   carries: {action_counter.get('Carry', 0)}",
    )
    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=FIRST_TOUCH_COLORS[label],
                   markeredgecolor="white", markersize=8, lw=0, label=label)
            for label in ("Shot", "Pass", "Carry")
        ] + [
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100",
                   markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick")
        ],
        ncol=4,
    )
    save_fig(fig, output_path, tight=False)


def _plot_first_touch_heatmap_side(
    sequences: list[dict[str, Any]],
    side: str,
    output_path: Path,
) -> None:
    subset = [seq for seq in sequences if seq["corner_side"] == side and seq["first_touch_x"] is not None]
    pitch = Pitch(pitch_type="statsbomb", half=True, pitch_color="white", line_color="#c7d5cc")
    fig, ax = pitch.draw(figsize=(8.6, 7.6))
    xs, ys = [], []
    for seq in subset:
        pt = _display_point((seq["first_touch_x"], seq["first_touch_y"]), side)
        if pt is None:
            continue
        xs.append(pt[0])
        ys.append(pt[1])
    if xs:
        bin_stat = pitch.bin_statistic(xs, ys, statistic="count", bins=(8, 8))
        pitch.heatmap(bin_stat, ax=ax, cmap="Reds", edgecolors="#f0f0f0", alpha=0.75)
        pitch.label_heatmap(
            bin_stat,
            color="#222222",
            fontsize=10,
            ax=ax,
            str_format="{:.0f}",
            exclude_zeros=True,
        )
        pitch.scatter(xs, ys, ax=ax, s=18, color=FOCUS_COLOR, edgecolors="white", linewidth=0.35, alpha=0.8)
    ax.set_title(
        f"Barcelona corners - first-touch heatmap ({_side_label(side)})\nCount of first Barcelona touches after the corner",
        fontsize=15, fontweight="bold", pad=12,
    )
    save_fig(fig, output_path, tight=False)


def _plot_shot_assist_side(
    sequences: list[dict[str, Any]],
    side: str,
    output_path: Path,
) -> None:
    subset = [seq for seq in sequences if seq["corner_side"] == side]
    fig, ax, pitch = _dark_single_pitch()
    _single_pitch_title(
        fig,
        f"Barcelona corner sequences - last pass before shot ({_side_label(side)})",
        "Faded dot + arrow = last pass   Star = shot location   Colour = shot outcome",
    )
    _draw_corner_marker(pitch, ax, side)

    links = [link for seq in subset for link in seq["shot_links"]]
    counts = Counter(link["outcome"] for link in links)
    for link in links:
        color = SHOT_OUTCOME_COLORS[link["outcome"]]
        pass_start = _display_point(link["pass_start"], side)
        pass_end = _display_point(link["pass_end"], side)
        shot_loc = _display_point(link["shot_loc"], side)
        if pass_start is not None:
            pitch.scatter([pass_start[0]], [pass_start[1]], ax=ax, s=28, color="#cfcfcf", edgecolors="white", linewidth=0.3, alpha=0.45, zorder=2)
        if pass_start is not None and pass_end is not None:
            pitch.arrows(
                pass_start[0], pass_start[1], pass_end[0], pass_end[1], ax=ax,
                color=color, width=1.6, headwidth=4.2, headlength=4.2,
                alpha=0.55, zorder=2,
            )
        if shot_loc is not None:
            pitch.scatter([shot_loc[0]], [shot_loc[1]], ax=ax, marker="*", s=138, color=color, edgecolors="white", linewidth=0.8, zorder=4)

    ax.set_title(f"n = {len(links)} shots", color="#111111", fontsize=13, pad=10)
    _annotate_pitch_footer(
        ax,
        f"goals: {counts.get('Goal', 0)}   saved: {counts.get('Saved', 0)}   other: {counts.get('Other', 0)}",
    )
    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Goal"], markeredgecolor="white", markersize=11, lw=0, label="Goal"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Saved"], markeredgecolor="white", markersize=11, lw=0, label="Saved"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Other"], markeredgecolor="white", markersize=11, lw=0, label="Off target / blocked"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#cfcfcf", markeredgecolor="white", markersize=7, lw=0, alpha=0.45, label="Pass start"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100", markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=3,
    )
    save_fig(fig, output_path, tight=False)


def _plot_goal_sequence_single(sequence: dict[str, Any], output_path: Path) -> None:
    fig, ax, pitch = _dark_single_pitch()
    scorer = next((action["player"] for action in sequence["goal_actions"] if action["is_goal"]), "Unknown")
    fig.text(0.5, 0.975, "Barcelona goal from corner", ha="center", va="top", color="#111111", fontsize=18, fontweight="bold")
    fig.text(0.5, 0.945, f"{sequence['match_label']}, {sequence['minute']}'", ha="center", va="top", color="#111111", fontsize=16, fontweight="bold")
    fig.text(
        0.5,
        0.918,
        f"Scorer: {scorer}   Blue = pass   Yellow = carry   Red star = goal shot",
        ha="center",
        va="top",
        color="#333333",
        fontsize=10.4,
    )
    _draw_corner_marker(pitch, ax, sequence["corner_side"])

    for action in sequence["goal_actions"]:
        start = _display_point(action["start"], sequence["corner_side"])
        end = _display_point(action["end"], sequence["corner_side"])
        if start is None:
            continue
        type_name = action["type"]
        if type_name == "Pass":
            color = "#3b82f6"
            if end is not None:
                pitch.arrows(start[0], start[1], end[0], end[1], ax=ax, color=color, width=1.9, headwidth=4.8, headlength=4.8, alpha=0.82, zorder=2)
            pitch.scatter([start[0]], [start[1]], ax=ax, s=58, color=color, edgecolors="white", linewidth=0.5, zorder=3)
        elif type_name == "Carry":
            color = "#ffd43b"
            if end is not None:
                pitch.arrows(start[0], start[1], end[0], end[1], ax=ax, color=color, width=1.9, headwidth=4.8, headlength=4.8, alpha=0.82, zorder=2)
            pitch.scatter([start[0]], [start[1]], ax=ax, s=58, color=color, edgecolors="white", linewidth=0.5, zorder=3)
        elif type_name == "Shot":
            pitch.scatter([start[0]], [start[1]], ax=ax, marker="*", s=178, color="#ff4d6d", edgecolors="white", linewidth=0.8, zorder=5)
            if end is not None:
                pitch.arrows(start[0], start[1], end[0], end[1], ax=ax, color="#ff4d6d", width=1.5, headwidth=4.5, headlength=4.5, alpha=0.6, zorder=4)
        else:
            pitch.scatter([start[0]], [start[1]], ax=ax, s=42, color="#d9d9d9", edgecolors="white", linewidth=0.35, alpha=0.85, zorder=3)

    _add_dark_legend(
        fig,
        [
            Line2D([0], [0], color="#3b82f6", lw=3, label="Pass"),
            Line2D([0], [0], color="#ffd43b", lw=3, label="Carry"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#d9d9d9", markeredgecolor="white", markersize=7, lw=0, label="Intermediate contact"),
            Line2D([0], [0], marker="*", color="w", markerfacecolor="#ff4d6d", markeredgecolor="white", markersize=12, lw=0, label="Goal shot"),
            Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd100", markeredgecolor=DARK_FIG_COLOR, markersize=11, lw=0, label="Corner kick"),
        ],
        ncol=3,
    )
    save_fig(fig, output_path, tight=False)


def _plot_role_profile(sequences: list[dict[str, Any]], output_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 7))
    fig.subplots_adjust(top=0.84, bottom=0.1, wspace=0.28)
    specs = [
        ("corner_taker", "Corner takers"),
        ("delivery_receiver", "Delivery receivers"),
        ("first_shot_player", "First-shot takers"),
    ]

    for ax, (key, title) in zip(axes, specs):
        counter = Counter(s[key] for s in sequences if s[key] not in ("Unknown", "No shot"))
        items = counter.most_common(8)
        if not items:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            continue
        names = [name for name, _ in items][::-1]
        vals = [val for _, val in items][::-1]
        colors = [FOCUS_COLOR if i == len(vals) - 1 else AVG_COLOR for i in range(len(vals))]
        ax.barh(names, vals, color=colors, alpha=0.9)
        ax.set_title(title)
        ax.set_xlabel("Count")

    _apply_light_header(
        fig,
        "Barcelona offensive corners - role distribution",
        "Who takes corners, receives the first meaningful delivery, and shoots first",
    )
    save_fig(fig, output_path, tight=False)


def _plot_sequence_value(sequences: list[dict[str, Any]], output_path: Path) -> None:
    labels = [label for label in ROUTINE_ORDER if any(s["routine_type"] == label for s in sequences)]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5))
    fig.subplots_adjust(top=0.82, bottom=0.12, wspace=0.28)
    ax_phase, ax_xg, ax_obv = axes

    phase_order = ["Immediate shot", "Second-phase shot", "No shot"]
    phase_colors = {
        "Immediate shot": FOCUS_COLOR,
        "Second-phase shot": POSITIVE_COLOR,
        "No shot": NEUTRAL_COLOR,
    }

    bottom = np.zeros(len(labels))
    for phase in phase_order:
        vals = []
        for label in labels:
            subset = [s for s in sequences if s["routine_type"] == label]
            share = np.mean([1.0 if s["shot_phase"] == phase else 0.0 for s in subset]) if subset else 0.0
            vals.append(share)
        ax_phase.bar(labels, vals, bottom=bottom, color=phase_colors[phase], label=phase)
        bottom += np.array(vals)
    ax_phase.set_title("Sequence outcome")
    ax_phase.set_ylabel("Share of corners")
    ax_phase.tick_params(axis="x", rotation=20)
    ax_phase.legend(fontsize=8)

    first_vals = []
    added_vals = []
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        first_vals.append(np.mean([s["first_shot_xg"] for s in subset]) if subset else 0.0)
        added_vals.append(np.mean([s["added_xg"] for s in subset]) if subset else 0.0)
    ax_xg.bar(labels, first_vals, color=FOCUS_COLOR, label="First-shot xG")
    ax_xg.bar(labels, added_vals, bottom=first_vals, color=POSITIVE_COLOR, label="Added xG after first shot")
    ax_xg.set_title("First action vs recycled value")
    ax_xg.set_ylabel("xG / corner")
    ax_xg.tick_params(axis="x", rotation=20)
    ax_xg.legend(fontsize=8)

    obv_vals = []
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        obv_vals.append(np.mean([s["total_obv"] for s in subset]) if subset else 0.0)
    ax_obv.bar(labels, obv_vals, color=[ROUTINE_COLORS[label] for label in labels])
    ax_obv.axhline(0.0, color=NEUTRAL_COLOR, lw=1.0)
    ax_obv.set_title("Average OBV added per sequence")
    ax_obv.set_ylabel("OBV")
    ax_obv.tick_params(axis="x", rotation=20)

    _apply_light_header(
        fig,
        "Barcelona offensive corners - sequence value",
        "Immediate shots, recycled value, and OBV by routine",
    )
    save_fig(fig, output_path, tight=False)


def _plot_matchup_adaptation(sequences: list[dict[str, Any]], output_path: Path) -> None:
    by_match: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seq in sequences:
        by_match[seq["match_id"]].append(seq)

    rows: list[dict[str, Any]] = []
    for match_id, subset in by_match.items():
        first = subset[0]
        gap = first["height_gap"]
        if gap is None:
            continue
        n = len(subset)
        rows.append({
            "label": first["match_label"],
            "height_gap": gap,
            "short_share": sum(1 for s in subset if s["routine_type"] == "Short corner") / n,
            "far_post_share": sum(1 for s in subset if s["delivery_zone"] == "Far post") / n,
            "second_phase_share": sum(1 for s in subset if s["shot_phase"] == "Second-phase shot") / n,
            "xg_per_corner": sum(s["total_xg"] for s in subset) / n,
        })

    if not rows:
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.subplots_adjust(top=0.88, bottom=0.08, hspace=0.32, wspace=0.24)
    metrics = [
        ("short_share", "Short-corner share"),
        ("far_post_share", "Far-post share"),
        ("second_phase_share", "Second-phase shot share"),
        ("xg_per_corner", "xG per corner"),
    ]

    x = np.array([row["height_gap"] for row in rows])
    for ax, (metric, title) in zip(axes.flat, metrics):
        y = np.array([row[metric] for row in rows])
        ax.scatter(x, y, color=FOCUS_COLOR, s=65, alpha=0.85)
        if len(rows) >= 2 and np.ptp(x) > 0:
            coef = np.polyfit(x, y, deg=1)
            xs = np.linspace(float(np.min(x)), float(np.max(x)), 50)
            ax.plot(xs, coef[0] * xs + coef[1], color=AVG_COLOR, lw=1.8)
        for row in rows:
            ax.text(row["height_gap"] + 0.03, row[metric] + 0.003, _abbr(row["label"]), fontsize=8)
        ax.axvline(0.0, color=NEUTRAL_COLOR, lw=1.0, ls="--")
        ax.set_title(title)
        ax.set_xlabel("Opponent top-6 height minus Barcelona top-6 height (cm)")
        ax.set_ylabel(title)

    _apply_light_header(
        fig,
        "Barcelona offensive corners - matchup adaptation",
        "Routine choices against taller and smaller opponents",
    )
    save_fig(fig, output_path, tight=False)


def _plot_single_bar(
    labels: list[str],
    values: list[float],
    *,
    title: str,
    ylabel: str,
    output_path: Path,
    colors: list[str] | None = None,
    rotation: int = 20,
    ylim_max: float | None = None,
    value_fmt: str = ".2f",
) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    if colors is None:
        colors = [FOCUS_COLOR] * len(labels)
    bars = ax.bar(labels, values, color=colors, edgecolor="white", linewidth=0.6)
    ymax = max(values) if values else 1.0
    ylim = ylim_max if ylim_max is not None else ymax * 1.18 if ymax > 0 else 1.0
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(ylim, 1.0) * 0.015, f"{val:{value_fmt}}", ha="center", va="bottom", fontsize=10)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, ylim)
    ax.tick_params(axis="x", rotation=rotation, labelsize=10)
    save_fig(fig, output_path)


def _plot_stacked_share_chart(
    labels: list[str],
    value_map: dict[str, list[float]],
    order: list[str],
    *,
    colors: dict[str, str],
    title: str,
    ylabel: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = np.zeros(len(labels))
    for key in order:
        vals = value_map.get(key, [])
        if not vals or not any(vals):
            continue
        ax.bar(labels, vals, bottom=bottom, color=colors[key], label=key, edgecolor="white", linewidth=0.5)
        bottom += np.array(vals)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1.02)
    ax.tick_params(axis="x", rotation=20, labelsize=10)
    ax.legend(fontsize=9, loc="upper right")
    save_fig(fig, output_path)


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
        save_fig(fig, output_path)
        return
    names = [name for name, _ in items][::-1]
    vals = [val for _, val in items][::-1]
    bars = ax.barh(names, vals, color=FOCUS_COLOR, edgecolor="white", linewidth=0.6)
    xmax = max(vals) if vals else 1
    for bar, val in zip(bars, vals):
        ax.text(bar.get_width() + max(xmax, 1) * 0.02, bar.get_y() + bar.get_height() / 2, str(val), va="center", fontsize=10)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, xmax * 1.18 if xmax > 0 else 1)
    save_fig(fig, output_path)


def _plot_matchup_metric_single(
    rows: list[dict[str, Any]],
    metric: str,
    title: str,
    output_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8.4, 6.2))
    x = np.array([row["height_gap"] for row in rows])
    y = np.array([row[metric] for row in rows])
    ax.scatter(x, y, color=FOCUS_COLOR, s=68, alpha=0.85)
    if len(rows) >= 2 and np.ptp(x) > 0:
        coef = np.polyfit(x, y, deg=1)
        xs = np.linspace(float(np.min(x)), float(np.max(x)), 50)
        ax.plot(xs, coef[0] * xs + coef[1], color=AVG_COLOR, lw=2)
    for row in rows:
        ax.text(row["height_gap"] + 0.03, row[metric] + 0.003, _abbr(row["label"]), fontsize=8.5)
    ax.axvline(0.0, color=NEUTRAL_COLOR, lw=1.0, ls="--")
    ax.set_title(title, fontsize=15, fontweight="bold", pad=10)
    ax.set_xlabel("Opponent top-6 height minus Barcelona top-6 height (cm)")
    ax.set_ylabel(title)
    save_fig(fig, output_path)


def _write_sequence_table(sequences: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "match_id",
        "match_label",
        "opponent",
        "minute",
        "corner_taker",
        "corner_side",
        "routine_type",
        "corner_length",
        "corner_recipient",
        "delivery_receiver",
        "delivery_zone",
        "shot_phase",
        "shot_generated",
        "first_shot_player",
        "first_shot_xg",
        "total_xg",
        "added_xg",
        "shots_in_sequence",
        "goals_in_sequence",
        "total_obv",
        "team_top6_height",
        "opponent_top6_height",
        "height_gap",
        "corner_start_x",
        "corner_start_y",
        "corner_end_x",
        "corner_end_y",
        "delivery_start_x",
        "delivery_start_y",
        "delivery_end_x",
        "delivery_end_y",
        "first_shot_x",
        "first_shot_y",
        "first_touch_kind",
        "first_touch_player",
        "first_touch_x",
        "first_touch_y",
        "first_touch_end_x",
        "first_touch_end_y",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sequences)


def _generate_single_panel_outputs(sequences: list[dict[str, Any]], output_dir: Path) -> None:
    labels = [label for label in ROUTINE_ORDER if any(s["routine_type"] == label for s in sequences)]
    routine_counts = [sum(1 for s in sequences if s["routine_type"] == label) for label in labels]
    routine_colors = [ROUTINE_COLORS[label] for label in labels]
    _plot_single_bar(
        labels,
        routine_counts,
        title="Barcelona corners - routine mix",
        ylabel="Count",
        output_path=output_dir / "routine_mix_single.png",
        colors=routine_colors,
        value_fmt=".0f",
    )

    shot_rates = []
    total_xg = []
    zone_shares = defaultdict(list)
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        shot_rates.append(np.mean([float(s["shot_generated"]) for s in subset]) if subset else 0.0)
        total_xg.append(np.mean([s["total_xg"] for s in subset]) if subset else 0.0)
        n = len(subset) or 1
        counter = Counter(s["delivery_zone"] for s in subset)
        for zone in ZONE_ORDER:
            zone_shares[zone].append(counter.get(zone, 0) / n)

    _plot_single_bar(
        labels,
        shot_rates,
        title="Barcelona corners - shot generation rate by routine",
        ylabel="Share of corners with a shot",
        output_path=output_dir / "shot_generation_rate_single.png",
        colors=routine_colors,
        ylim_max=max(0.55, max(shot_rates, default=0.0) * 1.2),
        value_fmt=".2f",
    )
    _plot_single_bar(
        labels,
        total_xg,
        title="Barcelona corners - average xG by routine",
        ylabel="xG per corner",
        output_path=output_dir / "xg_by_routine_single.png",
        colors=routine_colors,
        value_fmt=".3f",
    )
    _plot_stacked_share_chart(
        labels,
        zone_shares,
        ZONE_ORDER,
        colors=ZONE_COLORS,
        title="Barcelona corners - target-zone share by routine",
        ylabel="Share of sequences",
        output_path=output_dir / "target_zone_share_by_routine_single.png",
    )

    _plot_horizontal_counts(
        Counter(s["corner_taker"] for s in sequences if s["corner_taker"] not in ("Unknown", "")).most_common(8),
        title="Barcelona corners - top takers",
        xlabel="Corners taken",
        output_path=output_dir / "corner_takers_single.png",
    )
    _plot_horizontal_counts(
        Counter(s["delivery_receiver"] for s in sequences if s["delivery_receiver"] not in ("Unknown", "")).most_common(8),
        title="Barcelona corners - top first receivers",
        xlabel="Deliveries received",
        output_path=output_dir / "delivery_receivers_single.png",
    )
    _plot_horizontal_counts(
        Counter(s["first_shot_player"] for s in sequences if s["first_shot_player"] not in ("No shot", "")).most_common(8),
        title="Barcelona corners - top first-shot players",
        xlabel="First shots",
        output_path=output_dir / "first_shot_players_single.png",
    )

    phase_order = ["Immediate shot", "Second-phase shot", "No shot"]
    phase_colors = {"Immediate shot": FOCUS_COLOR, "Second-phase shot": POSITIVE_COLOR, "No shot": NEUTRAL_COLOR}
    phase_vals = {phase: [] for phase in phase_order}
    first_vals = []
    added_vals = []
    obv_vals = []
    for label in labels:
        subset = [s for s in sequences if s["routine_type"] == label]
        for phase in phase_order:
            phase_vals[phase].append(np.mean([1.0 if s["shot_phase"] == phase else 0.0 for s in subset]) if subset else 0.0)
        first_vals.append(np.mean([s["first_shot_xg"] for s in subset]) if subset else 0.0)
        added_vals.append(np.mean([s["added_xg"] for s in subset]) if subset else 0.0)
        obv_vals.append(np.mean([s["total_obv"] for s in subset]) if subset else 0.0)

    _plot_stacked_share_chart(
        labels,
        phase_vals,
        phase_order,
        colors=phase_colors,
        title="Barcelona corners - sequence outcome by routine",
        ylabel="Share of corners",
        output_path=output_dir / "sequence_outcome_single.png",
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(labels, first_vals, color=FOCUS_COLOR, label="First-shot xG", edgecolor="white", linewidth=0.6)
    ax.bar(labels, added_vals, bottom=first_vals, color=POSITIVE_COLOR, label="Added xG after first shot", edgecolor="white", linewidth=0.6)
    ax.set_title("Barcelona corners - first action vs recycled value", fontsize=15, fontweight="bold", pad=10)
    ax.set_ylabel("xG per corner")
    ax.tick_params(axis="x", rotation=20, labelsize=10)
    ax.legend(fontsize=9)
    save_fig(fig, output_dir / "first_action_vs_recycled_value_single.png")

    _plot_single_bar(
        labels,
        obv_vals,
        title="Barcelona corners - average OBV by routine",
        ylabel="OBV per corner",
        output_path=output_dir / "obv_by_routine_single.png",
        colors=routine_colors,
        value_fmt=".3f",
    )

    by_match: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seq in sequences:
        by_match[seq["match_id"]].append(seq)

    rows: list[dict[str, Any]] = []
    for _, subset in by_match.items():
        first = subset[0]
        gap = first["height_gap"]
        if gap is None:
            continue
        n = len(subset)
        rows.append({
            "label": first["match_label"],
            "height_gap": gap,
            "short_share": sum(1 for s in subset if s["routine_type"] == "Short corner") / n,
            "far_post_share": sum(1 for s in subset if s["delivery_zone"] == "Far post") / n,
            "second_phase_share": sum(1 for s in subset if s["shot_phase"] == "Second-phase shot") / n,
            "xg_per_corner": sum(s["total_xg"] for s in subset) / n,
        })

    if rows:
        _plot_matchup_metric_single(rows, "short_share", "Short-corner share", output_dir / "matchup_short_corner_share_single.png")
        _plot_matchup_metric_single(rows, "far_post_share", "Far-post share", output_dir / "matchup_far_post_share_single.png")
        _plot_matchup_metric_single(rows, "second_phase_share", "Second-phase shot share", output_dir / "matchup_second_phase_share_single.png")
        _plot_matchup_metric_single(rows, "xg_per_corner", "xG per corner", output_dir / "matchup_xg_per_corner_single.png")


def run(
    team: str = TEAM,
    data_dir: Path = DATA,
    output_dir: Path | None = None,
) -> None:
    if output_dir is None:
        output_dir = ASSETS_ROOT

    apply_theme()

    print("Collecting Barcelona attacking corner sequences...")
    sequences = _collect(team, data_dir)
    if not sequences:
        print(f"No offensive corners found for {team} in {data_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"  {len(sequences)} corner sequences found")

    _write_sequence_table(sequences, output_dir / "barcelona_corner_sequences.csv")
    _plot_routine_profile(sequences, output_dir / "routine_profile.png")
    _plot_spatial_profile(sequences, output_dir / "spatial_profile.png")
    _plot_delivery_routes_by_side(sequences, output_dir / "delivery_routes_by_side.png")
    _plot_delivery_endpoints_by_side(sequences, output_dir / "delivery_endpoints_by_side.png")
    _plot_first_touch_map(sequences, output_dir / "corner_first_touch_map.png")
    _plot_shot_assist_map(sequences, output_dir / "shot_assist_after_corner_map.png")
    _plot_goal_sequences(sequences, output_dir / "goal_sequences_from_corners.png")
    _plot_role_profile(sequences, output_dir / "role_profile.png")
    _plot_sequence_value(sequences, output_dir / "sequence_value.png")
    _plot_matchup_adaptation(sequences, output_dir / "matchup_adaptation.png")
    _generate_single_panel_outputs(sequences, output_dir)

    for side in ("bottom", "top"):
        slug = _side_slug(side)
        _plot_delivery_routes_side(sequences, side, output_dir / f"delivery_routes_{slug}.png")
        _plot_delivery_endpoints_side(sequences, side, output_dir / f"delivery_endpoints_{slug}.png")
        _plot_first_touch_side(sequences, side, output_dir / f"corner_first_touch_{slug}.png")
        _plot_first_touch_heatmap_side(sequences, side, output_dir / f"corner_first_touch_heatmap_{slug}.png")
        _plot_shot_assist_side(sequences, side, output_dir / f"shot_assist_after_corner_{slug}.png")

    goal_sequences = [seq for seq in sequences if seq["goal_actions"]]
    for idx, seq in enumerate(goal_sequences, start=1):
        _plot_goal_sequence_single(
            seq,
            output_dir / f"goal_sequence_{idx:02d}_{seq['match_id']}_{seq['minute']}.png",
        )

    print(f"Done - outputs saved to {output_dir}/")


if __name__ == "__main__":
    run()
