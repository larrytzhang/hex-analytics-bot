"""Chart engine — the main entry point for the visualization module.

Implements ChartEngineInterface by dispatching to the appropriate
chart type renderer, applying styling, and exporting to image bytes.
Uses matplotlib's Agg backend for thread-safe, non-interactive rendering.
"""

import matplotlib

matplotlib.use("Agg")  # Non-interactive, thread-safe backend

from typing import Any, Callable

from matplotlib.figure import Figure

from hex.shared.errors import EmptyDataError, UnsupportedChartTypeError
from hex.shared.interfaces import ChartEngineInterface
from hex.shared.models import ChartRequest, ChartResult, ChartType

from hex.viz.chart_types import bar, line, pie, scatter, table
from hex.viz.config import ChartConfig
from hex.viz.export import figure_to_bytes
from hex.viz.inference import infer_chart_type
from hex.viz.validators import validate_columns, validate_data


# Type alias for renderer functions
RendererFunc = Callable[[list[dict[str, Any]], ChartRequest, ChartConfig], Figure]


class ChartEngine(ChartEngineInterface):
    """Concrete implementation of the chart engine.

    Maintains a registry mapping ChartType to renderer functions.
    Handles the full render pipeline: validate -> infer -> dispatch ->
    style -> export.

    Attributes:
        _config:    Default chart configuration.
        _renderers: Registry mapping ChartType to renderer functions.
    """

    def __init__(self, config: ChartConfig | None = None) -> None:
        """Initialize the chart engine with optional custom configuration.

        Args:
            config: Optional ChartConfig override. Uses defaults if None.
        """
        self._config = config or ChartConfig()
        self._renderers: dict[ChartType, RendererFunc] = {
            ChartType.BAR: bar.render,
            ChartType.GROUPED_BAR: bar.render_grouped,
            ChartType.STACKED_BAR: bar.render_stacked,
            ChartType.LINE: line.render,
            ChartType.MULTI_LINE: line.render_multi,
            ChartType.PIE: pie.render,
            ChartType.DONUT: pie.render_donut,
            ChartType.SCATTER: scatter.render,
            ChartType.TABLE: table.render,
        }

    def render(self, request: ChartRequest) -> ChartResult:
        """Generate a chart from structured data.

        Full pipeline: validate data -> resolve chart type (infer if AUTO)
        -> dispatch to renderer -> export to bytes.

        Args:
            request: ChartRequest containing data, chart type, and config.

        Returns:
            ChartResult with PNG image bytes and the actual chart type used.

        Raises:
            EmptyDataError: If no plottable data is provided.
            UnsupportedChartTypeError: If the chart type is not in the registry.
        """
        # Validate input data
        validate_data(request.data, request.chart_type)
        validate_columns(request.data, request.x_column, request.y_columns)

        # Build config from request overrides
        config = ChartConfig(
            width=request.width,
            height=request.height,
            dpi=request.dpi,
            theme=self._config.theme,
            output_format=self._config.output_format,
        )

        # Resolve chart type (infer if AUTO)
        chart_type = request.chart_type
        if chart_type == ChartType.AUTO:
            columns = list(request.data[0].keys()) if request.data else []
            chart_type = infer_chart_type(request.data, columns)

        # Dispatch to renderer
        renderer = self._renderers.get(chart_type)
        if renderer is None:
            raise UnsupportedChartTypeError(f"Unsupported chart type: {chart_type}")

        fig = renderer(request.data, request, config)
        image_bytes = figure_to_bytes(fig, config)

        return ChartResult(
            image_bytes=image_bytes,
            chart_type=chart_type,
            metadata={"width": config.width, "height": config.height, "dpi": config.dpi},
        )

    def supported_chart_types(self) -> list[ChartType]:
        """Return list of chart types this engine can produce.

        Returns:
            List of ChartType enum values registered in the renderer registry.
        """
        return list(self._renderers.keys())
