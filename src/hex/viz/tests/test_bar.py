"""Tests for bar chart renderers.

Verifies that bar, grouped bar, and stacked bar charts render
correctly with appropriate data.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from hex.shared.models import ChartRequest, ChartType
from hex.viz.chart_types.bar import render, render_grouped
from hex.viz.config import ChartConfig


class TestBarChart:
    """Tests for the simple bar chart renderer."""

    def test_renders_with_categorical_x_numeric_y(self):
        """Bar chart should render with categorical x and numeric y data."""
        data = [
            {"category": "A", "value": 10},
            {"category": "B", "value": 25},
            {"category": "C", "value": 15},
        ]
        request = ChartRequest(data=data, chart_type=ChartType.BAR)
        config = ChartConfig()

        fig = render(data, request, config)
        assert fig is not None
        plt.close(fig)


class TestGroupedBarChart:
    """Tests for the grouped bar chart renderer."""

    def test_renders_with_group_column(self):
        """Grouped bar should render with multiple y-columns."""
        data = [
            {"team": "A", "q1": 100, "q2": 150},
            {"team": "B", "q1": 200, "q2": 180},
        ]
        request = ChartRequest(
            data=data,
            chart_type=ChartType.GROUPED_BAR,
            x_column="team",
            y_columns=["q1", "q2"],
        )
        config = ChartConfig()

        fig = render_grouped(data, request, config)
        assert fig is not None
        plt.close(fig)
