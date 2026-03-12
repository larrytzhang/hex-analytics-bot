"""Table-as-image renderer.

Produces a matplotlib Figure containing a styled table from
row-oriented data dicts, rendered as an image (no axes).
"""

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from hex.shared.models import ChartRequest
from hex.viz.config import ChartConfig
from hex.viz.styling import THEMES


def render(data: list[dict[str, Any]], request: ChartRequest, config: ChartConfig) -> Figure:
    """Render a styled table as an image.

    Creates a matplotlib table from the data and renders it without axes.
    Limits to 20 rows for readability.

    Args:
        data:    Row-oriented list of dicts.
        request: ChartRequest with chart configuration.
        config:  ChartConfig with rendering parameters.

    Returns:
        A matplotlib Figure with the rendered table image.
    """
    # Limit rows for readability
    display_data = data[:20]
    columns = list(display_data[0].keys()) if display_data else []

    fig, ax = plt.subplots(figsize=(config.width, config.height))
    ax.axis("off")

    # Build cell data
    cell_text = [[str(row.get(col, "")) for col in columns] for row in display_data]

    theme = THEMES.get(config.theme, THEMES["professional_light"])

    table = ax.table(
        cellText=cell_text,
        colLabels=columns,
        cellLoc="center",
        loc="center",
    )

    # Style the table
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.5)

    # Style header cells
    for j in range(len(columns)):
        cell = table[0, j]
        cell.set_facecolor("#4C78A8")
        cell.set_text_props(color="white", fontweight="bold")

    # Style data cells with alternating rows
    for i in range(1, len(display_data) + 1):
        for j in range(len(columns)):
            cell = table[i, j]
            if i % 2 == 0:
                cell.set_facecolor("#F0F4F8")
            else:
                cell.set_facecolor("#FFFFFF")

    if request.title:
        ax.set_title(request.title, fontsize=14, color=theme["text_color"], pad=20)

    fig.tight_layout()
    return fig
