"""Chart export utilities.

Converts matplotlib Figure objects to bytes or files. Always closes
the figure in a finally block to prevent memory leaks.
"""

import io
from pathlib import Path

from matplotlib.figure import Figure

from hex.viz.config import ChartConfig


def figure_to_bytes(fig: Figure, config: ChartConfig) -> bytes:
    """Render a matplotlib Figure to PNG bytes.

    Saves the figure to an in-memory buffer and returns the raw bytes.
    Always closes the figure to prevent matplotlib memory leaks.

    Args:
        fig:    The matplotlib Figure to export.
        config: ChartConfig with DPI and format settings.

    Returns:
        Raw PNG image bytes.
    """
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format=config.output_format, dpi=config.dpi,
                    bbox_inches="tight", facecolor=fig.get_facecolor())
        buf.seek(0)
        return buf.read()
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)


def figure_to_file(fig: Figure, config: ChartConfig, path: str | Path) -> Path:
    """Save a matplotlib Figure to a file on disk.

    Always closes the figure to prevent matplotlib memory leaks.

    Args:
        fig:    The matplotlib Figure to export.
        config: ChartConfig with DPI and format settings.
        path:   File path to save the image to.

    Returns:
        Path object pointing to the saved file.
    """
    output_path = Path(path)
    try:
        fig.savefig(output_path, format=config.output_format, dpi=config.dpi,
                    bbox_inches="tight", facecolor=fig.get_facecolor())
        return output_path
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)
