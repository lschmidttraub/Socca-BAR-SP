"""Physicality / height analysis across teams and per match for Barcelona.

Only matches from ``league_phase.zip`` and ``playoffs.zip`` are used;
``last16.zip`` contains no lineup files and is therefore skipped.

Plots produced
--------------
all_teams_top6_height.png
    All-team vertical bar chart: mean height of the 6 tallest outfield
    players (unique, across all their appearances) per team.

barca_match_height.png
    Per-match grouped bar chart for Barcelona vs each opponent — mean
    height of the 6 tallest outfield players deployed in that game.
"""

from collections import defaultdict
from pathlib import Path
import json
import zipfile

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from stats.data import _find_matches_csv, _read_matches_csv
    from stats.viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig
else:
    from ..data import _find_matches_csv, _read_matches_csv
    from ..viz.style import FOCUS_COLOR, AVG_COLOR, apply_theme, save_fig

ASSETS_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent / "assets" / "physicality"
)
DATA = Path(__file__).resolve().parent.parent.parent.parent / "data" / "statsbomb"

TEAM = "Barcelona"
# Zips that contain lineup files (last16.zip deliberately excluded)
LINEUP_ZIPS = ("league_phase.zip", "playoffs.zip")

TOP_N = 6  # tallest N outfield players to average

AVG_LABEL = "League Avg"
AVG_BAR_COLOR = "#f4a261"


# ── Lineup loading ────────────────────────────────────────────────────


def _load_lineup_from_zip(zip_path: Path, match_id: str) -> list[dict] | None:
    """Return parsed lineup JSON for *match_id* from *zip_path*, or None."""
    target = f"{match_id}_lineups.json"
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.rsplit("/", 1)[-1] == target:
                with zf.open(name) as fh:
                    return json.load(fh)
    return None


def _load_lineup(data_dir: Path, match_id: str) -> list[dict] | None:
    """Find lineup data for *match_id* across the LINEUP_ZIPS archives."""
    for zip_name in LINEUP_ZIPS:
        zip_path = data_dir / zip_name
        if not zip_path.is_file():
            continue
        result = _load_lineup_from_zip(zip_path, match_id)
        if result is not None:
            return result
    return None


# ── Team-name matching ────────────────────────────────────────────────


def _match_lineup_to_csv(
    lineup: list[dict], home_csv: str, away_csv: str
) -> dict[str, list[dict]]:
    """Map each of the two CSV team names to its lineup player list.

    Uses substring matching (case-insensitive) with process-of-elimination
    fallback when neither name matches exactly.
    """
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
        # partial word overlap
        a_words = set(a.split())
        b_words = set(b.split())
        return len(a_words & b_words)

    # Assign home
    scores_home = {sb: _score(home_csv, sb) for sb in sb_names}
    best_sb_home = max(scores_home, key=scores_home.get)

    # Away gets the other one
    best_sb_away = next(sb for sb in sb_names if sb != best_sb_home)

    return {
        home_csv: players_by_sb[best_sb_home],
        away_csv: players_by_sb[best_sb_away],
    }


# ── Height helpers ────────────────────────────────────────────────────


def _is_goalkeeper(player: dict) -> bool:
    return any(
        "Goalkeeper" in pos.get("position", "")
        for pos in player.get("positions", [])
    )


def _actually_played(player: dict) -> bool:
    """Player appeared on the pitch ↔ positions list is non-empty."""
    return len(player.get("positions", [])) > 0


def _top_n_mean(heights: list[float], n: int = TOP_N) -> float | None:
    """Mean of the *n* largest values, or None if fewer than *n* available."""
    top = sorted(heights, reverse=True)[:n]
    return float(np.mean(top)) if len(top) >= n else None


# ── Data collection ───────────────────────────────────────────────────


def _collect(
    data_dir: Path,
) -> tuple[dict[str, float], list[dict]]:
    """Return all-team height metric and per-match Barcelona data.

    all_team_metric : {csv_team_name: mean_height_of_top6_unique_players}
    barca_matches   : [{"label": "vs X", "barca": h, "opp": h}, ...]
    """
    csv_path = _find_matches_csv(data_dir)
    if csv_path is None:
        raise FileNotFoundError(
            f"matches.csv not found in {data_dir} or {data_dir.parent}"
        )
    rows = _read_matches_csv(csv_path)

    # {team_csv: {player_id: player_height}}  — deduplicated by player_id
    team_players: dict[str, dict[int, float]] = defaultdict(dict)
    barca_matches: list[dict] = []

    for row in rows:
        match_id = row.get("statsbomb", "").strip()
        if not match_id:
            continue

        lineup = _load_lineup(data_dir, match_id)
        if lineup is None:
            continue  # no lineup file (last16 or missing)

        home_csv = row.get("home", "").strip()
        away_csv = row.get("away", "").strip()
        if not home_csv or not away_csv:
            continue

        mapping = _match_lineup_to_csv(lineup, home_csv, away_csv)
        if not mapping:
            continue

        # Accumulate per-team unique player heights (all-team chart)
        for csv_name, players in mapping.items():
            for p in players:
                if not _actually_played(p) or _is_goalkeeper(p):
                    continue
                h = p.get("player_height")
                if h:
                    pid = p["player_id"]
                    team_players[csv_name][pid] = float(h)

        # Per-match Barcelona data (match-height chart)
        barca_csv = next(
            (n for n in [home_csv, away_csv] if "Barcelona" in n), None
        )
        if barca_csv:
            opp_csv = away_csv if barca_csv == home_csv else home_csv
            barca_pl = mapping.get(barca_csv, [])
            opp_pl = mapping.get(opp_csv, [])

            barca_h_list = [
                float(p["player_height"])
                for p in barca_pl
                if _actually_played(p) and not _is_goalkeeper(p) and p.get("player_height")
            ]
            opp_h_list = [
                float(p["player_height"])
                for p in opp_pl
                if _actually_played(p) and not _is_goalkeeper(p) and p.get("player_height")
            ]

            barca_h = _top_n_mean(barca_h_list)
            opp_h = _top_n_mean(opp_h_list)
            if barca_h is not None and opp_h is not None:
                barca_matches.append(
                    {"label": f"vs {opp_csv}", "barca": barca_h, "opp": opp_h}
                )

    # Compute all-team metric: mean height of top-N unique players per team
    all_team_metric: dict[str, float] = {}
    for team, pid_map in team_players.items():
        mean_h = _top_n_mean(list(pid_map.values()))
        if mean_h is not None:
            all_team_metric[team] = mean_h

    return all_team_metric, barca_matches


# ── Plot 1: All-team comparison ───────────────────────────────────────


def _plot_all_teams(
    all_team_metric: dict[str, float],
    focus_team: str,
    output_path: Path,
) -> None:
    """Bar chart: mean height of top-N outfield players per team."""
    items = sorted(all_team_metric.items(), key=lambda kv: kv[1], reverse=True)
    teams = [t for t, _ in items]
    vals = [v for _, v in items]

    league_avg = float(np.mean(vals))

    # Insert league average at its sorted position
    inserted = False
    for i, v in enumerate(vals):
        if league_avg >= v:
            teams.insert(i, AVG_LABEL)
            vals.insert(i, league_avg)
            inserted = True
            break
    if not inserted:
        teams.append(AVG_LABEL)
        vals.append(league_avg)

    colors = [
        AVG_BAR_COLOR if t == AVG_LABEL
        else FOCUS_COLOR if t == focus_team
        else AVG_COLOR
        for t in teams
    ]

    n = len(teams)
    fig, ax = plt.subplots(figsize=(max(14.0, n * 0.56), 7))
    x = np.arange(n)
    bars = ax.bar(x, vals, color=colors, edgecolor="white", linewidth=0.5, width=0.72)

    y_min = min(vals) - 2.0
    y_max = max(vals)
    span = y_max - y_min if y_max > y_min else 1.0
    for bar, val in zip(bars, vals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + span * 0.01,
            f"{val:.1f}",
            ha="center", va="bottom", fontsize=8,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(teams, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Mean height (cm)")
    ax.set_title(
        f"Mean Height of {TOP_N} Tallest Outfield Players per Team\n"
        "(unique players who appeared in at least one match)",
        fontsize=14, fontweight="bold",
    )
    ax.set_ylim(y_min, y_max + span * 0.22)
    ax.legend(
        handles=[
            Patch(facecolor=FOCUS_COLOR, label=focus_team),
            Patch(facecolor=AVG_BAR_COLOR, label=AVG_LABEL),
            Patch(facecolor=AVG_COLOR, label="Other teams"),
        ],
        loc="upper right", frameon=True, fontsize=9,
    )

    save_fig(fig, output_path)
    print(f"    -> {output_path.name}")


# ── Plot 2: Per-match Barcelona comparison ────────────────────────────


def _plot_barca_matches(
    matches: list[dict],
    focus_team: str,
    output_path: Path,
) -> None:
    """Grouped bar chart: per-match top-N height, Barcelona vs opponent."""
    labels = [m["label"] for m in matches]
    barca_vals = [m["barca"] for m in matches]
    opp_vals = [m["opp"] for m in matches]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.3), 6))
    ax.bar(x - width / 2, barca_vals, width, label=focus_team, color=FOCUS_COLOR)
    ax.bar(x + width / 2, opp_vals, width, label="Opponent", color=AVG_COLOR, alpha=0.7)

    all_vals = barca_vals + opp_vals
    y_min = min(all_vals) - 2.0
    y_max = max(all_vals)
    span = y_max - y_min if y_max > y_min else 1.0

    for xi, (bv, ov) in enumerate(zip(barca_vals, opp_vals)):
        ax.text(xi - width / 2, bv + span * 0.01, f"{bv:.1f}",
                ha="center", va="bottom", fontsize=7.5)
        ax.text(xi + width / 2, ov + span * 0.01, f"{ov:.1f}",
                ha="center", va="bottom", fontsize=7.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Mean height (cm)")
    ax.set_ylim(y_min, y_max + span * 0.18)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title(
        f"{focus_team} — Mean Height of {TOP_N} Tallest Outfield Players per Match",
        fontsize=14, fontweight="bold",
    )

    save_fig(fig, output_path)
    print(f"    -> {output_path.name}")


# ── Entry point ───────────────────────────────────────────────────────


def run(
    focus_team: str = TEAM,
    data_dir: Path = DATA,
    output_dir: Path | None = None,
) -> None:
    """Generate physicality / height charts."""
    if output_dir is None:
        output_dir = ASSETS_ROOT

    apply_theme()

    print("Loading lineup data…")
    all_team_metric, barca_matches = _collect(data_dir)
    print(
        f"  {len(all_team_metric)} teams with height data · "
        f"{len(barca_matches)} Barcelona matches"
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nGenerating charts…")
    if all_team_metric:
        _plot_all_teams(all_team_metric, focus_team, output_dir / "all_teams_top6_height.png")
    else:
        print("  No all-team height data found.")

    if barca_matches:
        _plot_barca_matches(
            barca_matches, focus_team, output_dir / "barca_match_height.png"
        )
    else:
        print("  No Barcelona matches with lineup data found.")

    print(f"\nDone — charts saved to {output_dir}/")


if __name__ == "__main__":
    run()