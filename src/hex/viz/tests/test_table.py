"""Tests for the table-as-image renderer.

Verifies that tables render with mixed-type data and produce
valid PNG bytes.
"""

import matplotlib

matplotlib.use("Agg")

from hex.shared.models import ChartRequest, ChartType
from hex.viz.engine import ChartEngine


class TestTableChart:
    """Tests for the table chart renderer."""

    def test_renders_with_mixed_type_data(self):
        """Table should render with mixed string and numeric data."""
        data = [
            {"name": "Alice", "age": 30, "active": "yes"},
            {"name": "Bob", "age": 25, "active": "no"},
            {"name": "Charlie", "age": 35, "active": "yes"},
        ]
        engine = ChartEngine()
        request = ChartRequest(data=data, chart_type=ChartType.TABLE)
        result = engine.render(request)
        assert len(result.image_bytes) > 0

    def test_produces_valid_png_bytes(self):
        """Table renderer should produce valid PNG bytes."""
        data = [
            {"id": 1, "status": "active"},
            {"id": 2, "status": "inactive"},
        ]
        engine = ChartEngine()
        request = ChartRequest(data=data, chart_type=ChartType.TABLE)
        result = engine.render(request)
        assert result.image_bytes[:4] == b"\x89PNG"
