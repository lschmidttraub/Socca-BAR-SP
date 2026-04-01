"""Comparison engine — run an analysis across teams and produce JSON output."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from . import data as _data
from .groups import Group, TOP_16
from .models import AnalysisResult


# ── Dict arithmetic ──────────────────────────────────────────────────

def sum_dicts(dicts: list[dict]) -> dict:
    """Element-wise sum of a list of dicts (recursively handles nested dicts)."""
    if not dicts:
        return {}
    result: dict = {}
    all_keys: set[str] = set()
    for d in dicts:
        all_keys.update(d.keys())
    for key in all_keys:
        values = [d[key] for d in dicts if key in d]
        if not values:
            continue
        if isinstance(values[0], dict):
            result[key] = sum_dicts(values)
        elif isinstance(values[0], (int, float)):
            result[key] = sum(values)
        else:
            result[key] = values[0]
    return result


def average_dicts(dicts: list[dict]) -> dict:
    """Element-wise average of a list of dicts (recursively handles nested dicts)."""
    if not dicts:
        return {}
    n = len(dicts)
    totals = sum_dicts(dicts)
    return _divide_dict(totals, n)


def _divide_dict(d: dict, n: int) -> dict:
    result: dict = {}
    for key, val in d.items():
        if isinstance(val, dict):
            result[key] = _divide_dict(val, n)
        elif isinstance(val, (int, float)):
            result[key] = round(val / n, 3)
        else:
            result[key] = val
    return result


# ── Core compare function ────────────────────────────────────────────

def compare(
    analysis_module: ModuleType,
    data_dir: Path,
    focus_team: str = "Barcelona",
    group: Group = TOP_16,
    per_team: bool = False,
) -> dict:
    """Run an analysis for *focus_team* and a comparison group.

    Parameters
    ----------
    analysis_module:
        A module from ``stats.analyses`` that exposes ``name``,
        ``analyze_match(events, team) -> dict``, and
        ``summarize(totals, n_matches) -> dict``.
    data_dir:
        Path to the StatsBomb data (directory or .zip).
    focus_team:
        The team to highlight.
    group:
        A ``Group`` instance that resolves to the comparison set.
    per_team:
        If True, include full per-team results in the output.

    Returns
    -------
    dict
        JSON-serialisable comparison result.
    """
    comparison_teams = group.resolve(data_dir)

    # Collect raw match-level dicts per team
    team_raws: dict[str, list[dict]] = defaultdict(list)

    for row, events in _data.iter_matches(data_dir):
        try:
            t1, t2 = _data.get_team_names(row)
        except ValueError:
            continue
        for t in (t1, t2):
            raw = analysis_module.analyze_match(events, t)
            team_raws[t].append(raw)

    # Aggregate per team
    team_results: dict[str, dict] = {}
    for t, raws in team_raws.items():
        totals = sum_dicts(raws)
        n_matches = len(raws)
        summarized = analysis_module.summarize(totals, n_matches)
        team_results[t] = AnalysisResult(
            analysis=analysis_module.name,
            team=t,
            matches=n_matches,
            metrics=summarized.get("metrics", {}),
            breakdowns=summarized.get("breakdowns", {}),
        ).to_dict()

    # Group average (exclude focus team from avg calculation)
    group_members = sorted(comparison_teams - {focus_team})
    group_dicts = [team_results[t] for t in group_members if t in team_results]
    if group_dicts:
        avg_metrics = average_dicts([d["metrics"] for d in group_dicts])
        avg_breakdowns = average_dicts([d["breakdowns"] for d in group_dicts])
        avg_matches = round(
            sum(d["matches"] for d in group_dicts) / len(group_dicts), 1
        )
    else:
        avg_metrics = {}
        avg_breakdowns = {}
        avg_matches = 0

    result: dict = {
        "analysis": analysis_module.name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": str(data_dir),
        "focus_team": focus_team,
        "focus": team_results.get(focus_team, {}),
        "comparison_group": group.name,
        "comparison_teams": group_members,
        "group_average": {
            "matches": avg_matches,
            "metrics": avg_metrics,
            "breakdowns": avg_breakdowns,
        },
    }

    if per_team:
        result["per_team"] = {
            t: team_results[t] for t in group_members if t in team_results
        }

    return result
