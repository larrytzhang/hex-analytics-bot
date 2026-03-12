"""Chart type inference from data shape.

Automatically determines the best chart type based on column data types,
column count, and data characteristics. Used when ChartType.AUTO is requested.
"""

from typing import Any

from hex.shared.models import ChartType

from hex.viz.validators import detect_categorical_columns, detect_numeric_columns


def _is_datetime_like(values: list[Any]) -> bool:
    """Check if a list of values looks like datetime strings.

    Heuristic: checks if values are strings containing date-like patterns.

    Args:
        values: Sample values to check.

    Returns:
        True if values appear to be datetime strings.
    """
    if not values:
        return False
    for v in values[:5]:
        if not isinstance(v, str):
            return False
        # Simple heuristic: contains digits and dashes/slashes typical of dates
        if not any(c.isdigit() for c in v):
            return False
        if not any(sep in v for sep in ["-", "/", "T"]):
            return False
    return True


def infer_chart_type(data: list[dict[str, Any]], columns: list[str]) -> ChartType:
    """Infer the best chart type from data shape and column types.

    Heuristics:
    - 1 categorical + 1 numeric -> BAR
    - datetime-like + numeric(s) -> LINE / MULTI_LINE
    - 2 numerics only -> SCATTER
    - 1 categorical + multiple numerics -> GROUPED_BAR
    - Fallback -> BAR

    Args:
        data:    Row-oriented list of dicts.
        columns: Ordered list of column names.

    Returns:
        The inferred ChartType enum value.
    """
    if not data or not columns:
        return ChartType.TABLE

    numeric_cols = detect_numeric_columns(data)
    cat_cols = detect_categorical_columns(data)

    # Check for datetime-like columns among categoricals
    datetime_cols = []
    for col in cat_cols:
        sample_vals = [row.get(col) for row in data[:5] if row.get(col) is not None]
        if _is_datetime_like(sample_vals):
            datetime_cols.append(col)

    # datetime + numeric(s) -> LINE or MULTI_LINE
    if datetime_cols and numeric_cols:
        if len(numeric_cols) > 1:
            return ChartType.MULTI_LINE
        return ChartType.LINE

    # 1 categorical + 1 numeric -> BAR
    non_datetime_cats = [c for c in cat_cols if c not in datetime_cols]
    if len(non_datetime_cats) >= 1 and len(numeric_cols) == 1:
        return ChartType.BAR

    # 1 categorical + multiple numerics -> GROUPED_BAR
    if len(non_datetime_cats) >= 1 and len(numeric_cols) > 1:
        return ChartType.GROUPED_BAR

    # 2+ numerics only (no categoricals) -> SCATTER
    if len(numeric_cols) >= 2 and len(cat_cols) == 0:
        return ChartType.SCATTER

    # Fallback -> BAR if we have any numeric, else TABLE
    if numeric_cols:
        return ChartType.BAR

    return ChartType.TABLE
