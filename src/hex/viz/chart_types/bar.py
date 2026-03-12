"""Bar chart renderers (simple, grouped, and stacked).

Produces matplotlib Figure objects for bar-style visualizations
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
    """Render a simple bar chart.

    Auto-detects x (categorical) and y (numeric) columns if not specified
    in the request.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered bar chart.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    x_col = request.x_column or _detect_x(data)
    y_col = (request.y_columns[0] if request.y_columns else None) or _detect_y(data)

    x_values = [str(row.get(x_col, "")) for row in data]
    y_values = [float(row.get(y_col, 0)) for row in data]

    colors = get_color_palette(1)
    ax.bar(x_values, y_values, color=colors[0])

    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or y_col)
    ax.set_title(request.title)

    # Rotate labels if many categories
    if len(x_values) > 6:
        plt.xticks(rotation=45, ha="right")

    apply_theme(fig, ax, config.theme)
    return fig


def render_grouped(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a grouped bar chart with multiple y-columns side by side.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered grouped bar chart.
    """
    import numpy as np

    fig, ax = plt.subplots(figsize=(config.width, config.height))

    x_col = request.x_column or _detect_x(data)
    y_cols = request.y_columns or detect_numeric_columns(data)

    x_labels = [str(row.get(x_col, "")) for row in data]
    x_positions = np.arange(len(x_labels))
    bar_width = 0.8 / max(len(y_cols), 1)
    colors = get_color_palette(len(y_cols))

    for i, y_col in enumerate(y_cols):
        values = [float(row.get(y_col, 0)) for row in data]
        offset = (i - len(y_cols) / 2 + 0.5) * bar_width
        ax.bar(x_positions + offset, values, bar_width, label=y_col, color=colors[i])

    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels)
    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or "Value")
    ax.set_title(request.title)
    ax.legend()

    if len(x_labels) > 6:
        plt.xticks(rotation=45, ha="right")

    apply_theme(fig, ax, config.theme)
    return fig


def render_stacked(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a stacked bar chart with multiple y-columns stacked.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered stacked bar chart.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    x_col = request.x_column or _detect_x(data)
    y_cols = request.y_columns or detect_numeric_columns(data)

    x_labels = [str(row.get(x_col, "")) for row in data]
    colors = get_color_palette(len(y_cols))
    bottom = [0.0] * len(data)

    for i, y_col in enumerate(y_cols):
        values = [float(row.get(y_col, 0)) for row in data]
        ax.bar(x_labels, values, bottom=bottom, label=y_col, color=colors[i])
        bottom = [b + v for b, v in zip(bottom, values)]

    ax.set_xlabel(request.x_label or x_col)
    ax.set_ylabel(request.y_label or "Value")
    ax.set_title(request.title)
    ax.legend()

    if len(x_labels) > 6:
        plt.xticks(rotation=45, ha="right")

    apply_theme(fig, ax, config.theme)
    return fig


def _detect_x(data: list[dict[str, Any]]) -> str:
    """Auto-detect the best x-axis (categorical) column.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Name of the detected categorical column, or the first column.
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
        Name of the detected numeric column, or the second column.
    """
    nums = detect_numeric_columns(data)
    if nums:
        return nums[0]
    keys = list(data[0].keys()) if data else []
    return keys[1] if len(keys) > 1 else keys[0] if keys else ""
