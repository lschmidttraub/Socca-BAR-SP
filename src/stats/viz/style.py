"""Shared theme, colours, and styling helpers."""

import matplotlib as mpl
import matplotlib.pyplot as plt

# ── Colour palette ───────────────────────────────────────────────────

FOCUS_COLOR = "#4575b4"       # Barcelona / focus team (blue)
AVG_COLOR = "#d73027"         # comparison group / opponent (red)
POSITIVE_COLOR = "#1a9850"    # above average / good
NEGATIVE_COLOR = "#d73027"    # below average / bad
NEUTRAL_COLOR = "#878787"     # neutral / grid

# Extended palette for per-team charts (up to 8 distinct colours)
TEAM_PALETTE = [
    "#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
    "#ff7f00", "#a65628", "#f781bf", "#999999",
]

# ── Theme ────────────────────────────────────────────────────────────

def apply_theme() -> None:
    """Apply a clean, publication-ready matplotlib theme."""
    mpl.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": NEUTRAL_COLOR,
        "axes.grid": True,
        "grid.color": "#e0e0e0",
        "grid.linewidth": 0.5,
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "xtick.color": NEUTRAL_COLOR,
        "ytick.color": NEUTRAL_COLOR,
        "legend.frameon": False,
        "legend.fontsize": 10,
        "figure.dpi": 150,
    })


# ── Helpers ──────────────────────────────────────────────────────────

def save_fig(fig: plt.Figure, path, tight: bool = True) -> None:
    """Save figure, creating parent directories if needed."""
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if tight:
        fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
