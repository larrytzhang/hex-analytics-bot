"""Tests for line chart renderers.

Verifies that single-line and multi-line charts render correctly.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from hex.shared.models import ChartRequest, ChartType
from hex.viz.chart_types.line import render, render_multi
from hex.viz.config import ChartConfig


class TestLineChart:
    """Tests for the single-line chart renderer."""

    def test_renders_with_datetime_x_numeric_y(self):
        """Line chart should render with datetime x and numeric y data."""
        data = [
            {"date": "2024-01-01", "revenue": 100},
            {"date": "2024-02-01", "revenue": 150},
            {"date": "2024-03-01", "revenue": 200},
        ]
        request = ChartRequest(data=data, chart_type=ChartType.LINE)
        config = ChartConfig()

        fig = render(data, request, config)
        assert fig is not None
        plt.close(fig)


class TestMultiLineChart:
    """Tests for the multi-line chart renderer."""

    def test_renders_with_multiple_y_columns(self):
        """Multi-line chart should render with multiple y-columns."""
        data = [
            {"date": "2024-01-01", "revenue": 100, "cost": 50},
            {"date": "2024-02-01", "revenue": 150, "cost": 60},
            {"date": "2024-03-01", "revenue": 200, "cost": 75},
        ]
        request = ChartRequest(
            data=data,
            chart_type=ChartType.MULTI_LINE,
            x_column="date",
            y_columns=["revenue", "cost"],
        )
        config = ChartConfig()

        fig = render_multi(data, request, config)
        assert fig is not None
        plt.close(fig)
