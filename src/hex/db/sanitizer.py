"""SQL sanitizer for the database execution engine.

Validates SQL queries to ensure only safe, read-only SELECT statements
are executed. Blocks write operations, DDL, multiple statements, and
comment injection attempts.
"""

import re

from hex.shared.errors import ForbiddenQueryError


# ── Forbidden SQL keywords that indicate write/DDL operations ──
_FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
    "REINDEX",
]

# Pre-compiled regex patterns for forbidden keywords (word-boundary matched)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Pattern to detect SQL comments (both -- and /* */ styles)
_COMMENT_PATTERN = re.compile(r"(--|/\*)")


def validate(sql: str) -> None:
    """Validate that a SQL string is a safe, read-only query.

    Checks for:
    1. Forbidden keywords (INSERT, UPDATE, DELETE, DROP, ALTER, etc.)
    2. Multiple statements (semicolons within the query body)
    3. Comment injection attempts (-- and /* */ patterns)

    Args:
        sql: The SQL query string to validate.

    Raises:
        ForbiddenQueryError: If the SQL contains any forbidden operations,
            multiple statements, or comment injection attempts.
    """
    if not sql or not sql.strip():
        raise ForbiddenQueryError("Empty SQL query", original_sql=sql or "")

    cleaned = sql.strip()

    # ── Block comment injection ──
    if _COMMENT_PATTERN.search(cleaned):
        raise ForbiddenQueryError(
            "SQL comments are not allowed (potential injection)",
            original_sql=sql,
        )

    # ── Block multiple statements (semicolons within the body) ──
    # Remove trailing semicolon before checking
    body = cleaned.rstrip(";")
    if ";" in body:
        raise ForbiddenQueryError(
            "Multiple SQL statements are not allowed",
            original_sql=sql,
        )

    # ── Block forbidden keywords ──
    match = _FORBIDDEN_PATTERN.search(cleaned)
    if match:
        keyword = match.group(1).upper()
        raise ForbiddenQueryError(
            f"Forbidden SQL operation: {keyword}",
            original_sql=sql,
        )
