"""Configuration for the visualization engine.

Defines ChartConfig with rendering parameters (dimensions, DPI, theme)
used by all chart renderers and the export module.
"""

from dataclasses import dataclass


@dataclass
class ChartConfig:
    """Rendering configuration for chart generation.

    Attributes:
        width:         Figure width in inches.
        height:        Figure height in inches.
        dpi:           Dots per inch for the output image.
        theme:         Theme name from the styling module.
        output_format: Image format string (e.g. "png", "svg").
    """

    width: float = 10.0
    height: float = 6.0
    dpi: int = 150
    theme: str = "professional_light"
    output_format: str = "png"
