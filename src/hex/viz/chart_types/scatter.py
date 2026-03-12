"""Scatter plot renderer.

Produces matplotlib Figure objects for scatter-style visualizations
from row-oriented data dicts.
"""

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from hex.shared.models import ChartRequest
from hex.viz.config import ChartConfig
from hex.viz.styling import apply_theme, get_color_palette
from hex.viz.validators import detect_numeric_columns


def render(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a scatter plot.

    Auto-detects x and y numeric columns if not specified in the request.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered scatter plot.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    numeric_cols = detect_numeric_columns(data)
    x_col = request.x_column or (numeric_cols[0] if len(numeric_cols) >= 1 else list(data[0].keys())[0])
    y_col = (request.y_columns[0] if request.y_columns else None) or (
        numeric_cols[1] if len(numeric_cols) >= 2 else numeric_cols[0] if numeric_cols else list(data[0].keys())[1]
    )

    x_values = [float(row.get(x_col, 0)) for row in data]
    y_values = [float(row.get(y_col, 0)) for row in data]

    colors = get_color_palette(1)
    ax.scatter(x_values, y_values, color=colors[0], alpha=0.7, edgecolors="white", s=60)

    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or y_col)
    ax.set_title(request.title)

    apply_theme(fig, ax, config.theme)
    return fig
