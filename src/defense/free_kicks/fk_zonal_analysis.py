"""
fk_zonal_analysis.py

Zonal vs man-marking analysis of Barcelona's defensive free kicks across
the full UCL 2025-26 dataset (league phase → quarterfinals).

Driven from SkillCorner: every opponent ``free_kick_reception`` whose
location is on Barca's defensive side of midfield. The freeze-frame at
``frame_start`` gives the positions of all 22 players; for each Barca
outfielder we compute the distance to their nearest opponent and label
the FK by the fraction of "tight" defenders (≤ ``MAN_THRESHOLD_M``).

For the per-FK threat plot we additionally pair each classified SC FK
with its StatsBomb counterpart (rank-within-period matching) so we can
size the marker by the OBV/xG accumulated over the FK possession.

Outputs
-------
``assets/defense/free_kicks/``
    2_marking_system_frequency.png      team-level Zonal/Hybrid/Man split
    3_marking_distance_by_system.png    per-defender distance distribution
    4_player_marking_roles.png          per-player tight-rate + role label
    5_marking_system_per_match.png      system mix per opponent
    6_fk_locations_by_system.png        FK origins on the pitch coloured by
                                         system, sized by OBV/xG threat

Usage
-----
    uv run python src/defense/free_kicks/fk_zonal_analysis.py
"""

import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from mplsoccer import Pitch

# ── Imports from sibling defence modules ─────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corners"))
from defending_corners import (  # noqa: E402
    BARCELONA, ASSETS_DIR, MATCHES_CSV, _read_matches_df,
    read_statsbomb,
)
from def_corner_positioning import (  # noqa: E402
    _zip_path, read_dynamic_events, read_match_meta,
    iter_tracking_frames, teams_from_meta,
)

# ── Config ───────────────────────────────────────────────────────────────────
TEAM       = BARCELONA
OUT_DIR    = ASSETS_DIR / "defense" / "free_kicks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# An attacker is in a defender's "tight set" if within this distance.
MAN_THRESHOLD_M = 2.5
# A defender is *engaged* on an FK if their tight set is non-empty at the
# shot frame OR the reception frame; otherwise they aren't part of the
# marking action (forwards parked upfield, zonal defenders on a far post
# with no one nearby, …) and contribute no per-FK signal.
# A defender is *man-marking* if the shot-frame and reception-frame tight
# sets share at least one attacker — i.e. they kept a tight relationship
# with the same opponent through the delivery.
# SkillCorner extrapolated tracking runs at 10 fps. We bracket the FK
# delivery with two freeze-frames: the reception (FK event ``frame_start``)
# and a "shot" frame ``SHOT_OFFSET_FRAMES`` earlier — i.e. 2 s before the
# receiver controls the ball, which is approximately when the FK is struck
# for a typical box delivery and well into the pre-FK setup for shorter
# tap-style FKs. Using the kicker's tagged possession instead was too
# unreliable (≈70 % of FKs have no nearby opp possession event).
SHOT_OFFSET_FRAMES = 20
# Per-FK system thresholds (fraction of *engaged* defenders that man-marked).
MAN_FRAC_HI     = 0.55
MAN_FRAC_LO     = 0.30
# Per-player role thresholds (share of engaged FKs the player man-marked).
PLAYER_MIN_FKS  = 4
PLAYER_MAN_HI   = 0.55
PLAYER_MAN_LO   = 0.20

# Palette — muted, print-friendly, consistent across all plots.
C_ZONAL  = "#3a6b9c"
C_HYBRID = "#e09f3e"
C_MAN    = "#a23b3b"
C_GREY   = "#7d7d7d"

SYSTEM_ORDER  = ["Zonal-Marking", "Hybrid", "Man-Marking"]
SYSTEM_COLORS = {"Zonal-Marking": C_ZONAL, "Hybrid": C_HYBRID, "Man-Marking": C_MAN}
ROLE_ORDER    = ["Zonal", "Mixed", "Man-Marker"]
ROLE_COLORS   = {"Zonal": C_ZONAL, "Mixed": C_HYBRID, "Man-Marker": C_MAN}


def _set_style() -> None:
    sns.set_theme(style="white", rc={
        "axes.titleweight": "bold",
        "axes.titlesize":   12,
        "axes.titlepad":    12,
        "axes.labelsize":   10,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "xtick.labelsize":  9,
        "ytick.labelsize":  9,
        "legend.fontsize":  9,
        "figure.facecolor": "white",
    })


def _caption(fig, text: str) -> None:
    fig.text(0.99, 0.005, text, ha="right", va="bottom",
             fontsize=7.5, alpha=0.55, style="italic")


# ─────────────────────────────────────────────────────────────────────────────
# Player metadata helper (robust GK detection — overrides corners default)
# ─────────────────────────────────────────────────────────────────────────────
def parse_player_index(meta: dict) -> dict[int, dict]:
    """Map ``player_id`` / ``trackable_object`` → {team_id, is_gk, name}.

    GK detection uses ``player_role.name`` (the field that's actually populated
    in this dataset; ``position.name`` is None).
    """
    index: dict[int, dict] = {}
    for p in meta.get("players", []):
        role = p.get("player_role") or {}
        is_gk = (
            isinstance(role, dict)
            and ("goalkeeper" in (role.get("name") or "").lower()
                 or "goalkeeper" in (role.get("position_group") or "").lower())
        )
        name = (
            p.get("short_name")
            or " ".join(filter(None, [p.get("first_name"), p.get("last_name")])).strip()
            or str(p.get("id") or p.get("player_id") or "")
        )
        entry = {"team_id": p.get("team_id"), "is_gk": is_gk, "name": name}
        for key in ("id", "player_id", "trackable_object"):
            v = p.get(key)
            if v is not None:
                index[int(v)] = entry
    return index


# ─────────────────────────────────────────────────────────────────────────────
# SkillCorner — marking-system classification
# ─────────────────────────────────────────────────────────────────────────────
def _split_outfielders(frame: dict, player_index: dict, def_tid: int):
    """Return ``(defender_records, attacker_records, def_gk_xy)``.

    defender_records = [(player_id, name, x, y), ...]  (Barca outfielders)
    attacker_records = [(player_id, x, y), ...]        (opponent outfielders)
    """
    defs, atts = [], []
    def_gk = None
    for p in frame.get("player_data", []):
        pid, x, y = p.get("player_id"), p.get("x"), p.get("y")
        if pid is None or x is None or y is None:
            continue
        meta = player_index.get(int(pid), {})
        tid = meta.get("team_id")
        if meta.get("is_gk"):
            if tid == def_tid:
                def_gk = (x, y)
            continue
        if tid == def_tid:
            defs.append((int(pid), meta.get("name", str(pid)), x, y))
        else:
            atts.append((int(pid), x, y))
    return defs, atts, def_gk


def _nearest_attacker_distance(def_xy: tuple[float, float],
                               atts: list[tuple[int, float, float]]) -> float:
    return min(
        (math.hypot(def_xy[0] - ax, def_xy[1] - ay) for _, ax, ay in atts),
        default=math.inf,
    )


def _tight_attacker_set(def_xy: tuple[float, float],
                        atts: list[tuple[int, float, float]],
                        threshold: float = MAN_THRESHOLD_M) -> set[int]:
    """Set of attacker player_ids within ``threshold`` metres of ``def_xy``."""
    return {
        aid for aid, ax, ay in atts
        if math.hypot(def_xy[0] - ax, def_xy[1] - ay) <= threshold
    }


def classify_system(man_frac: float | None) -> str | None:
    if man_frac is None:
        return None
    if man_frac >= MAN_FRAC_HI:
        return "Man-Marking"
    if man_frac <= MAN_FRAC_LO:
        return "Zonal-Marking"
    return "Hybrid"


def collect_marking_rows() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return ``(per_fk, per_defender, per_player)`` dataframes.

    Detection logic
    ---------------
    For each defensive FK we extract two freeze-frames:
      * **shot frame** — `frame_start` of the kicker's possession event
        (latest opp `team_id` event preceding the FK delivery)
      * **reception frame** — `frame_start` of the SC FK event itself

    For every Barca outfielder present in *both* frames we compute the
    player_id of their nearest attacker at each. If they are within
    ``ENGAGEMENT_DIST_M`` of *some* attacker at one of the two frames
    they are "engaged" on this FK; an engaged defender is **man-marking**
    if the nearest-attacker player_id is unchanged between frames, and
    **zonal** otherwise. Forwards parked upfield are filtered out by the
    engagement check and contribute no per-FK signal.
    """
    matches_df = _read_matches_df(MATCHES_CSV)
    mt = matches_df[
        matches_df["home"].str.contains(TEAM, case=False, na=False)
        | matches_df["away"].str.contains(TEAM, case=False, na=False)
    ]

    per_fk: list[dict] = []
    per_def: list[dict] = []
    per_player: list[dict] = []

    for _, row in mt.iterrows():
        if pd.isna(row["skillcorner"]):
            continue
        sc_id = int(row["skillcorner"])
        if _zip_path(sc_id) is None:
            continue

        meta = read_match_meta(sc_id)
        if not meta:
            continue
        teams = teams_from_meta(meta)
        if len(teams) < 2:
            continue
        barca_tid = next(
            (t["id"] for t in teams if TEAM.casefold() in t["name"].casefold()),
            None,
        )
        if barca_tid is None:
            continue
        opponent = next(
            (t["name"] for t in teams if TEAM.casefold() not in t["name"].casefold()),
            "?",
        )
        date = str(row.get("date", ""))
        player_index = parse_player_index(meta)

        de = read_dynamic_events(sc_id)
        if de is None or "start_type" not in de.columns:
            continue

        # Defensive FK events: opp reception OR Barca interception.
        st = de["start_type"].astype(str).str.casefold()
        is_recv = (st == "free_kick_reception")    & (de["team_id"] != barca_tid)
        is_intc = (st == "free_kick_interception") & (de["team_id"] == barca_tid)
        fks = de[
            (is_recv | is_intc)
            & de["frame_start"].notna()
            & de["x_start"].notna()
        ]
        if fks.empty:
            continue

        # For each FK, the two frames we need: the reception and a "shot"
        # frame ``SHOT_OFFSET_FRAMES`` earlier (≈ 2 s before delivery).
        fk_records = []  # list of (fk_row, shot_frame, recv_frame)
        wanted_frames: set[int] = set()
        for _, fk in fks.iterrows():
            recv_frame = int(fk["frame_start"])
            shot_frame = recv_frame - SHOT_OFFSET_FRAMES
            if shot_frame < 0:
                continue
            fk_records.append((fk, shot_frame, recv_frame))
            wanted_frames.add(shot_frame)
            wanted_frames.add(recv_frame)

        if not fk_records:
            continue

        # Single pass over the tracking JSONL collecting every needed frame.
        frame_data: dict[int, tuple[list, list, tuple | None]] = {}
        remaining = set(wanted_frames)
        for frame in iter_tracking_frames(sc_id):
            fid = frame.get("frame")
            if fid not in remaining:
                continue
            frame_data[fid] = _split_outfielders(frame, player_index, barca_tid)
            remaining.discard(fid)
            if not remaining:
                break

        # Classify each FK using the two frames.
        for fk, shot_f, recv_f in fk_records:
            shot = frame_data.get(shot_f)
            recv = frame_data.get(recv_f)
            if shot is None or recv is None:
                continue
            shot_defs, shot_atts, shot_gk = shot
            recv_defs, recv_atts, _       = recv
            if (len(shot_defs) < 5 or len(shot_atts) < 3 or shot_gk is None
                    or len(recv_defs) < 5 or len(recv_atts) < 3):
                continue

            # Half filter: FK origin on Barca's defending side (same x-sign as Barca GK).
            fk_x = float(fk["x_start"])
            if fk_x * shot_gk[0] <= 0:
                continue

            # Index defenders by player_id so we can match across frames.
            shot_def_map = {pid: (name, x, y) for pid, name, x, y in shot_defs}
            recv_def_map = {pid: (name, x, y) for pid, name, x, y in recv_defs}

            n_engaged = 0
            n_man = 0
            per_def_rows: list[dict] = []
            for pid, (name, sx, sy) in shot_def_map.items():
                rec = recv_def_map.get(pid)
                if rec is None:
                    continue
                _, rx, ry = rec
                shot_set = _tight_attacker_set((sx, sy), shot_atts)
                recv_set = _tight_attacker_set((rx, ry), recv_atts)
                # Not engaged if no attacker was within the tight radius at either frame.
                if not shot_set and not recv_set:
                    continue
                n_engaged += 1
                # Man-marking iff at least one attacker stayed inside the tight
                # radius across both frames — i.e. tight-set intersection ≠ ∅.
                is_man = bool(shot_set & recv_set)
                n_man += int(is_man)
                per_def_rows.append({
                    "player":  name,
                    "shot_d":  _nearest_attacker_distance((sx, sy), shot_atts),
                    "recv_d":  _nearest_attacker_distance((rx, ry), recv_atts),
                    "is_man":  is_man,
                })

            if n_engaged == 0:
                continue
            man_frac = n_man / n_engaged
            system = classify_system(man_frac)
            if system is None:
                continue

            period = int(fk["period"]) if pd.notna(fk["period"]) else 0
            sc_t   = float(fk.get("minute_start") or 0) * 60 + float(fk.get("second_start") or 0)

            per_fk.append({
                "system":     system,
                "man_frac":   man_frac,
                "n_engaged":  n_engaged,
                "n_man":      n_man,
                "x_start":    fk_x,
                "y_start":    float(fk["y_start"]),
                "match":      sc_id,
                "statsbomb":  int(row["statsbomb"]) if pd.notna(row["statsbomb"]) else None,
                "opponent":   opponent,
                "date":       date,
                "period":     period,
                "sc_t":       sc_t,
            })
            for r in per_def_rows:
                per_def.append({"system": system, "nearest_distance_m": r["recv_d"]})
                per_player.append({
                    "player":   r["player"],
                    "is_man":   r["is_man"],
                    "shot_d":   r["shot_d"],
                    "recv_d":   r["recv_d"],
                    "system":   system,
                    "match":    sc_id,
                    "opponent": opponent,
                })

    return pd.DataFrame(per_fk), pd.DataFrame(per_def), pd.DataFrame(per_player)


# ─────────────────────────────────────────────────────────────────────────────
# StatsBomb pairing — attach OBV/xG to each classified FK
# ─────────────────────────────────────────────────────────────────────────────
SEQUENCE_MAX_SECONDS = 10.0
TYPE_PASS = 30
TYPE_SHOT = 16


def _ts_seconds(ts: str) -> float:
    if not ts:
        return 0.0
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _is_fk_event(e: dict) -> bool:
    tid = e.get("type", {}).get("id")
    if tid == TYPE_PASS:
        return e.get("pass", {}).get("type", {}).get("name") == "Free Kick"
    if tid == TYPE_SHOT:
        return e.get("shot", {}).get("type", {}).get("name") == "Free Kick"
    return False


def _is_penalty_shot(e: dict) -> bool:
    return (e.get("type", {}).get("id") == TYPE_SHOT
            and e.get("shot", {}).get("type", {}).get("name") == "Penalty")


def _event_value(e: dict) -> float:
    """statsbomb_obv.value → shot.statsbomb_xg → 0."""
    obv = e.get("statsbomb_obv")
    v = obv.get("value") if isinstance(obv, dict) else None
    if v is None:
        v = e.get("shot", {}).get("statsbomb_xg")
    return float(v) if v is not None else 0.0


def _sequence_value(events: list, start_idx: int, team: str) -> float:
    """Sum the FK-taking team's per-event OBV/xG over the FK possession,
    capped at SEQUENCE_MAX_SECONDS — same convention as fouls_freekicks.py."""
    start = events[start_idx]
    poss, period = start.get("possession"), start.get("period")
    t0 = _ts_seconds(start.get("timestamp", ""))
    total = 0.0
    for e in events[start_idx:]:
        if e.get("period") != period or e.get("possession") != poss:
            break
        if _ts_seconds(e.get("timestamp", "")) - t0 > SEQUENCE_MAX_SECONDS:
            break
        if e.get("team", {}).get("name") == team:
            total += _event_value(e)
    return total


def _statsbomb_opp_fks(sb_id: int) -> list[dict]:
    """Return opp FK pass/shot events in Barca's defensive half with OBV/xG.

    Coordinates are reflected into Barca's frame (own goal at x = 0):
    barca_x = 120 − opp_x, barca_y = 80 − opp_y.
    """
    try:
        events = read_statsbomb(sb_id)
    except FileNotFoundError:
        return []

    out = []
    for idx, e in enumerate(events):
        team = e.get("team", {}).get("name", "")
        if not team or TEAM.casefold() in team.casefold():
            continue
        if _is_penalty_shot(e):
            continue
        if not _is_fk_event(e):
            continue
        loc = e.get("location")
        if not loc or len(loc) < 2:
            continue
        opp_x, opp_y = float(loc[0]), float(loc[1])
        # In opp's attacking frame, x > 60 = Barca's defending half.
        if opp_x <= 60.0:
            continue
        out.append({
            "period":  e.get("period"),
            "sb_t":    _ts_seconds(e.get("timestamp", "")),
            "barca_x": 120.0 - opp_x,
            "barca_y": 80.0  - opp_y,
            "obv_xg":  _sequence_value(events, idx, team),
        })
    return out


def attach_obv(per_fk: pd.DataFrame) -> pd.DataFrame:
    """Pair each SC-classified FK with its StatsBomb counterpart by
    rank-within-period (sort both by time, zip together).
    Unpaired rows are dropped.

    Rank pairing is more robust than absolute-time matching here because
    SC uses continuous match-seconds while SB is period-relative, so a
    bad anchor offset can throw off every pair in the period.
    """
    if per_fk.empty:
        return per_fk

    enriched_rows = []
    for sb_id, group in per_fk.groupby("statsbomb"):
        if pd.isna(sb_id):
            continue
        sb_fks = _statsbomb_opp_fks(int(sb_id))
        if not sb_fks:
            continue
        sb_by_period: dict[int, list[dict]] = defaultdict(list)
        for s in sb_fks:
            sb_by_period[int(s["period"])].append(s)
        for p in sb_by_period:
            sb_by_period[p].sort(key=lambda d: d["sb_t"])

        for period, sc_block in group.groupby("period"):
            sb_list = sb_by_period.get(int(period), [])
            if not sb_list:
                continue
            sc_sorted = sc_block.sort_values("sc_t").reset_index(drop=True)
            for i, sc_row in sc_sorted.iterrows():
                if i >= len(sb_list):
                    break
                sb = sb_list[i]
                enriched_rows.append({
                    **sc_row.to_dict(),
                    "barca_x": sb["barca_x"],
                    "barca_y": sb["barca_y"],
                    "obv_xg":  sb["obv_xg"],
                })

    return pd.DataFrame(enriched_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────
def aggregate_per_match(per_fk: pd.DataFrame) -> pd.DataFrame:
    if per_fk.empty:
        return pd.DataFrame()
    g = per_fk.groupby(["opponent", "date"], dropna=False)
    out = g.agg(
        n_fks=("system", "size"),
        n_zonal=("system", lambda s: (s == "Zonal-Marking").sum()),
        n_hybrid=("system", lambda s: (s == "Hybrid").sum()),
        n_man=("system", lambda s: (s == "Man-Marking").sum()),
        mean_man_frac=("man_frac", "mean"),
    ).reset_index()
    return out.sort_values("mean_man_frac").reset_index(drop=True)


def aggregate_player_roles(per_player: pd.DataFrame) -> pd.DataFrame:
    if per_player.empty:
        return pd.DataFrame(columns=["player", "n_fks", "n_man", "man_pct", "median_dist_m", "role"])
    grp = per_player.groupby("player").agg(
        n_fks=("is_man", "size"),
        n_man=("is_man", "sum"),
        median_dist_m=("recv_d", "median"),
    ).reset_index()
    grp["man_pct"] = grp["n_man"] / grp["n_fks"]
    grp = grp[grp["n_fks"] >= PLAYER_MIN_FKS].copy()

    def _role(p: float) -> str:
        if p >= PLAYER_MAN_HI: return "Man-Marker"
        if p <= PLAYER_MAN_LO: return "Zonal"
        return "Mixed"
    grp["role"] = grp["man_pct"].map(_role)
    return grp.sort_values("man_pct").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Plots
# ─────────────────────────────────────────────────────────────────────────────
def plot_system_frequency(per_fk: pd.DataFrame, out: Path) -> None:
    counts = {s: int((per_fk["system"] == s).sum()) for s in SYSTEM_ORDER}
    total = sum(counts.values())

    fig, ax = plt.subplots(figsize=(8, 3.4))
    ys = list(reversed(SYSTEM_ORDER))
    vals = [counts[s] for s in ys]
    ax.barh(ys, vals,
            color=[SYSTEM_COLORS[s] for s in ys],
            edgecolor="white", height=0.62)
    for s, v in zip(ys, vals):
        pct = 100 * v / total if total else 0
        ax.text(v + max(vals) * 0.015, s, f"{v}  ·  {pct:.0f}%",
                va="center", fontsize=10)

    ax.set_xlim(0, max(vals) * 1.18 if vals else 1)
    ax.set_xlabel("Defensive free kicks (count)")
    ax.set_title("Marking system on defensive free kicks")
    ax.tick_params(left=False)
    ax.grid(axis="x", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)
    _caption(fig, f"N = {total} FKs • man-marker = at least one attacker stays within "
                  f"{MAN_THRESHOLD_M:.1f} m of the defender across shot + reception frames • "
                  f"Man ≥ {MAN_FRAC_HI:.0%} of engaged, Zonal ≤ {MAN_FRAC_LO:.0%}")
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=160)
    plt.close(fig)


def plot_distance_by_system(per_def: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    sns.boxplot(
        data=per_def, x="system", y="nearest_distance_m",
        order=SYSTEM_ORDER, hue="system", palette=SYSTEM_COLORS, legend=False,
        width=0.55, linewidth=1.0, fliersize=2.5, ax=ax,
    )
    ax.axhline(MAN_THRESHOLD_M, color=C_GREY, linestyle="--", linewidth=0.9, alpha=0.55)
    ax.set_title("Distance to nearest attacker (at reception) by classified system")
    ax.set_xlabel("")
    ax.set_ylabel("Distance to nearest attacker (m)")
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)
    _caption(fig, f"Per-engaged-defender distances at the reception frame • "
                  f"dashed line = tight threshold ({MAN_THRESHOLD_M:.1f} m)")
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=160)
    plt.close(fig)


def plot_player_roles(player_df: pd.DataFrame, out: Path) -> None:
    if player_df.empty:
        return
    fig, ax = plt.subplots(figsize=(8.5, max(4, 0.34 * len(player_df))))
    bars = ax.barh(
        player_df["player"], player_df["man_pct"] * 100,
        color=[ROLE_COLORS[r] for r in player_df["role"]],
        edgecolor="white", height=0.7,
    )
    for b, n_m, n in zip(bars, player_df["n_man"], player_df["n_fks"]):
        ax.text(b.get_width() + 1.2, b.get_y() + b.get_height() / 2,
                f"{int(n_m)}/{int(n)}", va="center", fontsize=8.5, color=C_GREY)

    # Subtle threshold guides.
    for x in (PLAYER_MAN_LO * 100, PLAYER_MAN_HI * 100):
        ax.axvline(x, color=C_GREY, linestyle=":", linewidth=0.8, alpha=0.4)

    max_pct = float(player_df["man_pct"].max() * 100) if len(player_df) else 0
    ax.set_xlim(0, max(70, max_pct + 12))
    ax.set_xlabel("Share of engaged FKs man-marking the same attacker (%)")
    ax.set_title(f"{TEAM} — player marking roles on defensive FKs")
    ax.tick_params(left=False)
    ax.grid(axis="x", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)

    handles = [plt.Rectangle((0, 0), 1, 1, color=ROLE_COLORS[r]) for r in ROLE_ORDER]
    ax.legend(handles, ROLE_ORDER, loc="lower right", frameon=False)
    _caption(fig, f"Min {PLAYER_MIN_FKS} engaged FKs • Zonal ≤ {PLAYER_MAN_LO:.0%}, "
                  f"Man-Marker ≥ {PLAYER_MAN_HI:.0%} • count = man-marking/engaged")
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=160)
    plt.close(fig)


_MONTH = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _short_date(d: str) -> str:
    """'2026-03-10' → '10 Mar'."""
    if not d or len(d) < 10:
        return ""
    try:
        y, m, dd = d[:4], int(d[5:7]), d[8:10]
        return f"{dd} {_MONTH[m]}"
    except Exception:
        return d


_MAN_CMAP = LinearSegmentedColormap.from_list(
    "man_frac", [C_ZONAL, C_MAN], N=256,
)


def plot_fk_locations_by_tightness(per_fk: pd.DataFrame, out: Path) -> None:
    if per_fk.empty or "barca_x" not in per_fk.columns:
        return

    pitch = Pitch(pitch_type="statsbomb", pitch_color="white",
                  line_color="#bdbdbd", linewidth=1.0)
    fig, ax = plt.subplots(figsize=(11.5, 6.5))
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=0.04, right=0.78, top=0.92, bottom=0.06)
    pitch.draw(ax=ax)
    ax.set_xlim(-1, 61)  # Barca's defending half (own goal on left)

    # Marker size from |OBV/xG|; non-zero floor so zero-threat FKs are visible.
    abs_v = per_fk["obv_xg"].abs()
    max_v = float(abs_v.max()) if len(abs_v) else 0.0
    sizes = 40 + (abs_v / max_v * 320) if max_v > 0 else pd.Series(80, index=per_fk.index)

    sc = pitch.scatter(
        per_fk["barca_x"], per_fk["barca_y"],
        ax=ax,
        s=sizes,
        c=per_fk["man_frac"],
        cmap=_MAN_CMAP, vmin=0.0, vmax=1.0,
        edgecolors="white", linewidths=0.6,
        alpha=0.85,
        zorder=4,
    )

    # Colorbar in the right margin — shows man-marking fraction with the system thresholds.
    cbar_ax = fig.add_axes([0.80, 0.30, 0.022, 0.45])
    cbar = fig.colorbar(sc, cax=cbar_ax)
    cbar.set_label("Man-marking fraction\n(engaged defenders keeping ≥ 1 attacker tight)", fontsize=9)
    cbar.ax.tick_params(labelsize=8)
    cbar.outline.set_visible(False)
    cbar.set_ticks([0.0, MAN_FRAC_LO, MAN_FRAC_HI, 1.0])
    cbar.set_ticklabels([
        "0%",
        f"{MAN_FRAC_LO:.0%}\nZonal ≤",
        f"{MAN_FRAC_HI:.0%}\nMan ≥",
        "100%",
    ])
    for frac in (MAN_FRAC_LO, MAN_FRAC_HI):
        cbar.ax.axhline(frac, color="white", linewidth=1.2)

    # Size reference (three markers) below the colorbar.
    if max_v > 0:
        ref_vals = [round(max_v * f, 3) for f in (0.2, 0.5, 1.0)]
        size_handles = [
            plt.scatter([], [], s=40 + f * 320, color=C_GREY, alpha=0.6,
                        edgecolors="white", linewidths=0.6,
                        label=f"|OBV/xG| ≈ {v:.2f}")
            for f, v in zip((0.2, 0.5, 1.0), ref_vals)
        ]
        ax.legend(
            handles=size_handles,
            loc="upper left", bbox_to_anchor=(1.20, 0.22),
            frameon=False, fontsize=8.5, labelspacing=1.4, handletextpad=1.2,
            title="Marker size", title_fontsize=9, borderaxespad=0.0,
        )

    ax.set_title(f"{TEAM} — defensive FK origins by man-marking fraction", loc="left")
    _caption(fig, "Barca defends the LEFT goal • colour = fraction of engaged defenders that man-marked (kept ≥1 attacker within 2.5 m across shot+reception) • marker size ∝ |OBV/xG|")
    plt.savefig(out, dpi=160)
    plt.close(fig)


def plot_per_match(match_df: pd.DataFrame, out: Path) -> None:
    if match_df.empty:
        return

    # If an opponent appears more than once, suffix with the date for clarity.
    op_counts = match_df["opponent"].value_counts()
    labels = [
        f"{r.opponent}  ({_short_date(r.date)})" if op_counts[r.opponent] > 1
        else r.opponent
        for r in match_df.itertuples()
    ]

    n_rows = len(match_df)
    fig, ax = plt.subplots(figsize=(8.5, max(4, 0.42 * n_rows)))

    y = list(range(n_rows))
    z = match_df["n_zonal"].values
    h = match_df["n_hybrid"].values
    m = match_df["n_man"].values

    ax.barh(y, z, color=C_ZONAL,  edgecolor="white", height=0.65, label="Zonal-Marking")
    ax.barh(y, h, left=z,         color=C_HYBRID, edgecolor="white", height=0.65, label="Hybrid")
    ax.barh(y, m, left=z + h,     color=C_MAN,    edgecolor="white", height=0.65, label="Man-Marking")

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Defensive FKs (count)")
    ax.set_xlim(0, match_df["n_fks"].max() * 1.08)
    ax.tick_params(left=False)
    ax.grid(axis="x", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_title(f"{TEAM} marking system per match")
    ax.legend(loc="lower right", frameon=False, ncol=3, fontsize=8.5,
              bbox_to_anchor=(1.0, -0.16))

    _caption(fig, "Sorted by mean man-marking fraction (top = most zonal, bottom = most man-marking)")
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight", dpi=160)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def run() -> None:
    _set_style()

    print("Collecting SkillCorner FK marking rows…")
    per_fk, per_def, per_player = collect_marking_rows()
    print(f"  {len(per_fk)} defensive FKs classified ({len(per_def)} defender-frames).")

    if not per_fk.empty:
        plot_system_frequency(per_fk,    OUT_DIR / "2_marking_system_frequency.png")
        plot_distance_by_system(per_def, OUT_DIR / "3_marking_distance_by_system.png")

        match_df = aggregate_per_match(per_fk)
        if not match_df.empty:
            plot_per_match(match_df, OUT_DIR / "5_marking_system_per_match.png")

        per_fk_obv = attach_obv(per_fk)
        print(f"  Paired with StatsBomb OBV/xG: {len(per_fk_obv)} / {len(per_fk)} FKs.")
        if not per_fk_obv.empty:
            plot_fk_locations_by_tightness(per_fk_obv, OUT_DIR / "6_fk_locations_by_tightness.png")

        print("\nMarking system breakdown:")
        for s in SYSTEM_ORDER:
            n = (per_fk["system"] == s).sum()
            pct = 100 * n / len(per_fk)
            print(f"  {s:14s} {n:3d}  ({pct:5.1f}%)")

        if not match_df.empty:
            print("\nPer-match breakdown:")
            print(f"  {'opponent':24s} {'date':10s} {'N':>3s}  Z   H   M   man")
            for _, r in match_df.iterrows():
                print(f"  {r['opponent']:24s} {r['date']:10s} {int(r['n_fks']):3d}  "
                      f"{int(r['n_zonal']):3d} {int(r['n_hybrid']):3d} {int(r['n_man']):3d}  "
                      f"{r['mean_man_frac']:5.0%}")

    player_roles = aggregate_player_roles(per_player)
    if not player_roles.empty:
        plot_player_roles(player_roles, OUT_DIR / "4_player_marking_roles.png")
        print(f"\nPer-player roles (min {PLAYER_MIN_FKS} engaged FKs):")
        for _, r in player_roles.sort_values("man_pct", ascending=False).iterrows():
            print(f"  {r['player']:22s} {int(r['n_man']):2d}/{int(r['n_fks']):2d} "
                  f"({r['man_pct']:5.0%})  median {r['median_dist_m']:4.1f} m   {r['role']}")

    print(f"\nPlots written to: {OUT_DIR}")


if __name__ == "__main__":
    run()
