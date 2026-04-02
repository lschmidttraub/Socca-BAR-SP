"""Statistical comparison charts using seaborn and matplotlib."""

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from . import style


def metric_bars(
    compare_result: dict,
    metrics: list[str] | None = None,
    title: str = "",
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Grouped bar chart: focus team vs group average for selected metrics.

    Parameters
    ----------
    compare_result:
        Output of ``stats.compare()``.
    metrics:
        Which metric keys to plot.  If None, plots all numeric metrics.
    title:
        Plot title.  Defaults to ``"<analysis>: <focus_team> vs <group>"``.
    ax:
        Optional axes.
    """
    style.apply_theme()

    focus = compare_result.get("focus", {})
    avg = compare_result.get("group_average", {})
    focus_m = focus.get("metrics", {})
    avg_m = avg.get("metrics", {})
    focus_team = compare_result.get("focus_team", "Focus")
    group_name = compare_result.get("comparison_group", "Group")

    if metrics is None:
        metrics = [k for k, v in focus_m.items() if isinstance(v, (int, float))]

    labels = metrics
    focus_vals = [focus_m.get(m, 0) for m in metrics]
    avg_vals = [avg_m.get(m, 0) for m in metrics]

    x = np.arange(len(labels))
    width = 0.35

    if ax is None:
        fig, ax = plt.subplots(figsize=(max(10, len(labels) * 1.2), 6))
    else:
        fig = ax.figure

    ax.bar(x - width / 2, focus_vals, width, label=focus_team,
           color=style.FOCUS_COLOR)
    ax.bar(x + width / 2, avg_vals, width, label=f"Avg ({group_name})",
           color=style.AVG_COLOR, alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.legend()
    if not title:
        analysis = compare_result.get("analysis", "")
        title = f"{analysis}: {focus_team} vs {group_name} avg"
    ax.set_title(title)
    return fig, ax


def breakdown_bars(
    compare_result: dict,
    breakdown_key: str,
    metric_key: str = "total",
    title: str = "",
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Grouped bar chart comparing a breakdown category.

    Parameters
    ----------
    compare_result:
        Output of ``stats.compare()``.
    breakdown_key:
        Key in ``breakdowns``, e.g. ``"by_side"``, ``"by_pitch_third"``.
    metric_key:
        Which value to plot within each breakdown category.
    title:
        Plot title.
    ax:
        Optional axes.
    """
    style.apply_theme()

    focus = compare_result.get("focus", {})
    avg = compare_result.get("group_average", {})
    focus_bd = focus.get("breakdowns", {}).get(breakdown_key, {})
    avg_bd = avg.get("breakdowns", {}).get(breakdown_key, {})
    focus_team = compare_result.get("focus_team", "Focus")
    group_name = compare_result.get("comparison_group", "Group")

    categories = sorted(set(focus_bd.keys()) | set(avg_bd.keys()))
    focus_vals = [focus_bd.get(c, {}).get(metric_key, 0) for c in categories]
    avg_vals = [avg_bd.get(c, {}).get(metric_key, 0) for c in categories]

    x = np.arange(len(categories))
    width = 0.35

    if ax is None:
        fig, ax = plt.subplots(figsize=(max(8, len(categories) * 1.5), 6))
    else:
        fig = ax.figure

    ax.bar(x - width / 2, focus_vals, width, label=focus_team,
           color=style.FOCUS_COLOR)
    ax.bar(x + width / 2, avg_vals, width, label=f"Avg ({group_name})",
           color=style.AVG_COLOR, alpha=0.7)

    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45, ha="right")
    ax.legend()
    if not title:
        title = f"{breakdown_key}: {focus_team} vs {group_name} avg"
    ax.set_title(title)
    return fig, ax


def metric_radar(
    compare_result: dict,
    metrics: list[str],
    labels: list[str] | None = None,
    title: str = "",
) -> tuple[plt.Figure, plt.Axes]:
    """Radar chart comparing focus team to group average.

    Parameters
    ----------
    compare_result:
        Output of ``stats.compare()``.
    metrics:
        Which metric keys to include as radar spokes.
    labels:
        Human-readable spoke labels (same length as *metrics*).
        Defaults to the metric keys.
    title:
        Plot title.
    """
    style.apply_theme()

    focus_m = compare_result.get("focus", {}).get("metrics", {})
    avg_m = compare_result.get("group_average", {}).get("metrics", {})
    focus_team = compare_result.get("focus_team", "Focus")
    group_name = compare_result.get("comparison_group", "Group")

    if labels is None:
        labels = metrics

    focus_vals = [focus_m.get(m, 0) for m in metrics]
    avg_vals = [avg_m.get(m, 0) for m in metrics]

    # Normalise to 0-1 range using max of both series per metric
    max_vals = [max(f, a, 1e-9) for f, a in zip(focus_vals, avg_vals)]
    focus_norm = [f / m for f, m in zip(focus_vals, max_vals)]
    avg_norm = [a / m for a, m in zip(avg_vals, max_vals)]

    n = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    # Close the polygon
    focus_norm += focus_norm[:1]
    avg_norm += avg_norm[:1]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.plot(angles, focus_norm, "o-", color=style.FOCUS_COLOR,
            linewidth=2, label=focus_team)
    ax.fill(angles, focus_norm, color=style.FOCUS_COLOR, alpha=0.15)
    ax.plot(angles, avg_norm, "o-", color=style.AVG_COLOR,
            linewidth=2, label=f"Avg ({group_name})")
    ax.fill(angles, avg_norm, color=style.AVG_COLOR, alpha=0.10)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 1.1)
    ax.set_yticklabels([])
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    if not title:
        title = f"{focus_team} vs {group_name} avg"
    ax.set_title(title, y=1.08, fontweight="bold")
    return fig, ax


def team_rank_bars(
    compare_result: dict,
    metric: str,
    title: str = "",
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Horizontal bar chart ranking all teams by a single metric.

    Requires ``per_team=True`` in the compare result.

    Parameters
    ----------
    compare_result:
        Output of ``stats.compare(per_team=True)``.
    metric:
        Which metric key to rank by.
    title:
        Plot title.
    ax:
        Optional axes.
    """
    style.apply_theme()

    per_team = compare_result.get("per_team", {})
    focus_team = compare_result.get("focus_team", "Focus")

    # Include focus team in the ranking
    focus_data = compare_result.get("focus", {})
    all_teams = {**per_team}
    if focus_data:
        all_teams[focus_team] = focus_data

    ranked = sorted(all_teams.items(),
                    key=lambda item: item[1].get("metrics", {}).get(metric, 0),
                    reverse=True)
    names = [t for t, _ in ranked]
    vals = [d.get("metrics", {}).get(metric, 0) for _, d in ranked]
    colors = [style.FOCUS_COLOR if t == focus_team else style.AVG_COLOR
              for t in names]

    if ax is None:
        fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.4)))
    else:
        fig = ax.figure

    bars = ax.barh(names, vals, color=colors)
    ax.invert_yaxis()
    ax.set_xlabel(metric)
    if not title:
        title = f"Team ranking: {metric}"
    ax.set_title(title)
    return fig, ax