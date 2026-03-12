"""Chart styling and theming for the visualization engine.

Provides theme definitions and an apply_theme function to configure
matplotlib figures with consistent, professional-looking styles.
"""

from typing import Any

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure


# ── Theme definitions ──
THEMES: dict[str, dict[str, Any]] = {
    "professional_light": {
        "background_color": "#FFFFFF",
        "text_color": "#333333",
        "grid_color": "#E0E0E0",
        "grid_alpha": 0.7,
        "font_size": 11,
        "title_size": 14,
        "spine_visible": False,
    },
    "dark": {
        "background_color": "#1E1E2E",
        "text_color": "#FFFFFF",
        "grid_color": "#444444",
        "grid_alpha": 0.5,
        "font_size": 11,
        "title_size": 14,
        "spine_visible": False,
    },
}

# ── Color palettes ──
COLOR_PALETTE = [
    "#4C78A8",  # Steel blue
    "#F58518",  # Orange
    "#E45756",  # Red
    "#72B7B2",  # Teal
    "#54A24B",  # Green
    "#EECA3B",  # Yellow
    "#B279A2",  # Purple
    "#FF9DA6",  # Pink
    "#9D755D",  # Brown
    "#BAB0AC",  # Gray
]


def get_color_palette(n: int = 10) -> list[str]:
    """Return a list of n colors from the default palette.

    Cycles through the palette if n exceeds the number of defined colors.

    Args:
        n: Number of colors needed.

    Returns:
        List of hex color strings.
    """
    return [COLOR_PALETTE[i % len(COLOR_PALETTE)] for i in range(n)]


def apply_theme(fig: Figure, ax: Axes, theme_name: str = "professional_light") -> None:
    """Apply a visual theme to a matplotlib figure and axes.

    Sets background colors, text colors, grid style, font sizes,
    and spine visibility based on the specified theme.

    Args:
        fig:        The matplotlib Figure to style.
        ax:         The matplotlib Axes to style.
        theme_name: Name of the theme from the THEMES dict.
                    Defaults to "professional_light".
    """
    theme = THEMES.get(theme_name, THEMES["professional_light"])

    # Background
    fig.patch.set_facecolor(theme["background_color"])
    ax.set_facecolor(theme["background_color"])

    # Text colors
    ax.title.set_color(theme["text_color"])
    ax.xaxis.label.set_color(theme["text_color"])
    ax.yaxis.label.set_color(theme["text_color"])
    ax.tick_params(colors=theme["text_color"])

    # Grid
    ax.grid(True, color=theme["grid_color"], alpha=theme["grid_alpha"], linestyle="--")
    ax.set_axisbelow(True)

    # Spines
    for spine in ax.spines.values():
        spine.set_visible(theme["spine_visible"])

    # Font sizes
    ax.title.set_fontsize(theme["title_size"])
    ax.xaxis.label.set_fontsize(theme["font_size"])
    ax.yaxis.label.set_fontsize(theme["font_size"])

    fig.tight_layout()
