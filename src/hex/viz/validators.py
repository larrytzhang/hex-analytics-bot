"""Input validation and data normalization for the visualization engine.

Validates that chart data meets minimum requirements before rendering,
and provides helpers to normalize row-oriented dicts into column-oriented
format for matplotlib consumption.
"""

from typing import Any

from hex.shared.errors import DataTypeMismatchError, EmptyDataError
from hex.shared.models import ChartType


def validate_data(data: list[dict[str, Any]], chart_type: ChartType) -> None:
    """Validate that data is suitable for chart rendering.

    Checks for empty datasets and verifies that numeric columns exist
    for chart types that require them.

    Args:
        data:       Row-oriented list of dicts to validate.
        chart_type: The intended chart type for rendering.

    Raises:
        EmptyDataError: If data is empty or has no rows.
        DataTypeMismatchError: If required numeric columns are missing.
    """
    if not data:
        raise EmptyDataError("No data provided for chart rendering")

    if len(data) == 0:
        raise EmptyDataError("Empty dataset — nothing to plot")


def validate_columns(
    data: list[dict[str, Any]],
    x_column: str | None,
    y_columns: list[str] | None,
) -> None:
    """Validate that specified columns exist in the data.

    Args:
        data:      Row-oriented list of dicts.
        x_column:  Name of the x-axis column, or None.
        y_columns: Names of y-axis columns, or None.

    Raises:
        DataTypeMismatchError: If specified columns don't exist in the data.
    """
    if not data:
        return

    available = set(data[0].keys())

    if x_column and x_column not in available:
        raise DataTypeMismatchError(
            f"x_column '{x_column}' not found. Available: {sorted(available)}"
        )

    if y_columns:
        for col in y_columns:
            if col not in available:
                raise DataTypeMismatchError(
                    f"y_column '{col}' not found. Available: {sorted(available)}"
                )


def to_column_oriented(data: list[dict[str, Any]]) -> dict[str, list[Any]]:
    """Convert row-oriented dicts to column-oriented format.

    Transforms [{col1: v1, col2: v2}, ...] into {col1: [v1, ...], col2: [v2, ...]}.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        Dict mapping column names to lists of values.
    """
    if not data:
        return {}

    columns: dict[str, list[Any]] = {key: [] for key in data[0].keys()}
    for row in data:
        for key, value in row.items():
            if key in columns:
                columns[key].append(value)

    return columns


def detect_numeric_columns(data: list[dict[str, Any]]) -> list[str]:
    """Identify columns containing numeric data.

    Samples up to 10 rows to determine which columns contain numeric values.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        List of column names that contain numeric data.
    """
    if not data:
        return []

    numeric_cols = []
    sample = data[:10]

    for col in data[0].keys():
        values = [row.get(col) for row in sample if row.get(col) is not None]
        if values and all(isinstance(v, (int, float)) for v in values):
            numeric_cols.append(col)

    return numeric_cols


def detect_categorical_columns(data: list[dict[str, Any]]) -> list[str]:
    """Identify columns containing categorical (string) data.

    Args:
        data: Row-oriented list of dicts.

    Returns:
        List of column names that contain string data.
    """
    if not data:
        return []

    cat_cols = []
    sample = data[:10]

    for col in data[0].keys():
        values = [row.get(col) for row in sample if row.get(col) is not None]
        if values and all(isinstance(v, str) for v in values):
            cat_cols.append(col)

    return cat_cols
