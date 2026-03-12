"""Line chart renderers (single-line and multi-line).

Produces matplotlib Figure objects for line-style visualizations
from row-oriented data dicts.
"""

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from hex.shared.models import ChartRequest
from hex.viz.config import ChartConfig
from hex.viz.styling import apply_theme, get_color_palette
from hex.viz.validators import detect_categorical_columns, detect_numeric_columns


def render(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a single-line chart.

    Auto-detects x (categorical/datetime) and y (numeric) columns
    if not specified in the request.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered line chart.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    x_col = request.x_column or _detect_x(data)
    y_col = (request.y_columns[0] if request.y_columns else None) or _detect_y(data)

    x_values = [row.get(x_col, "") for row in data]
    y_values = [float(row.get(y_col, 0)) for row in data]

    colors = get_color_palette(1)
    ax.plot(x_values, y_values, color=colors[0], marker="o", markersize=4, linewidth=2)

    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or y_col)
    ax.set_title(request.title)

    if len(x_values) > 6:
        plt.xticks(rotation=45, ha="right")

    apply_theme(fig, ax, config.theme)
    return fig


def render_multi(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a multi-line chart with multiple y-columns.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with multiple lines plotted.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    x_col = request.x_column or _detect_x(data)
    y_cols = request.y_columns or detect_numeric_columns(data)

    x_values = [row.get(x_col, "") for row in data]
    colors = get_color_palette(len(y_cols))

    for i, y_col in enumerate(y_cols):
        y_values = [float(row.get(y_col, 0)) for row in data]
        ax.plot(x_values, y_values, color=colors[i], marker="o", markersize=4,
                linewidth=2, label=y_col)

    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or "Value")
    ax.set_title(request.title)
    ax.legend()

    if len(x_values) > 6:
        plt.xticks(rotation=45, ha="right")

    apply_theme(fig, ax, config.theme)
    return fig


def _detect_x(data: list[dict[str, Any]]) -> str:
    """Auto-detect the best x-axis column (categorical or datetime).

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Name of the detected x-axis column.
    """
    cats = detect_categorical_columns(data)
    if cats:
        return cats[0]
    return list(data[0].keys())[0] if data else ""


def _detect_y(data: list[dict[str, Any]]) -> str:
    """Auto-detect the best y-axis (numeric) column.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Name of the detected numeric column.
    """
    nums = detect_numeric_columns(data)
    if nums:
        return nums[0]
    keys = list(data[0].keys()) if data else []
    return keys[1] if len(keys) > 1 else keys[0] if keys else ""
