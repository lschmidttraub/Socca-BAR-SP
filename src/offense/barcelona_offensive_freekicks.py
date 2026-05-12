"""Barcelona offensive free-kick analysis.

Mirrors the corner analysis in barcelona_offensive_corners.py for attacking
free kicks, covering all planned analyses from analyses/offense.md:

1. Routine profile (type mix, shot rate, xG, target zones)
2. Spatial profile (delivery routes, endpoints, shot locations)
3. Player roles (takers, shooters/receivers)
4. First-touch map after the FK
5. Shot assist map (last pass before shot)
6. Goal sequence maps (incl. direct FK goal vs Copenhagen)
7. Direct free-kick effectiveness (shot locations + outcomes)
8. OBV analysis by distance zone ("dead zone" vs direct-shot range)

Outputs are written to ``assets/offensive_freekicks/``.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from mplsoccer import Pitch


def _find_project_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError(f"Could not locate project root from {start}")


PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stats import filters as f
from stats.data import iter_matches
from stats.viz.style import AVG_COLOR, FOCUS_COLOR, NEUTRAL_COLOR, POSITIVE_COLOR, apply_theme, save_fig
from stats.analyses.setpiece_maps import _team_in_match

ASSETS_ROOT = PROJECT_ROOT / "assets" / "offensive_freekicks"
DATA = PROJECT_ROOT / "data" / "statsbomb"

TEAM = "Barcelona"
SHORT_FK_MAX_LEN = 12.0
SEQUENCE_MAX_SECONDS = 20.0
ATTACKING_HALF_X = 60.0
DEAD_ZONE_X_MAX = 92.0   # FKs with x < this are in the "dead zone" (too far to shoot directly)

ROUTINE_ORDER = ["Direct shot", "Short FK", "Cross into box", "Other indirect"]

ROUTINE_COLORS = {
    "Direct shot":   FOCUS_COLOR,
    "Short FK":      AVG_COLOR,
    "Cross into box": "#f28e2b",
    "Other indirect": "#8c6bb1",
}

ZONE_ORDER = ["Near post", "Central six-yard", "Far post", "Penalty spot", "Edge of box", "Wide recycle"]

ZONE_COLORS = {
    "Near post":        "#d73027",
    "Central six-yard": "#fc8d59",
    "Far post":         "#4575b4",
    "Penalty spot":     "#66bd63",
    "Edge of box":      "#984ea3",
    "Wide recycle":     "#878787",
}

FIRST_TOUCH_COLORS = {"Shot": "#ff4d6d", "Pass": "#3b82f6", "Carry": "#ffd43b"}

SHOT_OUTCOME_COLORS = {"Goal": "#ff4d6d", "Saved": "#ffb000", "Other": "#7aa6ff"}

DARK_FIG_COLOR   = "white"
DARK_PITCH_COLOR = "white"
DARK_LINE_COLOR  = "#c7d5cc"


# ── Helpers shared with corner script ────────────────────────────────────────

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
    return x, (80.0 - y) if flip_y else y


def _clip_to_pitch(loc: tuple[float, float] | None) -> tuple[float, float] | None:
    if loc is None:
        return None
    x, y = loc
    return max(60.0, min(120.0, x)), max(0.0, min(80.0, y))


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


def _event_end_location(event: dict, flip_y: bool) -> tuple[float, float] | None:
    end = None
    if f.is_pass(event):
        end = event.get("pass", {}).get("end_location")
    elif _is_carry(event):
        end = event.get("carry", {}).get("end_location")
    elif f.is_shot(event):
        end = event.get("shot", {}).get("end_location")
    return _clip_to_pitch(_flip_location(end, flip_y))


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


def _team_label(row: dict, team: str) -> str:
    home, away = row.get("home", "").strip(), row.get("away", "").strip()
    if team == home:
        return away
    if team == away:
        return home
    return away if team in home else home


def _shot_outcome_bucket(shot: dict) -> str:
    if f.is_goal(shot):
        return "Goal"
    outcome = shot.get("shot", {}).get("outcome", {}).get("name", "")
    return "Saved" if "Saved" in outcome else "Other"


def _apply_dark_header(fig, title, subtitle=None, *, title_y=0.975, subtitle_y=0.935, title_size=18, subtitle_size=11.0):
    fig.text(0.5, title_y, title, ha="center", va="top", color="#111111", fontsize=title_size, fontweight="bold")
    if subtitle:
        fig.text(0.5, subtitle_y, subtitle, ha="center", va="top", color="#333333", fontsize=subtitle_size)


def _apply_light_header(fig, title, subtitle=None, *, title_y=0.98, subtitle_y=0.945, title_size=16, subtitle_size=11.0):
    fig.text(0.5, title_y, title, ha="center", va="top", color="#111111", fontsize=title_size, fontweight="bold")
    if subtitle:
        fig.text(0.5, subtitle_y, subtitle, ha="center", va="top", color="#333333", fontsize=subtitle_size)


def _add_dark_legend(fig, handles, ncol=4):
    legend = fig.legend(handles=handles, loc="lower center", ncol=ncol, frameon=True, bbox_to_anchor=(0.5, 0.02), fontsize=10)
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("#cccccc")
    for text in legend.get_texts():
        text.set_color("#111111")


def _dark_pitch_figure(ncols: int, *, figsize: tuple[float, float]):
    pitch = Pitch(pitch_type="statsbomb", half=True, pitch_color=DARK_PITCH_COLOR,
                  line_color=DARK_LINE_COLOR, linewidth=1.7)
    fig, axes = plt.subplots(1, ncols, figsize=figsize)
    axes = [axes] if ncols == 1 else list(axes)
    fig.patch.set_facecolor(DARK_FIG_COLOR)
    for ax in axes:
        ax.set_facecolor(DARK_FIG_COLOR)
        ax.grid(False)
        pitch.draw(ax=ax)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.subplots_adjust(top=0.8, bottom=0.14, wspace=0.22)
    return fig, axes, pitch


def _dark_single_pitch():
    pitch = Pitch(pitch_type="statsbomb", half=True, pitch_color=DARK_PITCH_COLOR,
                  line_color=DARK_LINE_COLOR, linewidth=1.8)
    fig, ax = plt.subplots(figsize=(8.8, 8.2))
    fig.patch.set_facecolor(DARK_FIG_COLOR)
    ax.set_facecolor(DARK_FIG_COLOR)
    ax.grid(False)
    pitch.draw(ax=ax)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.subplots_adjust(top=0.8, bottom=0.15)
    return fig, ax, pitch


def _annotate_pitch_footer(ax, text):
    ax.text(62, 1.2, text, color="#111111", fontsize=9,
            bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "alpha": 0.9, "pad": 3})


def _draw_zone_boxes(ax, *, line_color=NEUTRAL_COLOR):
    boxes = [
        (114, 0, 6, 33, "Near post"),
        (114, 33, 6, 14, "Central six-yard"),
        (114, 47, 6, 33, "Far post"),
        (102, 28, 12, 24, "Penalty spot"),
        (96, 18, 6, 44, "Edge"),
    ]
    for x, y, w, h, _ in boxes:
        ax.add_patch(Rectangle((x, y), w, h, fill=False, lw=1.2, ls="--", ec=line_color, alpha=0.65))


# ── FK-specific helpers ───────────────────────────────────────────────────────

def _is_fk_event(event: dict) -> bool:
    return f.is_fk_pass(event) or f.is_fk_shot(event)


def _fk_routine_type(event: dict) -> str:
    if f.is_fk_shot(event):
        return "Direct shot"
    length = float(event.get("pass", {}).get("length", 0.0) or 0.0)
    if length <= SHORT_FK_MAX_LEN:
        return "Short FK"
    end = event.get("pass", {}).get("end_location")
    if end and end[0] >= 102 and 18 <= end[1] <= 62:
        return "Cross into box"
    return "Other indirect"


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


def _meaningful_fk_delivery(sequence: list[dict], team_sb: str, routine: str) -> dict | None:
    """Return the primary delivery event for the FK sequence."""
    fk = sequence[0]
    if routine == "Direct shot":
        return fk
    if routine != "Short FK":
        return fk
    # For short FKs, find the next pass/shot that enters the box or covers real ground
    for event in sequence[1:]:
        if not f.by_team(event, team_sb):
            continue
        if f.is_shot(event):
            return event
        if not f.is_pass(event):
            continue
        end = event.get("pass", {}).get("end_location")
        loc = event.get("location")
        if end and end[0] >= 96:
            return event
        if loc and float(event.get("pass", {}).get("length", 0.0) or 0.0) >= 12:
            return event
    return fk


def _shot_phase(sequence: list[dict], team_sb: str) -> tuple[str, dict | None]:
    t0 = _event_time_seconds(sequence[0])
    action_index = 0
    for event in sequence[1:]:
        if not f.by_team(event, team_sb):
            continue
        if f.is_pass(event) or f.is_shot(event):
            action_index += 1
        if not f.is_shot(event):
            continue
        dt = _event_time_seconds(event) - t0
        if action_index <= 2 and dt <= 6.0:
            return "Immediate shot", event
        return "Second-phase shot", event
    # Direct FK shots are immediate by definition
    if f.is_fk_shot(sequence[0]) and f.by_team(sequence[0], team_sb):
        return "Immediate shot", sequence[0]
    return "No shot", None


def _all_team_shots(sequence: list[dict], team_sb: str) -> list[dict]:
    return [e for e in sequence if f.by_team(e, team_sb) and f.is_shot(e)]


def _first_touch_after_fk(sequence: list[dict], team_sb: str, flip_y: bool) -> dict[str, Any] | None:
    tracked = {"Ball Receipt*", "Ball Recovery", "Carry", "Dribble", "Duel", "Pass", "Shot"}
    first_touch = None
    first_idx = None
    for idx, event in enumerate(sequence[1:], start=1):
        if not f.by_team(event, team_sb):
            continue
        if _event_type_name(event) not in tracked:
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
            if f.by_team(event, team_sb) and _is_actionable(event):
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
    return {"start": start, "end": end, "kind": kind, "player": f.event_player(action_event) or "Unknown"}


def _shot_links(sequence: list[dict], team_sb: str, flip_y: bool) -> list[dict[str, Any]]:
    links = []
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


def _goal_sequence_actions(sequence: list[dict], team_sb: str, flip_y: bool) -> list[dict[str, Any]]:
    actions = []
    order = 1
    tracked = {"Ball Receipt*", "Ball Recovery", "Carry", "Duel", "Dribble", "Pass", "Shot"}
    for event in sequence:
        if not f.by_team(event, team_sb):
            continue
        if _event_type_name(event) not in tracked:
            continue
        start = _clip_to_pitch(_flip_location(event.get("location"), flip_y))
        if start is None:
            continue
        actions.append({
            "order": order,
            "type": _event_type_name(event),
            "start": start,
            "end": _event_end_location(event, flip_y),
            "player": f.event_player(event) or "Unknown",
            "is_goal": f.is_shot(event) and f.is_goal(event),
        })
        order += 1
        if f.is_shot(event) and f.is_goal(event):
            break
    return actions


# ── Data collection ───────────────────────────────────────────────────────────

def _build_sequence(event: dict, idx: int, events: list[dict],
                    team_sb: str, opponent: str, row: dict) -> dict[str, Any]:
    """Build one FK sequence dict from a single FK event."""
    loc = event.get("location")
    routine  = _fk_routine_type(event)
    flip_y   = loc[1] > 40.0

    sequence     = _sequence_events(events, idx)
    delivery     = _meaningful_fk_delivery(sequence, team_sb, routine)
    phase, first_shot = _shot_phase(sequence, team_sb)
    shots        = _all_team_shots(sequence, team_sb)

    if routine == "Direct shot":
        shots = [sequence[0]] + shots if sequence[0] not in shots else shots

    total_xg     = float(sum(f.shot_xg(s) for s in shots))
    first_shot_xg = float(f.shot_xg(first_shot)) if first_shot else 0.0
    added_xg     = max(total_xg - first_shot_xg, 0.0)
    total_obv    = float(sum(float(e.get("obv_total_net", 0.0) or 0.0)
                             for e in sequence if f.by_team(e, team_sb)))

    fk_start = _flip_location(loc, flip_y)
    if delivery and f.is_pass(delivery):
        delivery_end_raw = delivery.get("pass", {}).get("end_location")
    elif delivery and f.is_fk_shot(delivery):
        delivery_end_raw = delivery.get("shot", {}).get("end_location")
    else:
        delivery_end_raw = None
    delivery_start = _flip_location(delivery.get("location"), flip_y) if delivery else fk_start
    delivery_end   = _clip_to_pitch(_flip_location(delivery_end_raw, flip_y))

    first_shot_loc = _clip_to_pitch(_flip_location(first_shot.get("location"), flip_y)) if first_shot else None
    first_touch    = _first_touch_after_fk(sequence, team_sb, flip_y)
    shot_links     = _shot_links(sequence, team_sb, flip_y)
    goal_actions   = (_goal_sequence_actions(sequence, team_sb, flip_y)
                      if any(f.is_goal(s) for s in shots) else [])

    taker = f.event_player(event) or "Unknown"
    first_receiver = (delivery.get("pass", {}).get("recipient", {}).get("name") or "Unknown"
                      if delivery and f.is_pass(delivery) else taker)

    return {
        "match_id":          row.get("statsbomb", "").strip(),
        "match_label":       f"vs {opponent}",
        "opponent":          opponent,
        "minute":            int(event.get("minute", 0)),
        "fk_taker":          taker,
        "fk_side":           "bottom" if not flip_y else "top",
        "routine_type":      routine,
        "fk_x":              fk_start[0] if fk_start else None,
        "fk_y":              fk_start[1] if fk_start else None,
        "delivery_start_x":  delivery_start[0] if delivery_start else None,
        "delivery_start_y":  delivery_start[1] if delivery_start else None,
        "delivery_end_x":    delivery_end[0] if delivery_end else None,
        "delivery_end_y":    delivery_end[1] if delivery_end else None,
        "delivery_zone":     _classify_zone(delivery_end),
        "shot_phase":        phase,
        "shot_generated":    bool(shots),
        "first_receiver":    first_receiver,
        "first_shot_x":      first_shot_loc[0] if first_shot_loc else None,
        "first_shot_y":      first_shot_loc[1] if first_shot_loc else None,
        "first_shot_xg":     first_shot_xg,
        "total_xg":          total_xg,
        "added_xg":          added_xg,
        "shots_in_sequence": len(shots),
        "goals_in_sequence": sum(1 for s in shots if f.is_goal(s)),
        "total_obv":         total_obv,
        "dead_zone":         loc[0] < DEAD_ZONE_X_MAX,
        "raw_x":             float(loc[0]),
        "first_touch_kind":    first_touch["kind"] if first_touch else "",
        "first_touch_x":       first_touch["start"][0] if first_touch else None,
        "first_touch_y":       first_touch["start"][1] if first_touch else None,
        "first_touch_end_x":   first_touch["end"][0] if first_touch and first_touch["end"] else None,
        "first_touch_end_y":   first_touch["end"][1] if first_touch and first_touch["end"] else None,
        "shot_links":          shot_links,
        "goal_actions":        goal_actions,
    }


def _collect(team: str, data_dir: Path) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []
    for row, events in iter_matches(data_dir):
        team_sb = _team_in_match(team, row, events)
        if team_sb is None:
            continue
        opponent = _team_label(row, team)
        for idx, event in enumerate(events):
            if not (_is_fk_event(event) and f.by_team(event, team_sb)):
                continue
            loc = event.get("location")
            if not loc or loc[0] < ATTACKING_HALF_X:
                continue
            sequences.append(_build_sequence(event, idx, events, team_sb, opponent, row))
    return sequences


def _collect_all(data_dir: Path) -> list[dict[str, Any]]:
    """Single-pass collection of FK sequences for every team in the dataset."""
    sequences: list[dict[str, Any]] = []
    for row, events in iter_matches(data_dir):
        team_names = list({ev.get("team", {}).get("name", "")
                           for ev in events if ev.get("team", {}).get("name")})
        for team_sb in team_names:
            opponent = next((t for t in team_names if t != team_sb), "Unknown")
            for idx, event in enumerate(events):
                if not _is_fk_event(event):
                    continue
                if event.get("team", {}).get("name") != team_sb:
                    continue
                loc = event.get("location")
                if not loc or loc[0] < ATTACKING_HALF_X:
                    continue
                seq = _build_sequence(event, idx, events, team_sb, opponent, row)
                seq["team"] = team_sb
                sequences.append(seq)
    return sequences


def _ordered_counts(values, order):
    counter = Counter(values)
    labels = [l for l in order if counter.get(l, 0) > 0]
    return labels, [counter[l] for l in labels]


# ── Plot 1: Routine profile ───────────────────────────────────────────────────

def _plot_routine_profile(sequences: list[dict], output_path: Path) -> None:
    labels, counts = _ordered_counts([s["routine_type"] for s in sequences], ROUTINE_ORDER)
    colors = [ROUTINE_COLORS[l] for l in labels]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.subplots_adjust(top=0.86, bottom=0.08, hspace=0.32, wspace=0.24)
    ax_count, ax_rate, ax_xg, ax_zone = axes.flat

    ax_count.bar(labels, counts, color=colors)
    ax_count.set_title("FK routine mix")
    ax_count.set_ylabel("Count")
    ax_count.tick_params(axis="x", rotation=15)

    shot_rates, xg_means = [], []
    for label in labels:
        sub = [s for s in sequences if s["routine_type"] == label]
        shot_rates.append(np.mean([float(s["shot_generated"]) for s in sub]))
        xg_means.append(np.mean([s["total_xg"] for s in sub]))

    ax_rate.bar(labels, shot_rates, color=colors)
    ax_rate.set_title("Shot generation rate")
    ax_rate.set_ylabel("Share of FKs with a shot")
    ax_rate.set_ylim(0, max(0.6, max(shot_rates, default=0) * 1.2))
    ax_rate.tick_params(axis="x", rotation=15)

    ax_xg.bar(labels, xg_means, color=colors)
    ax_xg.set_title("Average xG per FK sequence")
    ax_xg.set_ylabel("xG / FK")
    ax_xg.tick_params(axis="x", rotation=15)

    zone_shares = defaultdict(list)
    for label in labels:
        sub = [s for s in sequences if s["routine_type"] == label]
        n = len(sub) or 1
        counter = Counter(s["delivery_zone"] for s in sub)
        for zone in ZONE_ORDER:
            zone_shares[zone].append(counter.get(zone, 0) / n)

    bottom = np.zeros(len(labels))
    for zone in ZONE_ORDER:
        vals = zone_shares[zone]
        if not any(vals):
            continue
        ax_zone.bar(labels, vals, bottom=bottom, label=zone, color=ZONE_COLORS[zone], alpha=0.92)
        bottom += np.array(vals)
    ax_zone.set_title("Target-zone share by routine")
    ax_zone.set_ylabel("Share of sequences")
    ax_zone.tick_params(axis="x", rotation=15)
    ax_zone.legend(loc="upper right", fontsize=8)

    _apply_light_header(fig, "Barcelona offensive free kicks — routine profile",
                        "Routine mix, shot generation, xG and target-zone share")
    save_fig(fig, output_path, tight=False)


# ── Plot 2: Spatial profile (3-panel) ────────────────────────────────────────

def _plot_spatial_profile(sequences: list[dict], output_path: Path) -> None:
    pitch = Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#c7d5cc", half=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.subplots_adjust(top=0.82, bottom=0.08, wspace=0.22)
    for ax in axes:
        pitch.draw(ax=ax)

    for seq in sequences:
        sx, sy = seq["delivery_start_x"], seq["delivery_start_y"]
        ex, ey = seq["delivery_end_x"], seq["delivery_end_y"]
        if None not in (sx, sy, ex, ey):
            pitch.arrows(sx, sy, ex, ey, ax=axes[0],
                         color=ROUTINE_COLORS[seq["routine_type"]],
                         width=1.5, headwidth=4, headlength=4, alpha=0.5)
    axes[0].set_title("Delivery routes by routine type")
    axes[0].legend(
        handles=[Line2D([0], [0], color=ROUTINE_COLORS[l], lw=2, label=l)
                 for l in ROUTINE_ORDER if any(s["routine_type"] == l for s in sequences)],
        loc="lower left", fontsize=8)

    _draw_zone_boxes(axes[1])
    for zone in ZONE_ORDER:
        pts = [(s["delivery_end_x"], s["delivery_end_y"])
               for s in sequences if s["delivery_zone"] == zone
               and s["delivery_end_x"] is not None]
        if not pts:
            continue
        xs, ys = zip(*pts)
        pitch.scatter(xs, ys, ax=axes[1], s=55, color=ZONE_COLORS[zone],
                      edgecolors="white", linewidth=0.5, alpha=0.85, label=zone)
    axes[1].set_title("Delivery endpoints and target zones")
    axes[1].legend(loc="lower left", fontsize=8)

    shots = [s for s in sequences if s["first_shot_x"] is not None]
    if shots:
        xs = [s["first_shot_x"] for s in shots]
        ys = [s["first_shot_y"] for s in shots]
        sizes = [max(s["first_shot_xg"] * 1200, 40) for s in shots]
        pitch.scatter(xs, ys, ax=axes[2], s=sizes, color=FOCUS_COLOR,
                      edgecolors="white", linewidth=0.7, alpha=0.8)
    axes[2].set_title("Shot locations (size = xG)")

    _apply_light_header(fig, "Barcelona offensive free kicks — spatial profile",
                        "Delivery routes, endpoints and shot locations")
    save_fig(fig, output_path, tight=False)


def _plot_spatial_profile_by_routine(sequences: list[dict], routine: str, output_path: Path) -> None:
    sub = [s for s in sequences if s["routine_type"] == routine]
    if not sub:
        return

    pitch = Pitch(pitch_type="statsbomb", pitch_color="white", line_color="#c7d5cc", half=True)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.subplots_adjust(top=0.82, bottom=0.08, wspace=0.22)
    for ax in axes:
        pitch.draw(ax=ax)

    for seq in sub:
        sx, sy = seq["delivery_start_x"], seq["delivery_start_y"]
        ex, ey = seq["delivery_end_x"], seq["delivery_end_y"]
        if None not in (sx, sy, ex, ey):
            pitch.arrows(sx, sy, ex, ey, ax=axes[0],
                         color=ROUTINE_COLORS[routine],
                         width=1.5, headwidth=4, headlength=4, alpha=0.5)
    axes[0].set_title("Delivery routes")

    _draw_zone_boxes(axes[1])
    for zone in ZONE_ORDER:
        pts = [(s["delivery_end_x"], s["delivery_end_y"])
               for s in sub if s["delivery_zone"] == zone
               and s["delivery_end_x"] is not None]
        if not pts:
            continue
        xs, ys = zip(*pts)
        pitch.scatter(xs, ys, ax=axes[1], s=55, color=ZONE_COLORS[zone],
                      edgecolors="white", linewidth=0.5, alpha=0.85, label=zone)
    axes[1].set_title("Delivery endpoints and target zones")
    axes[1].legend(loc="lower left", fontsize=8)

    shots = [s for s in sub if s["first_shot_x"] is not None]
    if shots:
        xs = [s["first_shot_x"] for s in shots]
        ys = [s["first_shot_y"] for s in shots]
        sizes = [max(s["first_shot_xg"] * 1200, 40) for s in shots]
        pitch.scatter(xs, ys, ax=axes[2], s=sizes, color=FOCUS_COLOR,
                      edgecolors="white", linewidth=0.7, alpha=0.8)
    axes[2].set_title("Shot locations (size = xG)")

    _apply_light_header(fig, f"Barcelona offensive free kicks — {routine}",
                        f"Delivery routes, endpoints and shot locations  (n={len(sub)})")
    save_fig(fig, output_path, tight=False)


# ── Plot 3: Player roles ──────────────────────────────────────────────────────

def _hbar_single(ax, counter, title, color, top_n=10):
    top = counter.most_common(top_n)
    if not top:
        ax.set_title(title)
        return
    names, vals = zip(*reversed(top))
    bars = ax.barh(names, vals, color=color, alpha=0.85)
    for bar, val in zip(bars, vals):
        ax.text(val + 0.05, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9)
    ax.set_title(title)
    ax.set_xlabel("Count")
    ax.set_xlim(0, max(vals) * 1.18)


def _plot_fk_takers(sequences: list[dict], output_path: Path) -> None:
    taker_counts = Counter(s["fk_taker"] for s in sequences if s["fk_taker"] != "Unknown")
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.subplots_adjust(top=0.86, bottom=0.08)
    _hbar_single(ax, taker_counts, f"Top FK takers — {TEAM}", FOCUS_COLOR)
    _apply_light_header(fig, "Barcelona offensive free kicks — takers",
                        "Who takes the FK")
    save_fig(fig, output_path, tight=False)


def _plot_fk_receivers(sequences: list[dict], output_path: Path) -> None:
    receiver_counts = Counter(s["first_receiver"] for s in sequences
                              if s["first_receiver"] not in ("Unknown", s["fk_taker"]))
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.subplots_adjust(top=0.86, bottom=0.08)
    _hbar_single(ax, receiver_counts, "Top receivers / first contacts", AVG_COLOR)
    _apply_light_header(fig, "Barcelona offensive free kicks — receivers",
                        "Who receives the FK / first contact")
    save_fig(fig, output_path, tight=False)


# ── Plot 4: First-touch map ───────────────────────────────────────────────────

def _plot_first_touch_map(sequences: list[dict], output_path: Path) -> None:
    fig, ax, pitch = _dark_single_pitch()
    _apply_dark_header(fig, "Barcelona free kicks — first touch after the FK",
                       "Dot = first touch location   Arrow = next action",
                       title_y=0.97, subtitle_y=0.93)

    def _ry(y, side):
        """Restore normalised y back to its original pitch half."""
        return (80.0 - y) if side == "top" else y

    counter = Counter()
    for seq in sequences:
        kind = seq["first_touch_kind"]
        if kind not in FIRST_TOUCH_COLORS or seq["first_touch_x"] is None:
            continue
        side = seq["fk_side"]
        counter[kind] += 1
        color = FIRST_TOUCH_COLORS[kind]
        sx = seq["first_touch_x"]
        sy = _ry(seq["first_touch_y"], side)
        pitch.scatter([sx], [sy], ax=ax, s=64, color=color, edgecolors="white", linewidth=0.65, zorder=4)
        ex = seq["first_touch_end_x"]
        ey_raw = seq["first_touch_end_y"]
        if ex is not None and ey_raw is not None:
            pitch.arrows(sx, sy, ex, _ry(ey_raw, side), ax=ax, color=color,
                         width=1.7, headwidth=4.5, headlength=4.5, alpha=0.82, zorder=3)
        if seq["fk_x"] is not None:
            pitch.scatter([seq["fk_x"]], [_ry(seq["fk_y"], side)], ax=ax, s=90, marker="D",
                          color="#ffd100", edgecolors=DARK_FIG_COLOR, linewidth=0.8, zorder=6)

    ax.set_title(f"n = {len(sequences)}", color="#111111", fontsize=12, pad=10)
    _annotate_pitch_footer(ax, "   ".join(f"{l.lower()}s: {counter.get(l, 0)}"
                                           for l in ("Shot", "Pass", "Carry")))

    _add_dark_legend(fig, [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=FIRST_TOUCH_COLORS[l],
               markeredgecolor="white", markersize=8, lw=0, label=l)
        for l in ("Shot", "Pass", "Carry")
    ] + [Line2D([0], [0], marker="D", color="w", markerfacecolor="#ffd100",
                markeredgecolor=DARK_FIG_COLOR, markersize=9, lw=0, label="FK spot")],
        ncol=4)
    save_fig(fig, output_path, tight=False)


# ── Plot 5: Shot assist map ───────────────────────────────────────────────────

def _plot_shot_assist_map(sequences: list[dict], output_path: Path) -> None:
    fig, axes, pitch = _dark_pitch_figure(2, figsize=(15, 8))
    _apply_dark_header(fig, "Barcelona FK sequences — last pass before shot",
                       "Faded dot + arrow = last pass   Star = shot location   Colour = outcome")

    for ax, label, side in zip(axes, ["Direct / immediate", "Second phase"], ["bottom", "top"]):
        # Show direct/immediate shots on left panel, second-phase on right
        if side == "bottom":
            subset_seqs = [s for s in sequences if s["shot_phase"] in ("Immediate shot",)]
        else:
            subset_seqs = [s for s in sequences if s["shot_phase"] == "Second-phase shot"]
        links = [link for seq in subset_seqs for link in seq["shot_links"]]
        counts = Counter(link["outcome"] for link in links)

        for link in links:
            color = SHOT_OUTCOME_COLORS[link["outcome"]]
            ps, pe, sl = link["pass_start"], link["pass_end"], link["shot_loc"]
            if ps is not None:
                pitch.scatter([ps[0]], [ps[1]], ax=ax, s=28, color="#cfcfcf",
                              edgecolors="white", linewidth=0.3, alpha=0.45, zorder=2)
            if ps is not None and pe is not None:
                pitch.arrows(ps[0], ps[1], pe[0], pe[1], ax=ax, color=color,
                             width=1.5, headwidth=4.2, headlength=4.2, alpha=0.55, zorder=2)
            if sl is not None:
                pitch.scatter([sl[0]], [sl[1]], ax=ax, marker="*", s=130,
                              color=color, edgecolors="white", linewidth=0.8, zorder=4)

        ax.set_title(f"{label}  -  n = {len(links)} shots", color="#111111", fontsize=12, pad=10)
        _annotate_pitch_footer(ax, "   ".join(f"{l.lower()}: {counts.get(l, 0)}"
                                               for l in ("Goal", "Saved", "Other")))

    _add_dark_legend(fig, [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Goal"],
               markeredgecolor="white", markersize=11, lw=0, label="Goal"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Saved"],
               markeredgecolor="white", markersize=11, lw=0, label="Saved"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Other"],
               markeredgecolor="white", markersize=11, lw=0, label="Off target / blocked"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#cfcfcf",
               markeredgecolor="white", markersize=7, lw=0, alpha=0.45, label="Pass start"),
    ], ncol=4)
    save_fig(fig, output_path, tight=False)


# ── Plot 6: Goal sequences ────────────────────────────────────────────────────

def _plot_goal_sequences(sequences: list[dict], output_path: Path) -> None:
    goal_seqs = [s for s in sequences if s["goal_actions"]]
    if not goal_seqs:
        print("  No goal sequences from free kicks — skipping goal_sequences.png")
        return

    fig, axes, pitch = _dark_pitch_figure(len(goal_seqs), figsize=(7.6 * len(goal_seqs), 8))
    _apply_dark_header(fig, "Barcelona goals from free kicks — full sequence maps",
                       "Blue = pass   Yellow = carry   Grey = intermediate   Red star = goal")

    for ax, seq in zip(axes, goal_seqs):
        for action in seq["goal_actions"]:
            start, end = action["start"], action["end"]
            if start is None:
                continue
            t = action["type"]
            if t == "Pass":
                color = "#3b82f6"
                if end:
                    pitch.arrows(start[0], start[1], end[0], end[1], ax=ax,
                                 color=color, width=1.9, headwidth=4.8, headlength=4.8, alpha=0.8, zorder=2)
                pitch.scatter([start[0]], [start[1]], ax=ax, s=55, color=color, edgecolors="white", linewidth=0.5, zorder=3)
            elif t == "Carry":
                color = "#ffd43b"
                if end:
                    pitch.arrows(start[0], start[1], end[0], end[1], ax=ax,
                                 color=color, width=1.9, headwidth=4.8, headlength=4.8, alpha=0.8, zorder=2)
                pitch.scatter([start[0]], [start[1]], ax=ax, s=55, color=color, edgecolors="white", linewidth=0.5, zorder=3)
            elif t == "Shot":
                pitch.scatter([start[0]], [start[1]], ax=ax, marker="*", s=170,
                              color="#ff4d6d", edgecolors="white", linewidth=0.8, zorder=5)
                if end:
                    pitch.arrows(start[0], start[1], end[0], end[1], ax=ax,
                                 color="#ff4d6d", width=1.5, headwidth=4.5, headlength=4.5, alpha=0.6, zorder=4)
            else:
                pitch.scatter([start[0]], [start[1]], ax=ax, s=42, color="#d9d9d9",
                              edgecolors="white", linewidth=0.35, alpha=0.85, zorder=3)
        scorer = next((a["player"] for a in seq["goal_actions"] if a["is_goal"]), "Unknown")
        ax.set_title(f"{seq['match_label']}, {seq['minute']}' — {scorer}",
                     color="#111111", fontsize=12, pad=12)

    _add_dark_legend(fig, [
        Line2D([0], [0], color="#3b82f6", lw=3, label="Pass"),
        Line2D([0], [0], color="#ffd43b", lw=3, label="Carry"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#d9d9d9",
               markeredgecolor="white", markersize=7, lw=0, label="Intermediate contact"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#ff4d6d",
               markeredgecolor="white", markersize=12, lw=0, label="Goal shot"),
    ], ncol=4)
    save_fig(fig, output_path, tight=False)


# ── Plot 7: Direct FK shot effectiveness ─────────────────────────────────────

def _plot_direct_fk_effectiveness(sequences: list[dict], output_path: Path) -> None:
    direct = [s for s in sequences if s["routine_type"] == "Direct shot"]
    if not direct:
        print("  No direct FK shots found — skipping direct_effectiveness.png")
        return

    fig, axes, pitch = _dark_pitch_figure(1, figsize=(9, 8))
    ax = axes[0]

    _apply_dark_header(fig, "Barcelona direct free-kick shots",
                       "Star = shot location (size = xG)   Colour = outcome",
                       title_y=0.97, subtitle_y=0.93)
    _draw_zone_boxes(ax, line_color=DARK_LINE_COLOR)

    outcome_counts = Counter()
    for seq in direct:
        for link in seq["shot_links"]:
            outcome = link["outcome"]
            outcome_counts[outcome] += 1
            color = SHOT_OUTCOME_COLORS[outcome]
            sl = link["shot_loc"]
            if sl is None:
                continue
            xg = seq["first_shot_xg"]
            size = max(xg * 1800, 60)
            pitch.scatter([sl[0]], [sl[1]], ax=ax, marker="*", s=size,
                          color=color, edgecolors="white", linewidth=0.9, zorder=4, alpha=0.9)
            # Annotate opponent
            ax.text(sl[0] + 0.3, sl[1] + 0.5, seq["opponent"][:3].upper(),
                    color="#111111", fontsize=7, alpha=0.75, zorder=5)

    # Also include direct shot events that may not have shot_links
    for seq in direct:
        if not seq["shot_links"] and seq["first_shot_x"] is not None:
            xg = seq["first_shot_xg"]
            pitch.scatter([seq["first_shot_x"]], [seq["first_shot_y"]], ax=ax,
                          marker="*", s=max(xg * 1800, 60), color=FOCUS_COLOR,
                          edgecolors="white", linewidth=0.9, zorder=4, alpha=0.9)

    ax.set_title(f"n = {len(direct)} direct FKs", color="#111111", fontsize=13, pad=10)
    _annotate_pitch_footer(ax, "   ".join(f"{l.lower()}: {outcome_counts.get(l, 0)}"
                                           for l in ("Goal", "Saved", "Other")))

    _add_dark_legend(fig, [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Goal"],
               markeredgecolor="white", markersize=11, lw=0, label="Goal"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Saved"],
               markeredgecolor="white", markersize=11, lw=0, label="Saved"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=SHOT_OUTCOME_COLORS["Other"],
               markeredgecolor="white", markersize=11, lw=0, label="Off target / blocked"),
    ], ncol=3)
    save_fig(fig, output_path, tight=False)


# ── Plot 8: OBV analysis by zone ──────────────────────────────────────────────

def _plot_obv_dead_zone(sequences: list[dict], output_path: Path) -> None:
    """OBV distribution split by 10-yard distance zones from goal."""
    import matplotlib.patches as mpatches

    # Bin by distance from goal (120 - raw_x), in 10-yard bands
    def _dist_bin(x: float) -> str:
        d = 120 - x
        lo = int(d // 10) * 10
        return f"{lo}–{lo + 10}y"

    bin_order = ["0–10y", "10–20y", "20–30y", "30–40y", "40–50y", "50–60y"]
    bin_data: dict[str, list[float]] = defaultdict(list)
    for s in sequences:
        if s["raw_x"] is not None:
            b = _dist_bin(s["raw_x"])
            bin_data[b].append(s["total_obv"])

    active_bins = [b for b in bin_order if bin_data[b]]
    if not active_bins:
        print("  No OBV data — skipping obv_dead_zone.png")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.subplots_adjust(top=0.84, bottom=0.10, wspace=0.32)

    # Left: box plot of OBV by zone
    bp = ax1.boxplot(
        [bin_data[b] for b in active_bins],
        labels=active_bins,
        patch_artist=True,
        medianprops={"color": "black", "linewidth": 1.5},
        flierprops={"marker": "o", "markersize": 3, "alpha": 0.5},
    )
    dead_zone_bins = {b for b in active_bins if int(b.split("–")[0]) >= 28}
    for patch, b in zip(bp["boxes"], active_bins):
        patch.set_facecolor(NEUTRAL_COLOR if b in dead_zone_bins else FOCUS_COLOR)
        patch.set_alpha(0.75)
    ax1.axhline(0, color="#333333", lw=0.8, ls="--")
    ax1.set_title("OBV per FK sequence by distance zone")
    ax1.set_xlabel("Distance from goal")
    ax1.set_ylabel("Total OBV (sequence)")
    ax1.legend(handles=[
        mpatches.Patch(color=FOCUS_COLOR, alpha=0.75, label='Direct-shot range (< 28y)'),
        mpatches.Patch(color=NEUTRAL_COLOR, alpha=0.75, label='"Dead zone" (≥ 28y)'),
    ], fontsize=9)

    # Right: scatter of OBV vs x position, colored by routine
    for seq in sequences:
        if seq["raw_x"] is None:
            continue
        ax2.scatter(120 - seq["raw_x"], seq["total_obv"],
                    color=ROUTINE_COLORS[seq["routine_type"]],
                    s=35, alpha=0.6, edgecolors="none")
    ax2.axvline(120 - DEAD_ZONE_X_MAX, color=NEUTRAL_COLOR, ls="--", lw=1.2,
                label=f"Dead zone boundary ({int(120 - DEAD_ZONE_X_MAX)}y)")
    ax2.axhline(0, color="#333333", lw=0.8, ls="--")
    ax2.set_xlabel("Distance from goal (yards)")
    ax2.set_ylabel("Total OBV (sequence)")
    ax2.set_title("OBV vs FK distance — coloured by routine type")
    ax2.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ROUTINE_COLORS[l],
               markersize=8, lw=0, label=l)
        for l in ROUTINE_ORDER if any(s["routine_type"] == l for s in sequences)
    ] + [Line2D([0], [0], color=NEUTRAL_COLOR, ls="--", lw=1.2, label="Dead zone boundary")],
        fontsize=9)

    _apply_light_header(fig, "Barcelona offensive free kicks — OBV analysis",
                        f'Value generated by distance zone  |  "dead zone" = ≥ {int(120 - DEAD_ZONE_X_MAX)} yards from goal')
    save_fig(fig, output_path, tight=False)


# ── Plot 9: xG per origin zone & delivery type per origin zone ────────────────

FK_LATERAL_ORDER = ["Wide", "Channel", "Central"]
FK_DIST_ORDER    = ["0–20m", "20–30m", "30–50m"]

# 1 yard = 0.9144 m  →  20m ≈ 21.87y, 30m ≈ 32.81y
_FK_DIST_THRESHOLDS = (21.87, 32.81)   # yards from goal line

FK_DIST_COLORS = {
    "0–20m":  "#1a9641",
    "20–30m": "#fdae61",
    "30–50m": "#d7191c",
}


def _classify_fk_lateral(fk_y: float | None) -> str:
    if fk_y is None or fk_y < 14:
        return "Wide"
    if fk_y < 27:
        return "Channel"
    return "Central"


def _classify_fk_dist(fk_x: float | None) -> str:
    if fk_x is None:
        return "30–50m"
    d = 120.0 - fk_x          # yards from goal line
    if d <= _FK_DIST_THRESHOLDS[0]:
        return "0–20m"
    if d <= _FK_DIST_THRESHOLDS[1]:
        return "20–30m"
    return "30–50m"


def _league_avg_xg_by_zone(all_seqs: list[dict], lat: str, dist: str) -> float:
    """Per-team avg xG in (lat, dist), then averaged across teams."""
    teams = {s["team"] for s in all_seqs}
    per_team = []
    for t in teams:
        vals = [s["total_xg"] for s in all_seqs
                if s["team"] == t and s["fk_lateral"] == lat and s["fk_dist"] == dist]
        if vals:
            per_team.append(np.mean(vals))
    return float(np.mean(per_team)) if per_team else 0.0


def _league_avg_routine_share(all_seqs: list[dict], lat: str, dist: str,
                               routine: str) -> float:
    """Per-team share of <routine> FKs in (lat, dist), averaged across teams."""
    teams = {s["team"] for s in all_seqs}
    per_team = []
    for t in teams:
        cell = [s for s in all_seqs
                if s["team"] == t and s["fk_lateral"] == lat and s["fk_dist"] == dist]
        if cell:
            per_team.append(sum(1 for s in cell if s["routine_type"] == routine) / len(cell))
    return float(np.mean(per_team)) if per_team else 0.0


def _plot_xg_delivery_by_zone(sequences: list[dict], all_seqs: list[dict],
                               output_path: Path) -> None:
    for s in sequences + all_seqs:
        if "fk_lateral" not in s:
            s["fk_lateral"] = _classify_fk_lateral(s["fk_y"])
            s["fk_dist"]    = _classify_fk_dist(s["fk_x"])

    active_routines = [r for r in ROUTINE_ORDER
                       if any(s["routine_type"] == r for s in sequences)]

    BAR_W = 0.38
    barca_pos = np.array([0.0, 1.0, 2.0])
    avg_pos   = barca_pos + BAR_W + 0.04

    # ── Compute global y-max for shared xG scale ───────────────────────────────
    global_xg_top = 0.0
    for lat in FK_LATERAL_ORDER:
        for dist in FK_DIST_ORDER:
            b_vals = [s["total_xg"] for s in sequences
                      if s["fk_lateral"] == lat and s["fk_dist"] == dist]
            if b_vals:
                m = np.mean(b_vals)
                global_xg_top = max(global_xg_top, m)
            global_xg_top = max(global_xg_top,
                                _league_avg_xg_by_zone(all_seqs, lat, dist))

    # 2 rows × 3 cols
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.subplots_adjust(top=0.88, bottom=0.13, wspace=0.30, hspace=0.42)

    xtick_pos    = (barca_pos + avg_pos) / 2
    xtick_labels = FK_DIST_ORDER

    for col, lat in enumerate(FK_LATERAL_ORDER):
        lat_barca = [s for s in sequences if s["fk_lateral"] == lat]

        # ── Top row: avg xG ────────────────────────────────────────────────────
        ax_xg = axes[0, col]
        b_means, b_ns, av_means = [], [], []
        for dist in FK_DIST_ORDER:
            vals = [s["total_xg"] for s in lat_barca if s["fk_dist"] == dist]
            b_means.append(np.mean(vals) if vals else 0.0)
            b_ns.append(len(vals))
            av_means.append(_league_avg_xg_by_zone(all_seqs, lat, dist))

        b_bars  = ax_xg.bar(barca_pos, b_means, width=BAR_W,
                            color=FOCUS_COLOR, alpha=0.88,
                            edgecolor="white", linewidth=0.6, label="Barcelona")
        av_bars = ax_xg.bar(avg_pos, av_means, width=BAR_W,
                            color=AVG_COLOR, alpha=0.72,
                            edgecolor="white", linewidth=0.6, label="League avg")

        ceiling = global_xg_top * 1.7 or 0.05
        for bar, m, n in zip(b_bars, b_means, b_ns):
            ax_xg.text(bar.get_x() + bar.get_width() / 2,
                       bar.get_height() + global_xg_top * 0.04,
                       f"{m:.3f}\n(n={n})", ha="center", va="bottom", fontsize=7.5,
                       color=FOCUS_COLOR)
        for bar, m in zip(av_bars, av_means):
            ax_xg.text(bar.get_x() + bar.get_width() / 2,
                       bar.get_height() + global_xg_top * 0.04,
                       f"{m:.3f}", ha="center", va="bottom", fontsize=7.5,
                       color="#555555")

        ax_xg.set_xticks(xtick_pos)
        ax_xg.set_xticklabels(xtick_labels, fontsize=10)
        ax_xg.set_title(lat, fontweight="bold", fontsize=13)
        ax_xg.set_ylim(0, ceiling)
        ax_xg.grid(axis="y", alpha=0.25)
        if col == 0:
            ax_xg.set_ylabel("Avg xG per FK sequence", fontsize=10)
        if col == 0:
            ax_xg.legend(fontsize=8.5, loc="upper right")

        # ── Bottom row: delivery type share ────────────────────────────────────
        ax_dt = axes[1, col]
        b_bottom  = np.zeros(len(FK_DIST_ORDER))
        av_bottom = np.zeros(len(FK_DIST_ORDER))

        for routine in active_routines:
            b_vals = np.array([
                sum(1 for s in lat_barca
                    if s["fk_dist"] == dist and s["routine_type"] == routine)
                for dist in FK_DIST_ORDER
            ], dtype=float)
            av_shares = np.array([
                _league_avg_routine_share(all_seqs, lat, dist, routine)
                for dist in FK_DIST_ORDER
            ])
            b_totals = np.array([
                max(sum(1 for s in lat_barca if s["fk_dist"] == dist), 1)
                for dist in FK_DIST_ORDER
            ], dtype=float)
            av_vals = av_shares * b_totals   # scale avg share to same total height

            ax_dt.bar(barca_pos, b_vals, width=BAR_W, bottom=b_bottom,
                      color=ROUTINE_COLORS[routine], alpha=0.88,
                      edgecolor="white", linewidth=0.5)
            ax_dt.bar(avg_pos, av_vals, width=BAR_W, bottom=av_bottom,
                      color=ROUTINE_COLORS[routine], alpha=0.45,
                      edgecolor="white", linewidth=0.5)

            for pos_, v, b in zip(barca_pos, b_vals, b_bottom):
                if v >= 1:
                    ax_dt.text(pos_, b + v / 2, str(int(v)), ha="center", va="center",
                               fontsize=8, color="white", fontweight="bold")
            b_bottom  += b_vals
            av_bottom += av_vals

        ax_dt.set_xticks(xtick_pos)
        ax_dt.set_xticklabels(xtick_labels, fontsize=10)
        ax_dt.set_ylim(0, max(b_bottom.max(), av_bottom.max(), 1) * 1.3)
        ax_dt.grid(axis="y", alpha=0.25)
        if col == 0:
            ax_dt.set_ylabel("FK count  (avg scaled to same n)", fontsize=9)

        # Barca / avg text labels above stacks
        for pos_, tot in zip(barca_pos, b_bottom):
            ax_dt.text(pos_, tot + 0.15, "BAR", ha="center", va="bottom",
                       fontsize=7, color=FOCUS_COLOR, fontweight="bold")
        for pos_, tot in zip(avg_pos, av_bottom):
            ax_dt.text(pos_, tot + 0.15, "avg", ha="center", va="bottom",
                       fontsize=7, color="#666666")

    # Shared legend for delivery types
    handles = [Line2D([0], [0], color=ROUTINE_COLORS[r], lw=10, label=r, alpha=0.88)
               for r in active_routines]
    fig.legend(handles=handles, loc="lower center", ncol=len(active_routines),
               fontsize=9.5, bbox_to_anchor=(0.5, 0.005), frameon=True)

    _apply_light_header(
        fig,
        "Barcelona offensive free kicks — by origin zone vs league average",
        "Columns: lateral zone   |   X-axis: distance from goal line   |   Solid = Barcelona · Faded = league avg",
        title_y=0.975, subtitle_y=0.948,
    )
    save_fig(fig, output_path, tight=False)


# ── Entry point ───────────────────────────────────────────────────────────────

def run(team: str = TEAM, data_dir: Path = DATA, output_dir: Path | None = None) -> None:
    if output_dir is None:
        output_dir = ASSETS_ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    apply_theme()

    print(f"Collecting {team} attacking FK sequences from {data_dir} …")
    sequences = _collect(team, data_dir)
    print(f"  Found {len(sequences)} FK sequences")

    if not sequences:
        print("No sequences found — check data path and team name.")
        return

    print("Collecting all-team FK sequences for league comparison …")
    all_seqs = _collect_all(data_dir)
    print(f"  Found {len(all_seqs)} FK sequences across all teams")

    plots = [
        ("fk_routine_profile.png",       lambda p: _plot_routine_profile(sequences, p)),
        ("fk_spatial_profile.png",        lambda p: _plot_spatial_profile(sequences, p)),
        *[
            (
                f"fk_spatial_profile_{r.lower().replace(' ', '_').replace('/', '')}.png",
                (lambda p, r=r: _plot_spatial_profile_by_routine(sequences, r, p)),
            )
            for r in ROUTINE_ORDER
        ],
        ("fk_player_roles_takers.png",    lambda p: _plot_fk_takers(sequences, p)),
        ("fk_player_roles_receivers.png", lambda p: _plot_fk_receivers(sequences, p)),
        ("fk_first_touch_map.png",        lambda p: _plot_first_touch_map(sequences, p)),
        ("fk_shot_assist_map.png",        lambda p: _plot_shot_assist_map(sequences, p)),
        ("fk_goal_sequences.png",         lambda p: _plot_goal_sequences(sequences, p)),
        ("fk_direct_effectiveness.png",   lambda p: _plot_direct_fk_effectiveness(sequences, p)),
        ("fk_obv_dead_zone.png",          lambda p: _plot_obv_dead_zone(sequences, p)),
        ("fk_xg_delivery_by_zone.png",    lambda p: _plot_xg_delivery_by_zone(sequences, all_seqs, p)),
    ]

    for filename, plotter in plots:
        path = output_dir / filename
        print(f"  Saving {filename} …")
        plotter(path)

    print(f"\nDone — {len(plots)} plots saved to {output_dir}/")


if __name__ == "__main__":
    run()
