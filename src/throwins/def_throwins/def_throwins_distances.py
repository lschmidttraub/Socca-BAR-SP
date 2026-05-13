"""
def_throwins_distances.py

Average distance from each defending outfield player (GK excluded) to their
nearest opponent at the moment of a throw-in, broken down by zone.

Zone is from the defending team's perspective:
  Defensive  — throw-in taken in the defender's own third (near own goal)
  Middle     — throw-in in the middle third
  Attacking  — throw-in in the opponent's third (far from own goal)

Every game in matches.csv is processed; both teams are measured per game
so all teams in the league appear in the output, not just Barcelona's opponents.

Usage:
    python src/throwins/def_throwins/def_throwins_distances.py
"""

import io
import json
import math
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib.pyplot as plt
import pandas as pd

from throwins import (
    BARCELONA,
    THROWINS_ASSETS_DIR,
    DEFENSIVE_THIRD_MAX,
    ATTACKING_THIRD_MIN,
    _read_matches_df,
)

_PROJECT_ROOT   = Path(__file__).parent.parent.parent.parent
SKILLCORNER_DIR = _PROJECT_ROOT / "data" / "skillcorner"

_HALF_LEN = 52.5   # SkillCorner pitch half-length (x: -52.5 to +52.5)

ZONE_ORDER = ["Defensive", "Middle", "Attacking"]

_TI_START_TYPES = frozenset({
    "throw_in_reception",
    "throw_in_interception",
})


# ── SkillCorner I/O ───────────────────────────────────────────────────────────

def _zip_path(sc_id: int) -> Path | None:
    p = SKILLCORNER_DIR / f"{sc_id}.zip"
    return p if p.exists() else None


def _read_member(sc_id: int, filename: str) -> bytes | None:
    p = _zip_path(sc_id)
    if p is None:
        return None
    with zipfile.ZipFile(p) as zf:
        return zf.read(filename) if filename in zf.namelist() else None


def read_dynamic_events(sc_id: int) -> pd.DataFrame | None:
    raw = _read_member(sc_id, f"{sc_id}_dynamic_events.csv")
    return pd.read_csv(io.BytesIO(raw)) if raw else None


def read_match_meta(sc_id: int) -> dict:
    raw = _read_member(sc_id, f"{sc_id}.json")
    return json.loads(raw.decode("utf-8")) if raw else {}


def iter_tracking_frames(sc_id: int):
    raw = _read_member(sc_id, f"{sc_id}_tracking_extrapolated.jsonl")
    if raw is None:
        return
    for line in io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"):
        line = line.strip()
        if line:
            yield json.loads(line)


# ── Metadata helpers ──────────────────────────────────────────────────────────

def parse_player_index(meta: dict) -> dict[int, dict]:
    index: dict[int, dict] = {}
    for p in meta.get("players", []):
        pid = p.get("id") or p.get("player_id")
        if pid is None:
            continue
        role = p.get("player_role", {})
        is_gk = isinstance(role, dict) and (
            "goalkeeper" in role.get("name", "").lower()
            or "goalkeeper" in role.get("position_group", "").lower()
        )
        entry = {"team_id": p.get("team_id"), "is_gk": is_gk}
        index[int(pid)] = entry
        to = p.get("trackable_object")
        if to is not None:
            index[int(to)] = entry
    return index


def extract_teams(meta: dict) -> dict[int, str]:
    """Return {team_id: team_name} for both teams in the match."""
    teams: dict[int, str] = {}
    for key in ("home_team", "away_team", "homeTeam", "awayTeam"):
        val = meta.get(key, {})
        if isinstance(val, dict):
            tid  = val.get("id") or val.get("team_id")
            name = val.get("name", "")
            if tid is not None and name:
                teams[int(tid)] = name
    return teams


# ── Coordinate / zone helpers ─────────────────────────────────────────────────

def _team_attacks_positive_x(
    frame: dict, player_index: dict, team_tid: int
) -> bool | None:
    """Infer a team's attacking direction from their GK position.

    GK stands near their own goal: GK at negative x → team attacks toward +x.
    """
    for p in frame.get("player_data", []):
        pid = p.get("player_id")
        if pid is None:
            continue
        m = player_index.get(int(pid), {})
        if m.get("is_gk") and m.get("team_id") == team_tid:
            x = p.get("x")
            if x is not None:
                return float(x) < 0
    return None


def _zone_for_defender(x_ti: float, defender_attacks_pos: bool) -> str:
    """Zone of the throw-in from the defending team's own-goal perspective.

    Converts SkillCorner x to StatsBomb-style x where
      0 = defender's own goal,  120 = opponent's goal.
    """
    if defender_attacks_pos:
        x_sb = (x_ti + _HALF_LEN) / (2 * _HALF_LEN) * 120
    else:
        x_sb = (_HALF_LEN - x_ti) / (2 * _HALF_LEN) * 120
    if x_sb <= DEFENSIVE_THIRD_MAX:
        return "Defensive"
    if x_sb >= ATTACKING_THIRD_MIN:
        return "Attacking"
    return "Middle"


# ── Distance helper ───────────────────────────────────────────────────────────

def _nearest_dist(pos: tuple[float, float], others: list[tuple[float, float]]) -> float:
    x, y = pos
    return min(math.hypot(x - ox, y - oy) for ox, oy in others)


# ── Data collection ───────────────────────────────────────────────────────────

def collect_distances() -> dict[str, dict[str, dict[str, list[float]]]]:
    """Return {team_name: {zone: {"all": [...], "top5": [...]}}} for all teams.

    "all"  — avg distance over every outfield defending player per throw-in
    "top5" — avg distance of the 5 most closely marked defenders only

    Every game with a SkillCorner zip is processed; both teams are measured
    so the full league appears in the output.
    Zone labels are always from the defending team's own-goal perspective.
    """
    result: defaultdict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: {z: {"all": [], "top5": [], "bot5": []} for z in ZONE_ORDER}
    )

    for _, row in _read_matches_df().iterrows():
        if pd.isna(row.get("skillcorner")):
            continue
        sc_id = int(row["skillcorner"])
        if _zip_path(sc_id) is None:
            continue

        meta         = read_match_meta(sc_id)
        player_index = parse_player_index(meta)
        teams        = extract_teams(meta)   # {team_id: team_name}
        if len(teams) < 2:
            continue

        dyn = read_dynamic_events(sc_id)
        if dyn is None:
            continue

        dyn_copy = dyn.copy()
        dyn_copy["team_id"] = pd.to_numeric(dyn_copy["team_id"], errors="coerce")

        ti_rows = dyn_copy[
            dyn_copy["start_type"].astype(str).str.casefold().isin(_TI_START_TYPES)
        ].dropna(subset=["frame_start", "team_id"])

        if ti_rows.empty:
            continue

        # frame_id → throwing team_id
        frame_to_thrower: dict[int, int] = {
            int(r["frame_start"]): int(r["team_id"])
            for _, r in ti_rows.iterrows()
        }
        target = set(frame_to_thrower)

        for frame in iter_tracking_frames(sc_id):
            fid = frame.get("frame")
            if fid not in target:
                continue

            thrower_tid = frame_to_thrower[fid]
            if thrower_tid not in teams:
                target.discard(fid)
                continue
            defender_candidates = [tid for tid in teams if tid != thrower_tid]
            if not defender_candidates:
                target.discard(fid)
                continue
            defender_tid = defender_candidates[0]

            # Zone from the defender's own-goal perspective
            defender_attacks_pos = _team_attacks_positive_x(
                frame, player_index, defender_tid
            )
            if defender_attacks_pos is None:
                target.discard(fid)
                continue

            throwing_pos:  list[tuple[float, float]] = []
            defending_pos: list[tuple[float, float]] = []

            for p in frame.get("player_data", []):
                pid = p.get("player_id")
                x, y = p.get("x"), p.get("y")
                if pid is None or x is None or y is None:
                    continue
                m = player_index.get(int(pid), {})
                if m.get("is_gk"):
                    continue
                tid = m.get("team_id")
                if tid == thrower_tid:
                    throwing_pos.append((float(x), float(y)))
                elif tid == defender_tid:
                    defending_pos.append((float(x), float(y)))

            if not throwing_pos or not defending_pos:
                target.discard(fid)
                continue

            # Throw-in taker: throwing outfield player furthest from pitch centre (max |y|)
            x_ti, _ = max(throwing_pos, key=lambda p: abs(p[1]))
            zone = _zone_for_defender(x_ti, defender_attacks_pos)

            dists    = sorted(_nearest_dist(pos, throwing_pos) for pos in defending_pos)
            avg_all  = sum(dists) / len(dists)
            top5     = dists[:5]
            avg_top5 = sum(top5) / len(top5)
            bot5     = dists[-5:]
            avg_bot5 = sum(bot5) / len(bot5)

            defender_name = teams[defender_tid]
            result[defender_name][zone]["all"].append(avg_all)
            result[defender_name][zone]["top5"].append(avg_top5)
            result[defender_name][zone]["bot5"].append(avg_bot5)

            target.discard(fid)
            if not target:
                break

    return dict(result)


# ── Plotting ──────────────────────────────────────────────────────────────────

def _draw_zone_bars(
    ax,
    distances: dict[str, dict[str, dict[str, list[float]]]],
    zone: str,
    metric: str,
) -> None:
    """Populate one subplot panel with a sorted horizontal bar chart."""
    rows = []
    for team, zone_data in distances.items():
        vals = zone_data.get(zone, {}).get(metric, [])
        if vals:
            rows.append({
                "team":     team,
                "avg_dist": sum(vals) / len(vals),
                "n":        len(vals),
            })

    if not rows:
        ax.set_title(f"{zone} — no data", fontsize=10)
        return

    df   = pd.DataFrame(rows).sort_values("avg_dist")
    bars = ax.barh(df["team"], df["avg_dist"], color="steelblue", edgecolor="white")

    barca_mask = df["team"].str.contains(BARCELONA, case=False)
    for bar, is_barca in zip(bars, barca_mask):
        if is_barca:
            bar.set_color("#e63946")

    for bar, val, n in zip(bars, df["avg_dist"], df["n"]):
        ax.text(
            val + 0.05, bar.get_y() + bar.get_height() / 2,
            f"{val:.2f} m  ({n})", va="center", fontsize=7.5,
        )

    league_avg = df["avg_dist"].mean()
    ax.axvline(league_avg, color="black", linestyle="--", linewidth=1.2,
               label=f"Avg: {league_avg:.2f} m")

    ax.set_title(f"{zone} zone", fontsize=11)
    ax.set_xlabel("Avg nearest-opponent distance (m)", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(axis="x", alpha=0.25)
    ax.tick_params(labelsize=8)


def plot_distances_by_zone(
    distances: dict[str, dict[str, dict[str, list[float]]]],
    save: bool = True,
) -> None:
    """3×3 grid: rows = all / 5 most closely marked / 5 least closely marked, columns = zone."""
    n_teams = len(distances)
    row_meta = [
        ("all",  "All outfield players"),
        ("top5", "5 most closely marked players"),
        ("bot5", "5 least closely marked players"),
    ]

    fig, axes = plt.subplots(3, 3, figsize=(18, max(12, n_teams * 0.63)))
    fig.set_facecolor("white")

    for row, (metric, row_label) in enumerate(row_meta):
        for col, zone in enumerate(ZONE_ORDER):
            ax = axes[row][col]
            _draw_zone_bars(ax, distances, zone, metric)
            if col == 0:
                ax.set_ylabel(row_label, fontsize=9, labelpad=8)

    fig.suptitle(
        "Defensive compactness at throw-ins — avg distance to nearest opponent\n"
        "Red = Barcelona  ·  GKs excluded  ·  Zone = defender's own-goal perspective  ·  dashed = league avg\n"
        "Top row: all players  ·  Middle: 5 closest  ·  Bottom: 5 furthest",
        fontsize=12, y=1.01,
    )
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_distances.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")

    plt.show()


def plot_distances_combined(
    distances: dict[str, dict[str, dict[str, list[float]]]],
    save: bool = True,
) -> None:
    """Two-panel plot combining all zones: left = all players, right = 5 most closely marked."""
    metrics = [
        ("all",  "All outfield players"),
        ("top5", "5 most closely marked"),
    ]

    # Aggregate each team's values across all zones
    rows: dict[str, dict[str, list[float]]] = {}
    for team, zone_data in distances.items():
        rows[team] = {m: [] for m, _ in metrics}
        for zone in ZONE_ORDER:
            for metric, _ in metrics:
                rows[team][metric].extend(zone_data.get(zone, {}).get(metric, []))

    n_teams = len(distances)
    fig, axes = plt.subplots(1, 2, figsize=(16, max(8, n_teams * 0.45)))
    fig.set_facecolor("white")

    for ax, (metric, label) in zip(axes, metrics):
        plot_rows = [
            {"team": team, "avg_dist": sum(vals) / len(vals), "n": len(vals)}
            for team, vals_by_metric in rows.items()
            for vals in [vals_by_metric[metric]]
            if vals
        ]
        if not plot_rows:
            ax.set_title(label)
            continue

        df   = pd.DataFrame(plot_rows).sort_values("avg_dist")
        bars = ax.barh(df["team"], df["avg_dist"], color="steelblue", edgecolor="white")

        barca_mask = df["team"].str.contains(BARCELONA, case=False)
        for bar, is_barca in zip(bars, barca_mask):
            if is_barca:
                bar.set_color("#e63946")

        for bar, val, n in zip(bars, df["avg_dist"], df["n"]):
            ax.text(
                val + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{val:.2f} m  ({n})", va="center", fontsize=7.5,
            )

        league_avg = df["avg_dist"].mean()
        ax.axvline(league_avg, color="black", linestyle="--", linewidth=1.2,
                   label=f"Avg: {league_avg:.2f} m")

        ax.set_title(label, fontsize=11)
        ax.set_xlabel("Avg nearest-opponent distance (m)", fontsize=9)
        ax.legend(fontsize=8)
        ax.grid(axis="x", alpha=0.25)
        ax.tick_params(labelsize=8)

    fig.suptitle(
        "Defensive compactness at throw-ins — avg distance to nearest opponent (all zones combined)\n"
        "Red = Barcelona  ·  GKs excluded  ·  dashed = league avg",
        fontsize=12, y=1.01,
    )
    plt.tight_layout()

    if save:
        THROWINS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        out = THROWINS_ASSETS_DIR / "throwins_defense_distances_combined.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved {out}")

    plt.show()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Collecting SkillCorner throw-in distance data ...")
    distances = collect_distances()

    print(f"\nTeams found: {len(distances)}")
    for team, zone_data in sorted(distances.items()):
        parts = []
        for zone in ZONE_ORDER:
            vals_all  = zone_data.get(zone, {}).get("all",  [])
            vals_top5 = zone_data.get(zone, {}).get("top5", [])
            vals_bot5 = zone_data.get(zone, {}).get("bot5", [])
            if vals_all:
                parts.append(
                    f"{zone}: {sum(vals_all)/len(vals_all):.2f}m all"
                    f" / {sum(vals_top5)/len(vals_top5):.2f}m top5"
                    f" / {sum(vals_bot5)/len(vals_bot5):.2f}m bot5"
                    f" ({len(vals_all)})"
                )
        if parts:
            print(f"  {team:30s}  {' | '.join(parts)}")

    plot_distances_by_zone(distances)
    plot_distances_combined(distances)
