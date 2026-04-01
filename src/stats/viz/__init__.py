"""Visualization framework for set piece analysis.

Uses mplsoccer for pitch plots and seaborn for statistical charts.
"""

from .style import FOCUS_COLOR, AVG_COLOR, apply_theme
from .pitch_plots import event_map, heatmap, pass_map
from .charts import metric_bars, metric_radar, breakdown_bars
