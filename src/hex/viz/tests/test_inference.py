"""Tests for chart type inference.

Verifies that the inference engine correctly detects chart types
based on data shape and column types.
"""

from hex.shared.models import ChartType
from hex.viz.inference import infer_chart_type


class TestInferChartType:
    """Tests for the infer_chart_type function."""

    def test_one_cat_one_num_is_bar(self):
        """1 categorical + 1 numeric column should infer BAR."""
        data = [
            {"name": "Alice", "score": 85},
            {"name": "Bob", "score": 92},
        ]
        result = infer_chart_type(data, ["name", "score"])
        assert result == ChartType.BAR

    def test_datetime_plus_num_is_line(self):
        """Datetime-like column + numeric should infer LINE."""
        data = [
            {"date": "2024-01-15", "revenue": 100},
            {"date": "2024-02-15", "revenue": 150},
        ]
        result = infer_chart_type(data, ["date", "revenue"])
        assert result == ChartType.LINE

    def test_datetime_plus_multi_num_is_multi_line(self):
        """Datetime + multiple numeric columns should infer MULTI_LINE."""
        data = [
            {"date": "2024-01-15", "revenue": 100, "cost": 50},
            {"date": "2024-02-15", "revenue": 150, "cost": 60},
        ]
        result = infer_chart_type(data, ["date", "revenue", "cost"])
        assert result == ChartType.MULTI_LINE

    def test_two_nums_is_scatter(self):
        """2 numeric columns only should infer SCATTER."""
        data = [
            {"x": 1.0, "y": 2.5},
            {"x": 2.0, "y": 3.0},
        ]
        result = infer_chart_type(data, ["x", "y"])
        assert result == ChartType.SCATTER

    def test_empty_data_is_table(self):
        """Empty data should default to TABLE."""
        result = infer_chart_type([], [])
        assert result == ChartType.TABLE

    def test_one_cat_multi_num_is_grouped_bar(self):
        """1 categorical + multiple numeric columns should infer GROUPED_BAR."""
        data = [
            {"team": "A", "q1": 100, "q2": 150},
            {"team": "B", "q1": 200, "q2": 180},
        ]
        result = infer_chart_type(data, ["team", "q1", "q2"])
        assert result == ChartType.GROUPED_BAR
