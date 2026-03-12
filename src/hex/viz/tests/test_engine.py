"""Tests for the ChartEngine.

Verifies that charts render to valid PNG bytes, AUTO inference works,
and empty data raises the appropriate error.
"""

import pytest

from hex.shared.errors import EmptyDataError
from hex.shared.models import ChartRequest, ChartType
from hex.viz.engine import ChartEngine


@pytest.fixture
def engine():
    """Create a fresh ChartEngine instance for each test."""
    return ChartEngine()


@pytest.fixture
def sample_bar_data():
    """Sample data suitable for bar charts."""
    return [
        {"category": "A", "value": 10},
        {"category": "B", "value": 25},
        {"category": "C", "value": 15},
        {"category": "D", "value": 30},
    ]


class TestRender:
    """Tests for the render method."""

    def test_bar_chart_produces_png_bytes(self, engine, sample_bar_data):
        """BAR chart should produce non-empty PNG bytes."""
        request = ChartRequest(data=sample_bar_data, chart_type=ChartType.BAR)
        result = engine.render(request)
        assert len(result.image_bytes) > 0
        # PNG magic bytes
        assert result.image_bytes[:4] == b"\x89PNG"
        assert result.chart_type == ChartType.BAR

    def test_auto_inference_produces_valid_chart(self, engine, sample_bar_data):
        """AUTO chart type should infer a valid type and produce a chart."""
        request = ChartRequest(data=sample_bar_data, chart_type=ChartType.AUTO)
        result = engine.render(request)
        assert len(result.image_bytes) > 0
        assert result.chart_type != ChartType.AUTO  # Should be resolved
        assert result.chart_type != ChartType.NONE

    def test_empty_data_raises_error(self, engine):
        """Empty data should raise EmptyDataError."""
        request = ChartRequest(data=[], chart_type=ChartType.BAR)
        with pytest.raises(EmptyDataError):
            engine.render(request)

    def test_line_chart_renders(self, engine):
        """LINE chart should produce valid PNG bytes."""
        data = [
            {"date": "2024-01-01", "revenue": 100},
            {"date": "2024-02-01", "revenue": 150},
            {"date": "2024-03-01", "revenue": 200},
        ]
        request = ChartRequest(data=data, chart_type=ChartType.LINE)
        result = engine.render(request)
        assert len(result.image_bytes) > 0
        assert result.image_bytes[:4] == b"\x89PNG"

    def test_pie_chart_renders(self, engine, sample_bar_data):
        """PIE chart should produce valid PNG bytes."""
        request = ChartRequest(data=sample_bar_data, chart_type=ChartType.PIE)
        result = engine.render(request)
        assert len(result.image_bytes) > 0

    def test_scatter_chart_renders(self, engine):
        """SCATTER chart should produce valid PNG bytes."""
        data = [
            {"x": 1.0, "y": 2.5},
            {"x": 2.0, "y": 3.0},
            {"x": 3.0, "y": 1.5},
        ]
        request = ChartRequest(data=data, chart_type=ChartType.SCATTER)
        result = engine.render(request)
        assert len(result.image_bytes) > 0

    def test_table_chart_renders(self, engine, sample_bar_data):
        """TABLE chart should produce valid PNG bytes."""
        request = ChartRequest(data=sample_bar_data, chart_type=ChartType.TABLE)
        result = engine.render(request)
        assert len(result.image_bytes) > 0


class TestSupportedChartTypes:
    """Tests for supported_chart_types method."""

    def test_returns_all_registered_types(self, engine):
        """Should return all 9 renderable chart types."""
        supported = engine.supported_chart_types()
        assert ChartType.BAR in supported
        assert ChartType.LINE in supported
        assert ChartType.PIE in supported
        assert ChartType.SCATTER in supported
        assert ChartType.TABLE in supported
        # NONE and AUTO are not renderable
        assert ChartType.NONE not in supported
        assert ChartType.AUTO not in supported
