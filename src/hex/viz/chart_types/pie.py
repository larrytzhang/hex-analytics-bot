"""Pie and donut chart renderers.

Produces matplotlib Figure objects for pie-style visualizations
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
    """Render a pie chart.

    Auto-detects label (categorical) and value (numeric) columns
    if not specified in the request.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered pie chart.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    label_col = request.x_column or _detect_label(data)
    value_col = (request.y_columns[0] if request.y_columns else None) or _detect_value(data)

    labels = [str(row.get(label_col, "")) for row in data]
    values = [float(row.get(value_col, 0)) for row in data]
    colors = get_color_palette(len(labels))

    ax.pie(values, labels=labels, colors=colors, autopct="%1.1f%%", startangle=90)
    ax.set_title(request.title)

    apply_theme(fig, ax, config.theme)
    return fig


def render_donut(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a donut chart (pie chart with center hole).

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered donut chart.
    """
    fig, ax = plt.subplots(figsize=(config.width, config.height))

    label_col = request.x_column or _detect_label(data)
    value_col = (request.y_columns[0] if request.y_columns else None) or _detect_value(data)

    labels = [str(row.get(label_col, "")) for row in data]
    values = [float(row.get(value_col, 0)) for row in data]
    colors = get_color_palette(len(labels))

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.85,
    )

    # Draw center circle for donut effect
    centre_circle = plt.Circle((0, 0), 0.70, fc="white")
    ax.add_artist(centre_circle)

    ax.set_title(request.title)

    apply_theme(fig, ax, config.theme)
    return fig


def _detect_label(data: list[dict[str, Any]]) -> str:
    """Auto-detect the label (categorical) column for pie slices.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Name of the detected categorical column.
    """
    cats = detect_categorical_columns(data)
    return cats[0] if cats else list(data[0].keys())[0]


def _detect_value(data: list[dict[str, Any]]) -> str:
    """Auto-detect the value (numeric) column for pie slice sizes.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Name of the detected numeric column.
    """
    nums = detect_numeric_columns(data)
    if nums:
        return nums[0]
    keys = list(data[0].keys())
    return keys[1] if len(keys) > 1 else keys[0]
