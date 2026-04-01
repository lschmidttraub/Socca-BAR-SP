"""Pitch-based visualisations using mplsoccer.

All functions accept raw StatsBomb event lists and produce matplotlib
figures.  Coordinates are in StatsBomb's 120 x 80 yard system.
"""

import matplotlib.pyplot as plt
import numpy as np
from mplsoccer import Pitch, VerticalPitch

from . import style


def event_map(
    events: list[dict],
    title: str = "",
    color: str = style.FOCUS_COLOR,
    size_by_xg: bool = False,
    vertical: bool = False,
    half: bool = False,
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot event locations on a pitch.

    Parameters
    ----------
    events:
        StatsBomb events that have a ``location`` field.
    title:
        Plot title.
    color:
        Marker colour.
    size_by_xg:
        If True, scale marker size by ``shot.statsbomb_xg``.
    vertical:
        Use a vertical pitch orientation.
    half:
        Show only the attacking half.
    ax:
        Optional axes to draw on.  If None a new figure is created.

    Returns
    -------
    (fig, ax)
    """
    PitchClass = VerticalPitch if vertical else Pitch
    pitch = PitchClass(
        pitch_type="statsbomb",
        half=half,
        pitch_color="white",
        line_color="#c7d5cc",
    )

    if ax is None:
        fig, ax = pitch.draw(figsize=(12, 8))
    else:
        fig = ax.figure
        pitch.draw(ax=ax)

    xs, ys, sizes = [], [], []
    for e in events:
        loc = e.get("location")
        if not loc:
            continue
        xs.append(loc[0])
        ys.append(loc[1])
        if size_by_xg:
            xg = e.get("shot", {}).get("statsbomb_xg", 0.02)
            sizes.append(max(xg * 500, 20))
        else:
            sizes.append(60)

    if xs:
        pitch.scatter(
            xs, ys, s=sizes, ax=ax,
            color=color, edgecolors="white", linewidth=0.6,
            alpha=0.8, zorder=2,
        )

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    return fig, ax


def heatmap(
    events: list[dict],
    title: str = "",
    cmap: str = "Reds",
    vertical: bool = False,
    half: bool = False,
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Kernel density heatmap of event locations on a pitch.

    Parameters
    ----------
    events:
        StatsBomb events with ``location`` fields.
    title:
        Plot title.
    cmap:
        Matplotlib colourmap name.
    vertical / half:
        Pitch orientation options.
    ax:
        Optional axes.
    """
    PitchClass = VerticalPitch if vertical else Pitch
    pitch = PitchClass(
        pitch_type="statsbomb",
        half=half,
        pitch_color="white",
        line_color="#c7d5cc",
    )

    if ax is None:
        fig, ax = pitch.draw(figsize=(12, 8))
    else:
        fig = ax.figure
        pitch.draw(ax=ax)

    xs = [e["location"][0] for e in events if e.get("location")]
    ys = [e["location"][1] for e in events if e.get("location")]

    if xs:
        pitch.kdeplot(xs, ys, ax=ax, cmap=cmap, fill=True, levels=50, alpha=0.7)

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    return fig, ax


def pass_map(
    events: list[dict],
    title: str = "",
    completed_color: str = style.FOCUS_COLOR,
    incomplete_color: str = style.NEUTRAL_COLOR,
    vertical: bool = False,
    half: bool = False,
    ax: plt.Axes | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot passes as arrows on a pitch.

    Parameters
    ----------
    events:
        StatsBomb pass events (type id 30) with ``location`` and
        ``pass.end_location``.
    title:
        Plot title.
    completed_color / incomplete_color:
        Arrow colours for completed and incomplete passes.
    vertical / half:
        Pitch orientation options.
    ax:
        Optional axes.
    """
    PitchClass = VerticalPitch if vertical else Pitch
    pitch = PitchClass(
        pitch_type="statsbomb",
        half=half,
        pitch_color="white",
        line_color="#c7d5cc",
    )

    if ax is None:
        fig, ax = pitch.draw(figsize=(12, 8))
    else:
        fig = ax.figure
        pitch.draw(ax=ax)

    for e in events:
        loc = e.get("location")
        end = e.get("pass", {}).get("end_location")
        if not loc or not end:
            continue
        completed = e.get("pass", {}).get("outcome") is None
        color = completed_color if completed else incomplete_color
        alpha = 0.9 if completed else 0.4
        pitch.arrows(
            loc[0], loc[1], end[0], end[1], ax=ax,
            color=color, width=2, headwidth=6, headlength=4,
            alpha=alpha, zorder=2,
        )

    if title:
        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    return fig, ax
